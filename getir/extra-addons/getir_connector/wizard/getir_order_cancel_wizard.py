from odoo import models, fields, api


class GetirOrderCancelWizard(models.TransientModel):
    _name = "getir.order.cancel.wizard"
    _description = "Getir Order Cancel Wizard"

    order_id = fields.Many2one("getir.order", string="Sipariş", required=True)
    reason_id = fields.Many2one("getir.cancel.reason", string="İptal Sebebi", required=True)
    note = fields.Text(string="Açıklama")
    
    # Eksik ürün nedeniyle iptal için
    is_product_missing = fields.Boolean(string="Ürün Eksikliği", compute="_compute_is_product_missing", store=True)
    missing_product_id = fields.Char(string="Eksik Ürün ID (Getir)", 
        help="Eksik ürünün Getir'deki ID'si. Bu ürün otomatik olarak 'Tükendi' olarak işaretlenir.")

    @api.depends('reason_id')
    def _compute_is_product_missing(self):
        """Ürün eksik sebebi seçildiğinde otomatik true yap"""
        for wizard in self:
            # Ürün eksik reason ID: 5c5b49a768f6a45d427f0a8e
            wizard.is_product_missing = wizard.reason_id.getir_reason_id == '5c5b49a768f6a45d427f0a8e'

    def action_confirm(self):
        """İptali onayla"""
        self.ensure_one()
        
        product_id = self.missing_product_id if self.is_product_missing else None
        
        return self.order_id.do_cancel(
            reason_id=self.reason_id.id,
            note=self.note or "",
            product_id=product_id
        )
