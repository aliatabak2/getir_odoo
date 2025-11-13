from odoo import models, fields, api


class PosOrder(models.Model):
    _inherit = "pos.order"

    is_getir_order = fields.Boolean(string="Getir Siparişi", default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            pos_ref = vals.get("pos_reference", "") or ""
            if isinstance(pos_ref, str) and pos_ref.startswith("Getir-"):
                vals.setdefault("is_getir_order", True)
        return super().create(vals_list)
