import json
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GetirMenuItem(models.Model):
    """Getir'den gelen menü öğeleri"""
    _name = "getir.menu.item"
    _description = "Getir Menu Item"
    _order = "category_name, sequence, name"

    name = fields.Char(string="Ürün Adı", required=True, index=True)
    name_en = fields.Char(string="Ürün Adı (EN)")
    
    getir_product_id = fields.Char(string="Getir Product ID", required=True, index=True)
    chain_product_id = fields.Char(string="Chain Product ID", index=True)
    
    category_id = fields.Char(string="Getir Category ID")
    category_name = fields.Char(string="Kategori")
    chain_category_id = fields.Char(string="Chain Category ID")
    
    description = fields.Text(string="Açıklama")
    price = fields.Float(string="Fiyat")
    
    is_active = fields.Boolean(string="Aktif", default=True)
    is_option_product = fields.Boolean(string="Opsiyon Ürünü", default=False)
    
    image_url = fields.Char(string="Görsel URL")
    
    # İlişkiler
    product_id = fields.Many2one("product.product", string="Odoo Ürün", ondelete="set null")
    option_ids = fields.One2many("getir.menu.option", "menu_item_id", string="Opsiyonlar")
    
    sequence = fields.Integer(default=10)
    
    # Sync bilgisi
    last_sync = fields.Datetime(string="Son Senkronizasyon")
    raw_data = fields.Text(string="Raw JSON")

    _sql_constraints = [
        ("getir_product_id_unique", "unique(getir_product_id)", "Bu Getir ürünü zaten mevcut.")
    ]

    def action_create_odoo_product(self):
        """Bu menü öğesinden Odoo ürünü oluştur"""
        self.ensure_one()
        if self.product_id:
            raise UserError("Bu ürün zaten Odoo'da mevcut.")
        
        product = self.env["product.product"].sudo().create({
            "name": self.name,
            "list_price": self.price or 0.0,
            "sale_ok": True,
            "purchase_ok": False,
            "type": "consu",
            "available_in_pos": True,
        })
        
        self.product_id = product.id
        
        # Mapping tablosunu güncelle
        self.env["getir.product.map"].sudo().create({
            "name": self.name,
            "getir_product_id": self.getir_product_id,
            "getir_chain_product_id": self.chain_product_id or "",
            "product_id": product.id,
        })
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Ürün Oluşturuldu",
                "message": f"{self.name} Odoo'da oluşturuldu.",
                "type": "success",
            },
        }


class GetirMenuOption(models.Model):
    """Getir menü opsiyonları"""
    _name = "getir.menu.option"
    _description = "Getir Menu Option"
    _order = "category_name, sequence, name"

    name = fields.Char(string="Opsiyon Adı", required=True)
    name_en = fields.Char(string="Opsiyon Adı (EN)")
    
    getir_option_id = fields.Char(string="Getir Option ID", index=True)
    chain_option_id = fields.Char(string="Chain Option ID")
    
    category_id = fields.Char(string="Option Category ID")
    category_name = fields.Char(string="Opsiyon Kategorisi")
    chain_category_id = fields.Char(string="Chain Option Category ID")
    
    price = fields.Float(string="Ek Fiyat")
    is_active = fields.Boolean(string="Aktif", default=True)
    is_default = fields.Boolean(string="Varsayılan")
    is_required = fields.Boolean(string="Zorunlu")
    
    min_count = fields.Integer(string="Min Seçim", default=0)
    max_count = fields.Integer(string="Max Seçim", default=1)
    
    menu_item_id = fields.Many2one("getir.menu.item", string="Ana Ürün", ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Odoo Ürün", ondelete="set null")
    
    sequence = fields.Integer(default=10)


class GetirMenuCategory(models.Model):
    """Getir menü kategorileri"""
    _name = "getir.menu.category"
    _description = "Getir Menu Category"
    _order = "sequence, name"

    name = fields.Char(string="Kategori Adı", required=True)
    name_en = fields.Char(string="Kategori Adı (EN)")
    
    getir_category_id = fields.Char(string="Getir Category ID", required=True, index=True)
    chain_category_id = fields.Char(string="Chain Category ID")
    
    is_active = fields.Boolean(string="Aktif", default=True)
    sequence = fields.Integer(default=10)
    
    pos_category_id = fields.Many2one("pos.category", string="POS Kategori")
    
    item_count = fields.Integer(string="Ürün Sayısı", compute="_compute_item_count")

    def _compute_item_count(self):
        for rec in self:
            rec.item_count = self.env["getir.menu.item"].search_count([
                ("category_id", "=", rec.getir_category_id)
            ])

    _sql_constraints = [
        ("getir_category_id_unique", "unique(getir_category_id)", "Bu kategori zaten mevcut.")
    ]
