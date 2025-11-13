import requests
from odoo import models, fields
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class GetirAPI(models.Model):
    _name = "getir.api"
    _description = "Getir Yemek API"

    name = fields.Char(default="Getir API", required=True)
    api_url = fields.Char(
        default="https://food-external-api-gateway.development.getirapi.com",
        string="API URL"
    )
    app_secret_key = fields.Char(required=True, string="App Secret Key")
    restaurant_secret_key = fields.Char(required=True, string="Restaurant Secret Key")
    token = fields.Char(string="Access Token", readonly=True)

    # LOGIN & TOKEN
    def action_login(self):
        """Getir API Login"""
        url = f"{self.api_url}/auth/login"
        payload = {
            "appSecretKey": self.app_secret_key,
            "restaurantSecretKey": self.restaurant_secret_key,
        }
        headers = {"Content-Type": "application/json"}
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code != 200:
            raise UserError(f"Login failed! {res.status_code} - {res.text}")
        data = res.json()
        self.token = data.get("token") or data.get("data", {}).get("token")
        _logger.info("Getir token alındı: %s", self.token)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Getir API", "message": "Token başarıyla alındı.", "type": "success"},
        }

    def _auth_headers(self):
        if not self.token:
            self.action_login()
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    # POS AKTİF ET
    def activate_pos_status(self):
        url = f"{self.api_url}/restaurants/pos-status"
        payload = {
            "posStatus": 100,
            "appSecretKey": self.app_secret_key,
            "restaurantSecretKey": self.restaurant_secret_key
        }
        res = requests.put(url, json=payload, timeout=10)
        if res.status_code != 200:
            raise UserError(f"POS aktivasyon hatası: {res.status_code} - {res.text}")
        _logger.info("POS status aktif edildi (100).")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Getir POS", "message": "POS başarıyla aktif edildi.", "type": "success"},
        }

    # STATUS UPDATE
    def update_order_status(self, order_id, status_endpoint):
        """Odoo'dan Getir'e sipariş durumu gönder"""
        headers = self._auth_headers()
        url = f"{self.api_url}/food-orders/{order_id}/{status_endpoint}"
        res = requests.post(url, headers=headers, timeout=15)
        if res.status_code != 200:
            raise UserError(f"Status update failed: {res.status_code} - {res.text}")
        _logger.info("Getir order %s status updated via %s", order_id, status_endpoint)
        return True

    # POS ORDER OLUŞTURMA
    def _create_pos_order_from_getir(self, payload):
        """Getir JSON siparişini Odoo POS Order olarak kaydet"""
        client = payload.get("client", {})
        products = payload.get("products", [])
        order_id = payload.get("id")

        # Müşteri
        partner = self.env["res.partner"].sudo().search(
            [("phone", "=", client.get("contactPhoneNumber"))], limit=1
        )
        if not partner:
            partner = self.env["res.partner"].sudo().create({
                "name": client.get("name") or "Getir Müşteri",
                "phone": client.get("contactPhoneNumber"),
                "street": client.get("deliveryAddress", {}).get("address"),
                "city": client.get("deliveryAddress", {}).get("city"),
            })

        # Getir POS config bul
        pos_config = self.env["pos.config"].sudo().search([("name", "ilike", "getir")], limit=1)
        if not pos_config:
            raise UserError("Getir POS bulunamadı. Lütfen 'Getir Restoranı' adlı bir POS oluşturun.")

        # Açık session
        pos_session = self.env["pos.session"].sudo().search([
            ("config_id", "=", pos_config.id),
            ("state", "=", "opened")
        ], limit=1)
        if not pos_session:
            raise UserError("Getir POS oturumu açık değil.")

        # Satırları hazırla
        lines = []
        for p in products:
            name = p.get("product") or (p.get("name") or {}).get("tr")
            qty = p.get("count", 1)
            price = p.get("priceWithOption") or p.get("price") or 0.0

            product = self.env["product.product"].sudo().search(
                [("name", "ilike", name)], limit=1
            )
            if not product:
                product = self.env["product.product"].sudo().create({
                    "name": name,
                    "list_price": price,
                })

            lines.append((0, 0, {
                "product_id": product.id,
                "qty": qty,
                "price_unit": price,
            }))

        # Getir floor/table
        getir_table = self.env["pos.order"].sudo().create_getir_floor_and_table()

        # POS order oluştur
        pos_order = self.env["pos.order"].sudo().create({
            "session_id": pos_session.id,
            "partner_id": partner.id,
            "pos_reference": f"Getir-{order_id}",
            "lines": lines,
            "is_getir_order": True,
            "table_id": getir_table.id,
        })

        _logger.info("Yeni Getir siparişi oluşturuldu: %s", order_id)
        return pos_order
