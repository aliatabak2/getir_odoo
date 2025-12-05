import json
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GetirOrder(models.Model):
    _name = "getir.order"
    _description = "Getir Food Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(string="Order Ref", required=True, index=True)
    getir_id = fields.Char(string="Getir Order ID", index=True)
    status = fields.Char(string="Status Raw")
    delivery_type = fields.Integer(string="Delivery Type")
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

    # State Management
    state = fields.Selection([
        ("new", "Yeni"),
        ("verified", "Onaylandı"),
        ("preparing", "Hazırlanıyor"),
        ("ready", "Hazır"),
        ("handed_over", "Kuryeye Teslim"),
        ("delivered", "Teslim Edildi"),
        ("cancelled", "İptal"),
    ], string="Durum", default="new", tracking=True)

    # Timestamps
    verified_at = fields.Datetime(string="Onay Zamanı")
    prepared_at = fields.Datetime(string="Hazırlık Zamanı")
    handover_at = fields.Datetime(string="Kurye Teslim Zamanı")
    delivered_at = fields.Datetime(string="Müşteri Teslim Zamanı")
    cancelled_at = fields.Datetime(string="İptal Zamanı")

    # Cancel
    cancel_reason_id = fields.Many2one("getir.cancel.reason", string="İptal Sebebi")
    cancel_note = fields.Text(string="İptal Notu")

    # Getir status code from API
    getir_status_code = fields.Integer(string="Getir Status Code", help="325=İleri tarihli, 400=Yeni, 350=Onaylı, 500=Hazırlanıyor")

    # -------------------------------------------------------------
    # CREATE FROM PAYLOAD
    # -------------------------------------------------------------
    @api.model
    def create_from_payload(self, payload):
        if not payload:
            raise UserError("Getir payload boş geldi.")

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
            "payment_method_text": payment_method_text,
            "customer_name": client.get("name"),
            "customer_phone": client.get("contactPhoneNumber"),
            "customer_note": payload.get("note"),
            "address_text": delivery_address.get("address"),
            "address_city": delivery_address.get("city"),
            "address_lat": delivery_address.get("lat") or 0.0,
            "address_lng": delivery_address.get("lng") or 0.0,
            "raw_payload": json.dumps(payload, ensure_ascii=False),
        }

        # Create getir.order
        getir_order = self.create(order_vals)

        # POS order create
        pos_order = getir_order._create_pos_order_from_getir(payload)
        getir_order.pos_order_id = pos_order.id

        return getir_order

    # -------------------------------------------------------------
    # POS ORDER CREATE
    # -------------------------------------------------------------
    def _create_pos_order_from_getir(self, payload):
        self.ensure_one()
        env = self.env

        getir_order = self
        client = payload.get("client", {}) or {}
        products = payload.get("products", []) or []

        # CUSTOMER
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

        # POS CONFIG
        pos_config = env["pos.config"].sudo().search([("name", "ilike", "getir")], limit=1)
        if not pos_config:
            raise UserError("Getir POS bulunamadı. Adında 'Getir' geçen bir POS config oluşturun.")

        pos_session = env["pos.session"].sudo().search([
            ("config_id", "=", pos_config.id),
            ("state", "=", "opened")
        ], limit=1)
        if not pos_session:
            raise UserError("Getir POS oturumu açık değil.")

        # TABLE
        table = env["pos.order"].sudo().create_getir_floor_and_table()

        # LINES
        
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

            # NOTE oluştur
            line_note_parts = []
            for opt in p.get("options", []) or []:
                opt_name = opt.get("name") or ""
                if isinstance(opt_name, dict):
                    opt_name = opt_name.get("tr") or opt_name.get("en") or ""
                if opt_name:
                    line_note_parts.append(opt_name)

            note = ", ".join(line_note_parts) if line_note_parts else False

            # Zorunlu Odoo18 POS alanları
            line_vals = {
                "product_id": product.id,
                "qty": qty,
                "price_unit": price,
                "price_subtotal": qty * price,
                "price_subtotal_incl": qty * price,
            }

            if note:
                line_vals["note"] = note

            lines.append((0, 0, line_vals))

        # POS ORDER
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

        # PAYMENT
        payment_method = self._find_pos_payment_method(pos_order, getir_order.payment_method)
        env["pos.payment"].sudo().create({
            "pos_order_id": pos_order.id,
            "payment_method_id": payment_method.id,
            "amount": getir_order.total_discounted_price or pos_order.amount_total,
        })

        _logger.info("Getir siparişi POS'a oluşturuldu: %s", getir_order.name)
        return pos_order

    # -------------------------------------------------------------
    # PAYMENT METHOD MAP
    # -------------------------------------------------------------
    def _map_payment_method(self, payment_method_id: int):
        if payment_method_id in (3, 1, 26):
            return "card"
        if payment_method_id == 4:
            return "cash"
        return "other"

    # -------------------------------------------------------------
    # PAYMENT METHOD FIND
    # -------------------------------------------------------------
    def _find_pos_payment_method(self, pos_order, payment_method_id: int):
        env = self.env
        company = pos_order.company_id

        if payment_method_id in (3, 1, 26):
            pm = env["pos.payment.method"].sudo().search([
                ("name", "ilike", "kart"),
                ("company_id", "=", company.id),
            ], limit=1)
            if pm:
                return pm

        if payment_method_id == 4:
            pm = env["pos.payment.method"].sudo().search([
                ("is_cash_count", "=", True),
                ("company_id", "=", company.id),
            ], limit=1)
            if pm:
                return pm

        pm = env["pos.payment.method"].sudo().search([
            ("is_cash_count", "=", True),
            ("company_id", "=", company.id),
        ], limit=1)
        if not pm:
            raise UserError("Getir ödemesi için uygun POS ödeme yöntemi bulunamadı.")

        return pm

    # -------------------------------------------------------------
    # ORDER ACTIONS
    # -------------------------------------------------------------
    def _get_api(self):
        """Aktif Getir API config'ini döndür"""
        api = self.env["getir.api"].sudo().search([("active", "=", True)], limit=1)
        if not api:
            raise UserError("Aktif Getir API yapılandırması bulunamadı.")
        return api

    def action_verify(self):
        """Siparişi onayla - Getir'e bildir"""
        self.ensure_one()
        if self.state != "new":
            raise UserError("Sadece yeni siparişler onaylanabilir.")

        api = self._get_api()
        
        # İleri tarihli mi kontrol et
        if self.is_scheduled or self.getir_status_code == 325:
            api.verify_scheduled_order(self.getir_id)
        else:
            api.verify_order(self.getir_id)

        self.write({
            "state": "verified",
            "verified_at": fields.Datetime.now(),
        })

        return self._notify("Sipariş Onaylandı", f"{self.name} siparişi Getir'e onaylandı.")

    def action_prepare(self):
        """Siparişi hazırlanıyor olarak işaretle"""
        self.ensure_one()
        if self.state not in ("verified", "new"):
            raise UserError("Sipariş önce onaylanmalı.")

        api = self._get_api()
        api.prepare_order(self.getir_id)

        self.write({
            "state": "preparing",
            "prepared_at": fields.Datetime.now(),
        })

        return self._notify("Hazırlanıyor", f"{self.name} siparişi hazırlanıyor.")

    def action_ready(self):
        """Sipariş hazır - kuryeye teslim bekliyor"""
        self.ensure_one()
        if self.state != "preparing":
            raise UserError("Sipariş önce hazırlanmalı.")

        self.write({
            "state": "ready",
        })

        return self._notify("Hazır", f"{self.name} siparişi hazır, kurye bekleniyor.")

    def action_handover(self):
        """Siparişi Getir kuryesine teslim et (deliveryType: 1)"""
        self.ensure_one()
        if self.state not in ("preparing", "ready"):
            raise UserError("Sipariş önce hazırlanmalı.")

        if self.delivery_type != 1:
            raise UserError("Bu sipariş Getir kuryesi tarafından teslim edilmiyor. action_deliver kullanın.")

        api = self._get_api()
        api.handover_order(self.getir_id)

        self.write({
            "state": "handed_over",
            "handover_at": fields.Datetime.now(),
        })

        return self._notify("Kuryeye Teslim", f"{self.name} siparişi Getir kuryesine teslim edildi.")

    def action_deliver(self):
        """Siparişi müşteriye teslim et (deliveryType: 2 - restoran kurye)"""
        self.ensure_one()
        if self.state not in ("preparing", "ready", "handed_over"):
            raise UserError("Sipariş teslim edilebilir durumda değil.")

        # Restoran kuryesi ise deliver, Getir kuryesi ise zaten handover yapılmış olmalı
        if self.delivery_type == 2:
            api = self._get_api()
            api.deliver_order(self.getir_id)

        self.write({
            "state": "delivered",
            "delivered_at": fields.Datetime.now(),
        })

        return self._notify("Teslim Edildi", f"{self.name} siparişi müşteriye teslim edildi.")

    def action_cancel(self):
        """İptal wizard'ını aç"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Sipariş İptali",
            "res_model": "getir.order.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def do_cancel(self, reason_id, note="", product_id=None):
        """Siparişi iptal et"""
        self.ensure_one()
        
        api = self._get_api()
        reason = self.env["getir.cancel.reason"].browse(reason_id)
        
        api.cancel_order_by_restaurant(
            self.getir_id,
            reason.getir_reason_id,
            note,
            product_id
        )

        self.write({
            "state": "cancelled",
            "cancelled_at": fields.Datetime.now(),
            "cancel_reason_id": reason_id,
            "cancel_note": note,
        })

        # POS siparişini de iptal et
        if self.pos_order_id:
            self.pos_order_id.sudo().write({"state": "cancel"})

        return self._notify("İptal Edildi", f"{self.name} siparişi iptal edildi.")

    def _notify(self, title, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": title, "message": message, "type": "success"},
        }

    # -------------------------------------------------------------
    # AUTO VERIFY (Opsiyonel - webhook'tan çağrılabilir)
    # -------------------------------------------------------------
    def auto_verify_if_enabled(self):
        """Config'de otomatik onay açıksa siparişi onayla"""
        auto_verify = self.env["ir.config_parameter"].sudo().get_param("getir.auto_verify", "False")
        if auto_verify.lower() == "true":
            try:
                self.action_verify()
            except Exception as e:
                _logger.error("Auto verify failed for %s: %s", self.name, e)
