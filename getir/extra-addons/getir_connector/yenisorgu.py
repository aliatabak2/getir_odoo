controllers:
getir_webhook.py
from odoo import http
from odoo.http import request
import logging
import json
print("### webhook görünüyo ###")

_logger = logging.getLogger(__name__)

class GetirTest(http.Controller):
    @http.route('/getir/test', auth='public')
    def test(self):
        return "GETIR ROUTE ÇALIŞTI"

class GetirWebhook(http.Controller):

    @http.route('/getir/newOrder', type='json', auth='public', csrf=False, methods=['POST'])
    def new_order_long(self, **kw):
        return self._new_order_handler()

    @http.route('/newOrder', type='json', auth='public', csrf=False, methods=['POST'])
    def new_order_short(self, **kw):
        return self._new_order_handler()

    def _new_order_handler(self):
        print("### NEW ORDER ROUTE ÇALIŞTI ###")
        payload = request.jsonrequest or {}
        return {"ok": True}
                    #
                    #   tail -f var/log/odoo/odoo.log
                    #
    # ----------------------------------------------------------------------
    # 🟣 SİPARİŞ İPTAL / CANCEL
    # ----------------------------------------------------------------------
    @http.route(['/getir/cancelOrder', '/cancelOrder'], type='json', auth='public', csrf=False, methods=['POST'])
    def cancel_order(self):
        payload = request.jsonrequest or {}
        _logger.info("GETIR CANCEL ORDER PAYLOAD: %s", payload)

        order_id = str(payload.get("id") or payload.get("orderId"))
        if not order_id:
            return {"success": False, "error": "orderId bulunamadı."}

        getir_ref = f"Getir-{order_id}"

        getir_order = request.env["getir.order"].sudo().search([
            ("name", "=", getir_ref)
        ], limit=1)

        if not getir_order:
            return {"success": False, "error": "Sipariş bulunamadı"}

        # POS siparişi iptal et
        if getir_order.pos_order_id:
            getir_order.pos_order_id.sudo().write({"state": "cancel"})

        # Getir tarafına iptal sebebi iletilecek endpoint: /food-orders/{id}/cancel
        # Biz burada sadece kaydediyoruz
        getir_order.status = "cancelled"

        return {"success": True, "message": "İptal işlendi."}

    # ----------------------------------------------------------------------
    # 🟣 KURYE DURUMU
    # ----------------------------------------------------------------------
    @http.route(['/getir/courier', '/courier'], type='json', auth='public', csrf=False, methods=['POST'])
    def courier(self):
        payload = request.jsonrequest or {}
        _logger.info("GETIR COURIER STATUS: %s", payload)

        # Beklenen format:
        # {
        #   "orderId": "",
        #   "courierStatus": 450
        # }

        order_id = str(payload.get("orderId"))
        courier_status = payload.get("courierStatus")

        getir_order = request.env["getir.order"].sudo().search([
            ("getir_id", "=", order_id)
        ], limit=1)

        if getir_order:
            getir_order.status = f"courier:{courier_status}"

        return {"success": True}

    # ----------------------------------------------------------------------
    # 🟣 RESTORAN DURUMU (open/close)
    # ----------------------------------------------------------------------
    @http.route(['/getir/restaurant', '/restaurant'], type='json', auth='public', csrf=False, methods=['POST'])
    def restaurant(self):
        payload = request.jsonrequest or {}
        _logger.info("GETIR RESTAURANT STATUS PAYLOAD: %s", payload)

        # Örn: {"status": 100} = açık, 200 = kapalı
        return {"success": True}


models:

getir_api.py

