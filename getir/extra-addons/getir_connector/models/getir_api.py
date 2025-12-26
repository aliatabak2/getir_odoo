import requests
import json
import logging
from datetime import datetime, timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError

from .rate_limiter import get_rate_limiter

_logger = logging.getLogger(__name__)


class GetirAPI(models.Model):
    _name = "getir.api"
    _description = "Getir Yemek API Configuration"

    name = fields.Char(default="Getir API", required=True)

    app_secret_key = fields.Char(required=True)
    restaurant_secret_key = fields.Char(required=True)

    token = fields.Char(readonly=True)
    token_expire = fields.Datetime(string="Token Expire Time")

    api_url = fields.Char(
        default="https://food-external-api-gateway.development.getirapi.com",
        required=True,
    )

    active = fields.Boolean(default=True)

    # Polling durumu
    polling_active = fields.Boolean(string="Otomatik Sipariş Çekme", default=False)

    def action_start_polling(self):
        """15 saniyede bir sipariş çekmeyi başlat"""
        from . import getir_polling
        db_name = self.env.cr.dbname
        getir_polling.start_getir_polling(db_name, interval=15)
        self.write({"polling_active": True})
        return self._notify("Getir Polling", "Otomatik sipariş çekme başlatıldı (15 sn)")

    def action_stop_polling(self):
        """Sipariş çekmeyi durdur"""
        from . import getir_polling
        getir_polling.stop_getir_polling()
        self.write({"polling_active": False})
        return self._notify("Getir Polling", "Otomatik sipariş çekme durduruldu")

    # -------------------------------------------
    # LOGIN
    # -------------------------------------------
    def action_login(self):
        # Apply rate limiting for login endpoint
        rate_limiter = get_rate_limiter()
        rate_limiter.acquire("/auth/login")
        
        url = f"{self.api_url}/auth/login"
        payload = {
            "appSecretKey": self.app_secret_key,
            "restaurantSecretKey": self.restaurant_secret_key,
        }
        headers = {"Content-Type": "application/json"}

        res = requests.post(url, json=payload, timeout=20)

        if res.status_code != 200:
            raise UserError(f"Login failed: {res.text}")

        data = res.json()
        token = data.get("token") or data.get("data", {}).get("token")

        self.write({
            "token": token,
            "token_expire": datetime.utcnow() + timedelta(hours=1),
        })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Getir API",
                "message": "Login success. Token received.",
                "type": "success",
            },
        }

    def action_sync_menu(self):
        """Menüyü Getir'den çek ve senkronize et"""
        self.ensure_one()
        return self.env["getir.menu.sync"].action_quick_sync()

    # -------------------------------------------
    # TOKEN CHECK
    # -------------------------------------------
    def _ensure_token(self):
        if not self.token or not self.token_expire or self.token_expire < datetime.utcnow():
            self.action_login()

    # -------------------------------------------
    # API CALL WRAPPER
    # -------------------------------------------
    def call(self, method, endpoint, data=None, json_data=None, params=None, headers=None, files=None):
        self._ensure_token()
        
        # Apply rate limiting before making the request
        rate_limiter = get_rate_limiter()
        rate_limiter.acquire(endpoint)

        url = f"{self.api_url}{endpoint}"

        hdrs = {
            "token": self.token,
            "Content-Type": "application/json",
        }
        if headers:
            hdrs.update(headers)

        try:
            res = requests.request(
                method=method,
                url=url,
                json=json_data,
                data=data,
                params=params,
                files=files,
                headers=hdrs,
                timeout=30,
            )
        except Exception as e:
            self.env["getir.log"].create_log(endpoint, data or json_data, None, f"Error: {e}")
            raise UserError(str(e))

        # Log
        self.env["getir.log"].create_log(endpoint, data or json_data, res.text, res.status_code)

        if res.status_code >= 400:
            raise UserError(f"Getir API Error {res.status_code}: {res.text}")

        return res.json() if "application/json" in res.headers.get("Content-Type", "") else res.text

    # -------------------------------------------
    # POS STATUS MANAGEMENT
    # -------------------------------------------
    def get_pos_status(self):
        """POS durumunu sorgula"""
        # Apply rate limiting
        rate_limiter = get_rate_limiter()
        rate_limiter.acquire("/restaurants/pos-status")
        
        payload = {
            "appSecretKey": self.app_secret_key,
            "restaurantSecretKey": self.restaurant_secret_key,
        }
        url = f"{self.api_url}/restaurants/pos-status"
        headers = {"Content-Type": "application/json"}
        
        res = requests.post(url, json=payload, timeout=20)
        self.env["getir.log"].create_log("/restaurants/pos-status", payload, res.text, res.status_code, method="POST")
        
        if res.status_code >= 400:
            raise UserError(f"POS Status sorgu hatası: {res.text}")
        return res.json()

    def set_pos_status(self, status: int):
        """
        POS durumunu ayarla.
        status: 100 = Aktif, 200 = Pasif
        """
        # Apply rate limiting
        rate_limiter = get_rate_limiter()
        rate_limiter.acquire("/restaurants/pos-status")
        
        payload = {
            "posStatus": status,
            "appSecretKey": self.app_secret_key,
            "restaurantSecretKey": self.restaurant_secret_key,
        }
        url = f"{self.api_url}/restaurants/pos-status"
        headers = {"Content-Type": "application/json"}
        
        res = requests.put(url, json=payload, timeout=20)
        self.env["getir.log"].create_log("/restaurants/pos-status", payload, res.text, res.status_code, method="PUT")
        
        if res.status_code >= 400:
            raise UserError(f"POS Status güncelleme hatası: {res.text}")
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Getir POS Status",
                "message": f"POS durumu {'Aktif' if status == 100 else 'Pasif'} olarak güncellendi.",
                "type": "success",
            },
        }

    def action_activate_pos(self):
        """POS'u aktif et"""
        return self.set_pos_status(100)

    def action_deactivate_pos(self):
        """POS'u pasif et"""
        return self.set_pos_status(200)

    # -------------------------------------------
    # ORDER LIFECYCLE
    # -------------------------------------------
    def verify_order(self, order_id: str):
        """Siparişi onayla (yeni siparişler için)"""
        return self.call("POST", f"/food-orders/{order_id}/verify")

    def verify_scheduled_order(self, order_id: str):
        """İleri tarihli siparişi onayla"""
        return self.call("POST", f"/food-orders/{order_id}/verify-scheduled")

    def prepare_order(self, order_id: str):
        """Siparişi hazırlanıyor olarak işaretle"""
        return self.call("POST", f"/food-orders/{order_id}/prepare")

    def handover_order(self, order_id: str):
        """Siparişi Getir kuryesine teslim et (deliveryType: 1)"""
        return self.call("POST", f"/food-orders/{order_id}/handover")

    def deliver_order(self, order_id: str):
        """Siparişi müşteriye teslim et (deliveryType: 2 - restoran kurye)"""
        return self.call("POST", f"/food-orders/{order_id}/deliver")

    def cancel_order_by_restaurant(self, order_id: str, reason_id: str, note: str = "", product_id: str = None):
        """
        Siparişi restoran tarafından iptal et.
        product_id verilirse o ürün 'Tükendi' olarak işaretlenir.
        """
        payload = {
            "cancelReasonId": reason_id,
            "cancelNote": note,
        }
        if product_id:
            payload["productId"] = product_id
        return self.call("POST", f"/food-orders/{order_id}/cancel", json_data=payload)

    def get_active_orders(self):
        """Aktif siparişleri getir"""
        return self.call("POST", "/food-orders/active")

    def get_unapproved_orders(self):
        """Onaylanmamış siparişleri getir"""
        return self.call("POST", "/food-orders/periodic/unapproved")

    def get_cancelled_orders(self):
        """İptal edilen siparişleri getir (24 saat içinde)"""
        return self.call("POST", "/food-orders/periodic/cancelled")

    def action_fetch_orders(self):
        """Getir'den aktif siparişleri çek ve Odoo'ya ekle"""
        self.ensure_one()
        
        try:
            # Aktif siparişleri çek
            result = self.get_active_orders()
            _logger.info("Getir active orders response: %s", result)
            
            orders = []
            if isinstance(result, list):
                orders = result
            elif isinstance(result, dict):
                orders = result.get("data", []) or result.get("orders", []) or []
                # Eğer result tek bir obje ise listeye çevir
                if not orders and result.get("id"):
                    orders = [result]
            
            if not orders:
                return self._notify("Getir Siparişleri", "Aktif sipariş bulunamadı.")
            
            created_count = 0
            skipped_count = 0
            
            for order_data in orders:
                gid = str(order_data.get("id") or order_data.get("_id") or "")
                if not gid:
                    continue
                
                # Zaten var mı kontrol et
                existing = self.env["getir.order"].sudo().search([
                    ("getir_id", "=", gid)
                ], limit=1)
                
                if existing:
                    skipped_count += 1
                    continue
                
                try:
                    self.env["getir.order"].sudo().create_from_payload(order_data)
                    created_count += 1
                except Exception as e:
                    _logger.error("Sipariş oluşturma hatası (ID: %s): %s", gid, e)
            
            message = f"{created_count} yeni sipariş oluşturuldu"
            if skipped_count:
                message += f", {skipped_count} mevcut sipariş atlandı"
            
            return self._notify("Getir Siparişleri", message)
            
        except Exception as e:
            _logger.exception("Getir sipariş çekme hatası: %s", e)
            return self._notify("Getir Hata", f"Hata: {str(e)}")

    @api.model
    def _cron_fetch_orders(self):
        """Cron job: Tüm aktif API'lerden siparişleri otomatik çek"""
        apis = self.search([("active", "=", True)])
        for api in apis:
            try:
                result = api.get_active_orders()
                _logger.info("Getir cron - aktif siparişler: %s", result)
                
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
                    
                    existing = self.env["getir.order"].sudo().search([
                        ("getir_id", "=", gid)
                    ], limit=1)
                    
                    if existing:
                        continue
                    
                    try:
                        self.env["getir.order"].sudo().create_from_payload(order_data)
                        _logger.info("Getir cron - yeni sipariş oluşturuldu: %s", gid)
                    except Exception as e:
                        _logger.error("Getir cron - sipariş hatası (ID: %s): %s", gid, e)
                        
            except Exception as e:
                _logger.error("Getir cron - API hatası (%s): %s", api.name, e)

    # -------------------------------------------
    # RESTAURANT STATUS
    # -------------------------------------------
    def set_restaurant_busy(self, duration: int):
        """
        Yoğunluk modu aç - teslimat süresini artır.
        duration: 15, 30 veya 45 dakika
        """
        if duration not in (15, 30, 45):
            raise UserError("Yoğunluk süresi 15, 30 veya 45 dakika olmalı.")
        return self.call("PUT", "/restaurants/delivery-duration/busyness", json_data={
            "isBusy": True,
            "busynessDifferenceDuration": duration,
        })

    def clear_restaurant_busy(self):
        """Yoğunluk modunu kapat"""
        return self.call("PUT", "/restaurants/delivery-duration/busyness", json_data={
            "isBusy": False,
        })

    def close_restaurant_temporarily(self, minutes: int):
        """
        Restoranı geçici olarak kapat.
        minutes: 15, 30 veya 45 dakika
        """
        if minutes not in (15, 30, 45):
            raise UserError("Kapama süresi 15, 30 veya 45 dakika olmalı.")
        return self.call("PUT", "/restaurants/status/close", json_data={
            "timeOffAmount": minutes,
        })

    def disable_courier_temporarily(self, minutes: int):
        """
        Restoran kurye hizmetini geçici olarak kapat.
        minutes: 15, 30 veya 45 dakika
        """
        if minutes not in (15, 30, 45):
            raise UserError("Kapama süresi 15, 30 veya 45 dakika olmalı.")
        return self.call("POST", "/restaurants/courier/disable", json_data={
            "timeOffAmount": minutes,
        })

    # Action buttons for views
    def action_set_busy_15(self):
        self.set_restaurant_busy(15)
        return self._notify("Yoğunluk", "+15 dk yoğunluk eklendi.")

    def action_set_busy_30(self):
        self.set_restaurant_busy(30)
        return self._notify("Yoğunluk", "+30 dk yoğunluk eklendi.")

    def action_set_busy_45(self):
        self.set_restaurant_busy(45)
        return self._notify("Yoğunluk", "+45 dk yoğunluk eklendi.")

    def action_clear_busy(self):
        self.clear_restaurant_busy()
        return self._notify("Yoğunluk", "Yoğunluk modu kapatıldı.")

    def action_close_15(self):
        self.close_restaurant_temporarily(15)
        return self._notify("Restoran", "15 dakika kapatıldı.")

    def action_close_30(self):
        self.close_restaurant_temporarily(30)
        return self._notify("Restoran", "30 dakika kapatıldı.")

    def action_close_45(self):
        self.close_restaurant_temporarily(45)
        return self._notify("Restoran", "45 dakika kapatıldı.")

    def _notify(self, title, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": title, "message": message, "type": "success"},
        }

    # -------------------------------------------
    # PRODUCT STATUS
    # -------------------------------------------
    def get_product_status(self, product_id: str):
        """Ürün durumunu sorgula"""
        return self.call("GET", f"/products/{product_id}/status")

    def set_product_status(self, product_id: str, active: bool):
        """Ürün durumunu güncelle"""
        return self.call("PUT", f"/products/{product_id}/status", json_data={
            "isActive": active,
        })

    def get_product_status_by_chain(self, chain_product_id: str):
        """Zincir ürün durumunu sorgula"""
        return self.call("GET", f"/products/chain-id/{chain_product_id}/status")

    def set_product_status_by_chain(self, chain_product_id: str, active: bool):
        """Zincir ürün durumunu güncelle"""
        return self.call("PUT", f"/products/chain-id/{chain_product_id}/status", json_data={
            "isActive": active,
        })

    def activate_option_product(self, option_id: str):
        """Opsiyon ürünü aktif et"""
        return self.call("POST", f"/products/option-products/{option_id}/activate-as-option")

    def inactivate_option_product(self, option_id: str):
        """Opsiyon ürünü pasif et"""
        return self.call("POST", f"/products/option-products/{option_id}/inactivate-as-option")

    # -------------------------------------------
    # ZONES
    # -------------------------------------------
    def get_zones(self):
        """Teslimat bölgelerini getir"""
        return self.call("GET", "/restaurants/zones")

    def get_zone_etas(self):
        """ETA değerlerini getir"""
        return self.call("GET", "/restaurants/zones/eta")

    def update_zone(self, restaurant_id: str, zone_id: str, eta_id: str = None, min_basket_size: float = None):
        """Zone ETA ve minimum sepet tutarını güncelle"""
        payload = {}
        if eta_id:
            payload["eta"] = eta_id
        if min_basket_size is not None:
            payload["minBasketSize"] = min_basket_size
        return self.call("PUT", f"/restaurants/{restaurant_id}/zones/{zone_id}", json_data=payload)

    def activate_zone(self, zone_id: str):
        """Bölgeyi aktif et"""
        return self.call("PUT", f"/restaurants/zones/{zone_id}/active")

    def inactivate_zone(self, zone_id: str):
        """Bölgeyi pasif et"""
        return self.call("PUT", f"/restaurants/zones/{zone_id}/inactive")

    # -------------------------------------------
    # INVOICE
    # -------------------------------------------
    def upload_invoice(self, order_id: str, file_content, filename: str):
        """Fiş/fatura yükle"""
        self._ensure_token()
        
        # Apply rate limiting
        rate_limiter = get_rate_limiter()
        rate_limiter.acquire(f"/food-orders/{order_id}/invoice")
        
        url = f"{self.api_url}/food-orders/{order_id}/invoice"
        headers = {"Authorization": f"Bearer {self.token}"}
        files = {"file": (filename, file_content)}
        
        res = requests.post(url, headers=headers, files=files, timeout=30)
        self.env["getir.log"].create_log(f"/food-orders/{order_id}/invoice", {"filename": filename}, res.text, res.status_code, method="POST")
        
        if res.status_code >= 400:
            raise UserError(f"Fatura yükleme hatası: {res.text}")
        return res.json()

    def get_invoice(self, order_id: str):
        """Fatura durumunu sorgula"""
        return self.call("GET", f"/food-orders/{order_id}/invoice")

    def delete_invoice(self, order_id: str):
        """Faturayı sil"""
        return self.call("DELETE", f"/food-orders/{order_id}/invoice")

    # -------------------------------------------
    # REVIEWS
    # -------------------------------------------
    def get_reviews(self, start_date: str, end_date: str, page: int = 1, page_size: int = 20):
        """Sipariş değerlendirmelerini getir"""
        params = {
            "startDate": start_date,
            "endDate": end_date,
            "page": page,
            "pageSize": page_size,
        }
        return self.call("GET", "/restaurants/reviews", params=params)

    # -------------------------------------------
    # MENU
    # -------------------------------------------
    def get_restaurant_menu(self):
        """Restoran menüsünü getir"""
        return self.call("GET", "/restaurants/menu")

    def get_payment_methods(self):
        """Ödeme yöntemlerini getir"""
        return self.call("GET", "/payment-methods")
    # -------------------------------------------