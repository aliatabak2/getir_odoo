from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    is_getir_order = fields.Boolean(string="Getir Order", default=False, copy=False)
    getir_order_id = fields.Many2one("getir.order", string="Getir Order Ref")

    getir_payment_type = fields.Selection([
        ("card", "Card"),
        ("cash", "Cash"),
        ("other", "Other"),
    ], string="Getir Payment Type")

    getir_note = fields.Text(string="Getir Note")
    getir_lat = fields.Float(string="Lat")
    getir_lng = fields.Float(string="Lng")
    getir_address = fields.Char(string="Delivery Address")

    getir_total_price = fields.Float(string="Getir Total Price")
    getir_total_discounted_price = fields.Float(string="Getir Discounted Total")
    getir_discount = fields.Float(string="Getir Discount Amount")

    getir_delivery_type = fields.Selection([
        ("1", "Getir Courier"),
        ("2", "Restaurant Courier"),
        ("0", "Unknown"),
    ], string="Getir Delivery Type", default="0")

    @api.model
    def create_getir_floor_and_table(self):
        """
        Getir siparişleri için tek bir floor + tek bir masa üretir / bulur.
        Odoo 18'de mevcut model isimleri:
            - restaurant.floor
            - restaurant.table
        """
        Floor = self.env["restaurant.floor"].sudo()
        Table = self.env["restaurant.table"].sudo()

        # 1) Floor'u bul / oluştur
        floor = Floor.search([("name", "=", "Getir")], limit=1)
        if not floor:
            floor = Floor.create({
                "name": "Getir",
                "sequence": 50,
                "active": True,
            })
            _logger.info("Getir floor oluşturuldu: %s", floor.id)

        # 2) Masa'yı bul / oluştur
        table = Table.search([
            ("floor_id", "=", floor.id),
            ("table_number", "=", 999)
        ], limit=1)

        if not table:
            vals = {
                "table_number": 999,
                "seats": 1,
                "active": True,
                "shape": "square",
                "width": 120,
                "height": 120,
                "position_h": 200,
                "position_v": 200,
                "color": "#8e44ad",
                "floor_id": floor.id,
            }
            table = Table.create(vals)
            _logger.info("Getir table oluşturuldu: %s", table.id)

        return table

    @api.model_create_multi
    def create(self, vals_list):
        # Amount alanlarını NULL gitmesin diye doldur
        for vals in vals_list:
            if "amount_total" not in vals:
                total = 0.0
                for line_cmd in vals.get("lines", []):
                    if line_cmd[0] == 0:
                        line_vals = line_cmd[2]
                        total += line_vals.get("qty", 0.0) * line_vals.get("price_unit", 0.0)
                vals["amount_total"] = total
            if "amount_tax" not in vals:
                vals["amount_tax"] = 0.0
            if "amount_paid" not in vals:
                vals["amount_paid"] = vals.get("amount_total", 0.0)
            if "amount_return" not in vals:
                vals["amount_return"] = 0.0
        return super().create(vals_list)
