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
        Odoo 18 için floor/table oluşturma.
        Masa numarası (table_number) zorunlu olduğu için 999 kullanıyoruz.
        """
        env = self.env
        Floor = env["restaurant.floor"]
        Table = env["restaurant.table"]

        getir_floor = None
        getir_table = None

        try:
            getir_floor = Floor.search([("name", "=", "Getir")], limit=1)
            if not getir_floor:
                getir_floor = Floor.create({
                    "name": "Getir",
                    "sequence": 50,
                    "active": True,
                })
                _logger.info("Getir floor oluşturuldu: %s", getir_floor.id)
        except Exception as e:
            _logger.error("Getir floor oluşturulurken hata: %s", e)

        try:
            getir_table = Table.search([("table_number", "=", 999)], limit=1)
            if not getir_table:
                vals = {
                    "table_number": 999,
                    "seats": 0,
                    "active": True,
                    "shape": "square",
                    "width": 120,
                    "height": 120,
                    "position_h": 200,
                    "position_v": 200,
                    "color": "#8e44ad",
                    "floor_id": getir_floor.id if getir_floor else False,
                }
                getir_table = Table.create(vals)
                _logger.info("Getir table oluşturuldu: %s", getir_table.id)
        except Exception as e:
            _logger.error("Getir table oluşturulurken hata: %s", e)

        return getir_table

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
