from odoo import models, fields, api


class GetirOrderCancelWizard(models.TransientModel):
    _name = "getir.order.cancel.wizard"
    _description = "Getir Order Cancel Wizard"

    order_id = fields.Many2one("getir.order", string="Sipariş", required=True)
    reason_id = fields.Many2one("getir.cancel.reason", string="İptal Sebebi", required=True)
    note = fields.Text(string="Açıklama")
    
    # Eksik ürün nedeniyle iptal için
    is_product_missing = fields.Boolean(string="Ürün Eksikliği")
    missing_product_id = fields.Char(string="Eksik Ürün ID (Getir)", 
        help="Eksik ürünün Getir'deki ID'si. Bu ürün otomatik olarak 'Tükendi' olarak işaretlenir.")

    def action_confirm(self):
        """İptali onayla"""
        self.ensure_one()
        
        product_id = self.missing_product_id if self.is_product_missing else None
        
        return self.order_id.do_cancel(
            reason_id=self.reason_id.id,
            note=self.note or "",
            product_id=product_id
        )
