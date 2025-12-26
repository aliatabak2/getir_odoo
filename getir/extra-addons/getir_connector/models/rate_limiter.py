"""
Getir API Rate Limiter Module

Thread-safe rate limiting implementation for Getir API endpoints.
Uses a sliding window algorithm with endpoint-specific limits.
"""

import time
import re
import threading
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Thread-safe rate limiter for API endpoints.
    
    Each endpoint has:
    - max_requests: Maximum number of requests allowed in the window
    - window_seconds: Time window in seconds
    - cooldown_seconds: Wait time when limit is exceeded
    """
    
    # Rate limit definitions: pattern -> (max_requests, window_seconds, cooldown_seconds)
    RATE_LIMITS = {
        # Auth
        r'^/auth/login$': (10, 60, 30),
        
        # Food Orders - Reports
        r'^/food-orders/report$': (3, 60, 20),
        r'^/food-orders/report/details$': (3, 60, 20),
        
        # Food Orders - Active & Periodic
        r'^/food-orders/active$': (20, 60, 30),
        r'^/food-orders/periodic/': (20, 60, 30),  # unapproved, cancelled
        
        # Food Orders - Cancel Options
        r'^/food-orders/[^/]+/cancel-options$': (40, 60, 60),
        
        # Food Orders - Order Actions (2 req, 60s, 30s)
        r'^/food-orders/[^/]+/verify-scheduled$': (2, 60, 30),
        r'^/food-orders/[^/]+/deliver$': (2, 60, 30),
        r'^/food-orders/[^/]+/prepare$': (2, 60, 30),
        r'^/food-orders/[^/]+/transfer-to-another-restaurant$': (2, 60, 30),
        r'^/food-orders/[^/]+/handover$': (2, 60, 30),
        r'^/food-orders/[^/]+/cancel$': (2, 60, 30),
        r'^/food-orders/[^/]+/verify$': (2, 60, 30),
        r'^/food-orders/[^/]+/invoice$': (2, 60, 30),
        r'^/food-orders/[^/]+$': (2, 60, 30),  # GET order by ID
        
        # Payment Methods
        r'^/payment-methods$': (2, 60, 30),
        
        # Products - Status (3 req, 60s, 30s)
        r'^/products/[^/]+/status$': (3, 60, 30),
        r'^/products/chain-id/[^/]+/status$': (3, 60, 30),
        
        # Products - Activate/Inactivate as Option (3 req, 60s, 30s)
        r'^/products/[^/]+/inactivate-as-option$': (3, 60, 30),
        r'^/products/[^/]+/activate-as-option$': (3, 60, 30),
        r'^/products/chain-id/[^/]+/activate-as-option$': (3, 60, 30),
        r'^/products/chain-id/[^/]+/inactivate-as-option$': (3, 60, 30),
        
        # Products - Option Products (3 req, 60s, 30s)
        r'^/products/option-products/[^/]+/activate-as-option$': (3, 60, 30),
        r'^/products/option-products/[^/]+/inactivate-as-option$': (3, 60, 30),
        r'^/products/option-products/chain-id/[^/]+/activate-as-option$': (3, 60, 30),
        r'^/products/option-products/chain-id/[^/]+/inactivate-as-option$': (3, 60, 30),
        
        # Products - Option Categories (3 req, 60s, 30s)
        r'^/products/[^/]+/option-categories/[^/]+/options/[^/]+/status$': (3, 60, 30),
        r'^/products/chain-id/[^/]+/option-categories/[^/]+/options/[^/]+/status$': (3, 60, 30),
        
        # Restaurants - Basic (2 req, 60s, 30s)
        r'^/restaurants$': (2, 60, 30),
        r'^/restaurants/menu$': (2, 60, 30),
        r'^/restaurants/option-products$': (2, 60, 30),
        r'^/restaurants/payment-methods$': (2, 60, 30),
        r'^/restaurants/payment-methods/active$': (2, 60, 30),
        r'^/restaurants/payment-methods/inactive$': (2, 60, 30),
        r'^/restaurants/pos-status$': (2, 60, 30),
        
        # Restaurants - Zones (2 req, 60s, 30s)
        r'^/restaurants/zones$': (2, 60, 30),
        r'^/restaurants/zones/eta$': (2, 60, 30),
        r'^/restaurants/zones/[^/]+$': (2, 60, 30),
        r'^/restaurants/zones/[^/]+/inactive$': (2, 60, 30),
        r'^/restaurants/zones/[^/]+/active$': (2, 60, 30),
        
        # Restaurants - Courier (2 req, 60s, 30s)
        r'^/restaurants/courier/disable$': (2, 60, 30),
        r'^/restaurants/courier/enable$': (2, 60, 30),
        
        # Restaurants - Configuration (2 req, 60s, 30s)
        r'^/restaurants/average-preparation-time$': (2, 60, 30),
        r'^/restaurants/delivery-duration$': (2, 60, 30),
        r'^/restaurants/delivery-duration/busyness$': (2, 60, 30),
        r'^/restaurants/status/close$': (2, 60, 30),
        r'^/restaurants/status/open$': (2, 60, 30),
        
        # Restaurants - Option Products Status (2 req, 60s, 30s)
        r'^/restaurants/option-products/[^/]+/option-categories/[^/]+/options/[^/]+/status$': (2, 60, 30),
        r'^/restaurants/option-products/chain-id/[^/]+/option-categories/[^/]+/options/[^/]+/status$': (2, 60, 30),
        
        # Restaurants - Reviews
        r'^/restaurants/reviews$': (2, 60, 30),
        
        # Restaurants with ID
        r'^/restaurants/[^/]+/zones/[^/]+$': (2, 60, 30),
    }
    
    # Default limit for unmatched endpoints
    DEFAULT_LIMIT = (5, 60, 30)
    
    def __init__(self):
        self._lock = threading.Lock()
        # Structure: {endpoint_pattern: [(timestamp1, timestamp2, ...)]}
        self._request_times = defaultdict(list)
        # Compiled regex patterns for efficiency
        self._compiled_patterns = [(re.compile(pattern), limits) for pattern, limits in self.RATE_LIMITS.items()]
    
    def _get_limits(self, endpoint):
        """
        Get rate limit configuration for an endpoint.
        Returns (max_requests, window_seconds, cooldown_seconds)
        """
        for pattern, limits in self._compiled_patterns:
            if pattern.match(endpoint):
                return limits
        return self.DEFAULT_LIMIT
    
    def _normalize_endpoint(self, endpoint):
        """
        Normalize endpoint for consistent matching.
        Removes query strings and trailing slashes.
        """
        # Remove query string
        endpoint = endpoint.split('?')[0]
        # Remove trailing slash
        endpoint = endpoint.rstrip('/')
        return endpoint
    
    def _get_pattern_key(self, endpoint):
        """
        Get the pattern key for tracking requests.
        This groups similar endpoints together (e.g., all /food-orders/{id}/verify)
        """
        for pattern, _ in self._compiled_patterns:
            if pattern.match(endpoint):
                return pattern.pattern
        return endpoint
    
    def wait_if_needed(self, endpoint):
        """
        Check rate limit and wait if necessary.
        Returns the wait time in seconds (0 if no wait needed).
        """
        endpoint = self._normalize_endpoint(endpoint)
        max_requests, window_seconds, cooldown_seconds = self._get_limits(endpoint)
        pattern_key = self._get_pattern_key(endpoint)
        
        with self._lock:
            now = time.time()
            window_start = now - window_seconds
            
            # Clean old requests outside the window
            self._request_times[pattern_key] = [
                t for t in self._request_times[pattern_key] if t > window_start
            ]
            
            current_count = len(self._request_times[pattern_key])
            
            if current_count >= max_requests:
                # Calculate wait time
                oldest_request = self._request_times[pattern_key][0]
                wait_time = (oldest_request + window_seconds) - now
                
                if wait_time > 0:
                    _logger.warning(
                        "Rate limit reached for %s (%d/%d requests). Waiting %.2f seconds (cooldown: %ds)",
                        endpoint, current_count, max_requests, wait_time, cooldown_seconds
                    )
                    return max(wait_time, cooldown_seconds)
            
            # Record this request
            self._request_times[pattern_key].append(now)
            _logger.debug(
                "Rate limit check for %s: %d/%d requests in window",
                endpoint, current_count + 1, max_requests
            )
            return 0
    
    def acquire(self, endpoint):
        """
        Acquire permission to make a request.
        Blocks until rate limit allows the request.
        """
        wait_time = self.wait_if_needed(endpoint)
        if wait_time > 0:
            _logger.info("Rate limiter sleeping for %.2f seconds for endpoint: %s", wait_time, endpoint)
            time.sleep(wait_time)
            # After sleeping, register the request
            with self._lock:
                pattern_key = self._get_pattern_key(self._normalize_endpoint(endpoint))
                self._request_times[pattern_key].append(time.time())
    
    def get_status(self, endpoint):
        """
        Get current rate limit status for an endpoint.
        Returns dict with remaining requests and reset time.
        """
        endpoint = self._normalize_endpoint(endpoint)
        max_requests, window_seconds, _ = self._get_limits(endpoint)
        pattern_key = self._get_pattern_key(endpoint)
        
        with self._lock:
            now = time.time()
            window_start = now - window_seconds
            
            # Count requests in current window
            current_count = len([
                t for t in self._request_times[pattern_key] if t > window_start
            ])
            
            remaining = max(0, max_requests - current_count)
            
            # Calculate reset time
            if self._request_times[pattern_key]:
                oldest = min(t for t in self._request_times[pattern_key] if t > window_start)
                reset_in = (oldest + window_seconds) - now
            else:
                reset_in = 0
            
            return {
                'endpoint': endpoint,
                'max_requests': max_requests,
                'remaining': remaining,
                'reset_in_seconds': max(0, reset_in),
                'window_seconds': window_seconds,
            }


# Global rate limiter instance
_rate_limiter = None
_rate_limiter_lock = threading.Lock()


def get_rate_limiter():
    """Get the global RateLimiter instance (singleton pattern)."""
    global _rate_limiter
    if _rate_limiter is None:
        with _rate_limiter_lock:
            if _rate_limiter is None:
                _rate_limiter = RateLimiter()
    return _rate_limiter