import requests
import json
import logging
from datetime import datetime, timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError

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

    # -------------------------------------------
    # LOGIN
    # -------------------------------------------
    def action_login(self):
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

        url = f"{self.api_url}{endpoint}"

        hdrs = {
            "Authorization": f"Bearer {self.token}",
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

    getir_log.py

    import json
from odoo import models, fields, api


class GetirLog(models.Model):
    _name = "getir.log"
    _description = "Getir API Log"
    _order = "create_date desc"

    name = fields.Char(string="Name", default="/", required=True)
    endpoint = fields.Char(string="Endpoint")
    method = fields.Char(string="HTTP Method")
    request_payload = fields.Text(string="Request Payload")
    response_payload = fields.Text(string="Response Payload")
    http_status = fields.Integer(string="HTTP Status")
    success = fields.Boolean(default=False)
    error_message = fields.Char(string="Error")

    order_id = fields.Many2one("getir.order", string="Getir Order")

    @api.model
    def create_log(self, endpoint, request_data, response_data, http_status=None, method=None, order=None, error=None):
        """Helper - GetirAPI.call burayı kullanacak."""
        if isinstance(request_data, (dict, list)):
            request_data = json.dumps(request_data, ensure_ascii=False, indent=2)
        if isinstance(response_data, (dict, list)):
            response_data = json.dumps(response_data, ensure_ascii=False, indent=2)

        vals = {
            "name": endpoint or "/",
            "endpoint": endpoint or "",
            "method": method or "",
            "request_payload": request_data or "",
            "response_payload": response_data or "",
            "http_status": http_status or 0,
            "success": http_status is not None and http_status < 400,
            "error_message": error or "",
            "order_id": order.id if order else False,
        }
        return self.create(vals)

getir_order.py

import json
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GetirOrder(models.Model):
    _name = "getir.order"
    _description = "Getir Food Order"

    name = fields.Char(string="Order Ref", required=True, index=True)
    getir_id = fields.Char(string="Getir Order ID", index=True)
    status = fields.Char(string="Status Raw")
    delivery_type = fields.Integer(string="Delivery Type")  # 1: Getir, 2: Restaurant courier
    is_scheduled = fields.Boolean(string="Scheduled")
    scheduled_date = fields.Datetime(string="Scheduled Date")
    total_price = fields.Float(string="Total Price")
    total_discounted_price = fields.Float(string="Discounted Total")
    total_discount_amount = fields.Float(string="Total Discount Amount")
    supplier_support_rate = fields.Float(string="Supplier Support Rate")

    payment_method = fields.Integer(string="Payment Method (Getir ID)")
    payment_method_text = fields.Char(string="Payment Method Text")

    customer_name = fields.Char()
    customer_phone = fields.Char()
    customer_note = fields.Text()
    address_text = fields.Char()
    address_city = fields.Char()
    address_lat = fields.Float()
    address_lng = fields.Float()

    raw_payload = fields.Text(string="Raw JSON Payload")

    pos_order_id = fields.Many2one("pos.order", string="POS Order")

    @api.model
    def create_from_payload(self, payload):
        """Getir webhook payload → getir.order + POS order oluşturur."""

        if not payload:
            raise UserError("Getir payload boş geldi.")

        # Temel alanlar
        gid = str(payload.get("id") or payload.get("_id") or "")
        if not gid:
            raise UserError("Getir Order ID bulunamadı.")

        client = payload.get("client", {}) or {}
        delivery_address = client.get("deliveryAddress", {}) or {}

        total_price = payload.get("totalPrice") or 0.0
        total_discounted = payload.get("totalDiscountedPrice") or total_price
        total_discount_amount = payload.get("totalDiscountAmount") or 0.0
        supplier_support_rate = payload.get("supplierSupportRate") or 0.0

        payment_method = payload.get("paymentMethod")
        payment_method_text = ""
        if isinstance(payload.get("paymentMethodText"), dict):
            payment_method_text = payload["paymentMethodText"].get("tr") or payload["paymentMethodText"].get("en")

        # getir.order kaydı
        order_vals = {
            "name": f"Getir-{gid}",
            "getir_id": gid,
            "status": str(payload.get("status") or ""),
            "delivery_type": payload.get("deliveryType") or 0,
            "is_scheduled": bool(payload.get("isScheduled")),
            "scheduled_date": payload.get("scheduledDate") or False,
            "total_price": total_price,
            "total_discounted_price": total_discounted,
            "total_discount_amount": total_discount_amount,
            "supplier_support_rate": supplier_support_rate,
            "payment_method": payment_method or 0,
            "payment_method_text": payment_method_text or "",
            "customer_name": client.get("name"),
            "customer_phone": client.get("contactPhoneNumber"),
            "customer_note": payload.get("note"),
            "address_text": delivery_address.get("address"),
            "address_city": delivery_address.get("city"),
            "address_lat": delivery_address.get("lat") or 0.0,
            "address_lng": delivery_address.get("lng") or 0.0,
            "raw_payload": json.dumps(payload, ensure_ascii=False),
        }

        getir_order = self.create(order_vals)

        # POS order oluştur
        pos_order = self._create_pos_order_from_getir(getir_order, payload)
        getir_order.pos_order_id = pos_order.id

        return getir_order

    # ------------------------------------------------------------------
    # POS ORDER OLUŞTURMA (Getir payload → pos.order)
    # ------------------------------------------------------------------
    def _create_pos_order_from_getir(self, getir_order, payload):
        self.ensure_one()
        env = self.env

        client = payload.get("client", {}) or {}
        products = payload.get("products", []) or []

        # === MÜŞTERİ ===
        partner = env["res.partner"].sudo().search(
            [("phone", "=", client.get("contactPhoneNumber"))],
            limit=1,
        )
        if not partner:
            delivery_address = client.get("deliveryAddress", {}) or {}
            partner = env["res.partner"].sudo().create({
                "name": client.get("name") or "Getir Müşteri",
                "phone": client.get("contactPhoneNumber"),
                "street": delivery_address.get("address"),
                "city": delivery_address.get("city"),
            })

        # === POS CONFIG ===
        pos_config = env["pos.config"].sudo().search([("name", "ilike", "getir")], limit=1)
        if not pos_config:
            raise UserError("Getir POS bulunamadı. Lütfen adında 'Getir' geçen bir POS config oluşturun.")

        pos_session = env["pos.session"].sudo().search([
            ("config_id", "=", pos_config.id),
            ("state", "=", "opened")
        ], limit=1)
        if not pos_session:
            raise UserError("Getir POS oturumu açık değil.")

        # === MASA ===
        table = env["pos.order"].sudo().create_getir_floor_and_table()

        # === LİNELAR ===
        lines = []
        for p in products:
            prod_name = None
            if isinstance(p.get("product"), dict):
                prod_name = p["product"].get("name", {}).get("tr") or p["product"].get("name", {}).get("en")
            else:
                prod_name = p.get("product") or (p.get("name") or {}).get("tr")

            qty = p.get("count", 1)
            price = p.get("priceWithOption") or p.get("price") or 0.0

            product = env["product.product"].sudo().search(
                [("name", "ilike", prod_name)],
                limit=1,
            )
            if not product:
                product = env["product.product"].sudo().create({
                    "name": prod_name,
                    "list_price": price,
                })

            line_note_parts = []
            # seçenekleri nota yaz
            for opt in p.get("options", []) or []:
                opt_name = opt.get("name") or ""
                if isinstance(opt_name, dict):
                    opt_name = opt_name.get("tr") or opt_name.get("en") or ""
                if opt_name:
                    line_note_parts.append(opt_name)

            note = ", ".join(line_note_parts) if line_note_parts else False

            line_vals = {
                "product_id": product.id,
                "qty": qty,
                "price_unit": price,
            }
            if note:
                line_vals["note"] = note

            lines.append((0, 0, line_vals))

        # === POS ORDER VALS ===
        pos_vals = {
            "session_id": pos_session.id,
            "partner_id": partner.id,
            "pos_reference": getir_order.name,
            "lines": lines,
            "table_id": table.id if table else False,
            "is_getir_order": True,
            "getir_order_id": getir_order.id,
            "getir_payment_type": self._map_payment_method(getir_order.payment_method),
            "getir_note": getir_order.customer_note,
            "getir_lat": getir_order.address_lat,
            "getir_lng": getir_order.address_lng,
            "getir_address": getir_order.address_text,
            "getir_total_price": getir_order.total_price,
            "getir_total_discounted_price": getir_order.total_discounted_price,
            "getir_discount": getir_order.total_discount_amount,
            "getir_delivery_type": str(getir_order.delivery_type),
        }

        pos_order = env["pos.order"].sudo().create(pos_vals)

        # === ÖDEME OLUŞTUR ===
        payment_method = self._find_pos_payment_method(pos_order, getir_order.payment_method)
        env["pos.payment"].sudo().create({
            "pos_order_id": pos_order.id,
            "payment_method_id": payment_method.id,
            "amount": getir_order.total_discounted_price or pos_order.amount_total,
        })

        _logger.info("Getir siparişi POS'a oluşturuldu: %s", getir_order.name)
        return pos_order

    # ------------------------------------------------------------------
    # Payment Method mapping
    # ------------------------------------------------------------------
    def _map_payment_method(self, payment_method_id: int):
        """Getir paymentMethod id → internal code (selection string)."""
        if payment_method_id in (3, 1, 26):  # Kart / Online Payment / MasterPass
            return "card"
        if payment_method_id == 4:  # Nakit
            return "cash"
        return "other"

    def _find_pos_payment_method(self, pos_order, payment_method_id: int):
        env = self.env
        company = pos_order.company_id

        # Kart
        if payment_method_id in (3, 1, 26):
            pm = env["pos.payment.method"].sudo().search([
                ("name", "ilike", "kart"),
                ("company_id", "=", company.id),
            ], limit=1)
            if pm:
                return pm

        # Nakit
        if payment_method_id == 4:
            pm = env["pos.payment.method"].sudo().search([
                ("is_cash_count", "=", True),
                ("company_id", "=", company.id),
            ], limit=1)
            if pm:
                return pm

        # Fallback: ilk cash method
        pm = env["pos.payment.method"].sudo().search([
            ("is_cash_count", "=", True),
            ("company_id", "=", company.id),
        ], limit=1)
        if not pm:
            raise UserError("Getir ödemesi için uygun POS ödeme yöntemi bulunamadı.")
        return pm

getir_product_map.py
from odoo import models, fields


class GetirProductMap(models.Model):
    _name = "getir.product.map"
    _description = "Getir Product ↔ Odoo Product Mapping"

    name = fields.Char(required=True)
    getir_product_id = fields.Char(string="Getir Product ID", required=True, index=True)
    getir_chain_product_id = fields.Char(string="Getir Chain Product ID")
    product_id = fields.Many2one("product.product", required=True)
    active = fields.Boolean(default=True)

getir_order_init.py