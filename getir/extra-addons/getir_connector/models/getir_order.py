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
