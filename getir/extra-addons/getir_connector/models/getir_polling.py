import threading
import time
import logging
from odoo import api, registry

_logger = logging.getLogger(__name__)

# Global thread reference
_polling_thread = None
_stop_polling = False


def start_getir_polling(db_name, interval=15):
    """Getir siparişlerini belirli aralıklarla çeken polling thread'i başlat"""
    global _polling_thread, _stop_polling
    
    if _polling_thread and _polling_thread.is_alive():
        _logger.info("Getir polling zaten çalışıyor")
        return
    
    _stop_polling = False
    _polling_thread = threading.Thread(
        target=_polling_loop,
        args=(db_name, interval),
        daemon=True,
        name="GetirOrderPolling"
    )
    _polling_thread.start()
    _logger.info("Getir polling başlatıldı (her %s saniye)", interval)


def stop_getir_polling():
    """Polling thread'i durdur"""
    global _stop_polling
    _stop_polling = True
    _logger.info("Getir polling durduruldu")


def _polling_loop(db_name, interval):
    """Ana polling döngüsü"""
    global _stop_polling
    
    while not _stop_polling:
        try:
            _fetch_orders_once(db_name)
        except Exception as e:
            _logger.error("Getir polling hatası: %s", e)
        
        # Interval süresince bekle (ama _stop_polling kontrol et)
        for _ in range(interval):
            if _stop_polling:
                break
            time.sleep(1)


def _fetch_orders_once(db_name):
    """Tek seferlik sipariş çekme"""
    try:
        db_registry = registry(db_name)
        with db_registry.cursor() as cr:
            env = api.Environment(cr, 1, {})  # SUPERUSER_ID = 1
            
            apis = env["getir.api"].search([("active", "=", True)])
            
            for api_record in apis:
                try:
                    result = api_record.get_active_orders()
                    
                    orders = []
                    if isinstance(result, list):
                        orders = result
                    elif isinstance(result, dict):
                        orders = result.get("data", []) or result.get("orders", []) or []
                        if not orders and result.get("id"):
                            orders = [result]
                    
                    for order_data in orders:
                        gid = str(order_data.get("id") or order_data.get("_id") or "")
                        if not gid:
                            continue
                        
                        existing = env["getir.order"].search([
                            ("getir_id", "=", gid)
                        ], limit=1)
                        
                        if existing:
                            continue
                        
                        try:
                            env["getir.order"].create_from_payload(order_data)
                            cr.commit()
                            _logger.info("Getir polling - yeni sipariş: %s", gid)
                        except Exception as e:
                            cr.rollback()
                            _logger.error("Getir polling - sipariş hatası (%s): %s", gid, e)
                            
                except Exception as e:
                    _logger.error("Getir polling - API hatası (%s): %s", api_record.name, e)
                    
    except Exception as e:
        _logger.error("Getir polling - DB hatası: %s", e)
