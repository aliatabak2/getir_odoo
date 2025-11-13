from odoo import models, api

class GetirRestaurantSetup(models.Model):
    _inherit = "pos.order"

    @api.model
    def create_getir_floor_and_table(self):
        """Getir Floor ve Masa otomatik oluşturur (tek seferlik)"""
        env = self.env

        # GETIR FLOOR
        getir_floor = env["restaurant.floor"].search([("name", "=", "Getir")], limit=1)
        if not getir_floor:
            getir_floor = env["restaurant.floor"].create({
                "name": "Getir",
                "sequence": 50,
                "active": True,
            })

        # GETIR TABLE
        getir_table = env["restaurant.table"].search([("name", "=", "Getir Online")], limit=1)
        if not getir_table:
            getir_table = env["restaurant.table"].create({
                "name": "Getir Online",
                "floor_id": getir_floor.id,
                "shape": "square",
                "width": 100,
                "height": 100,
                "position_h": 200,
                "position_v": 200,
                "seats": 0,
                "active": True,
                "color": "#8e44ad"
            })

        return getir_table
class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_orders(self):
        orders = super()._load_orders()
        if self.env.context.get("is_getir"):
            orders = [o for o in orders if o.get("is_getir_order")]
        return orders