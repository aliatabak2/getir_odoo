from odoo import models, fields


class GetirProductMap(models.Model):
    _name = "getir.product.map"
    _description = "Getir Product ↔ Odoo Product Mapping"

    name = fields.Char(required=True)
    getir_product_id = fields.Char(string="Getir Product ID", required=True, index=True)
    getir_chain_product_id = fields.Char(string="Getir Chain Product ID")
    product_id = fields.Many2one("product.product", required=True)
    active = fields.Boolean(default=True)
