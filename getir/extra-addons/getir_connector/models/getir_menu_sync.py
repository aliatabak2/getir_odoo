import json
import logging
from datetime import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GetirMenuSync(models.Model):
    """Getir menü senkronizasyon yönetimi"""
    _name = "getir.menu.sync"
    _description = "Getir Menu Sync"
    _order = "create_date desc"

    name = fields.Char(string="Sync Adı", required=True, default=lambda self: f"Sync-{fields.Datetime.now()}")
    
    state = fields.Selection([
        ("draft", "Bekliyor"),
        ("running", "Çalışıyor"),
        ("done", "Tamamlandı"),
        ("error", "Hata"),
    ], string="Durum", default="draft")
    
    # İstatistikler
    total_products = fields.Integer(string="Toplam Ürün")
    created_products = fields.Integer(string="Oluşturulan")
    updated_products = fields.Integer(string="Güncellenen")
    total_options = fields.Integer(string="Toplam Opsiyon")
    total_categories = fields.Integer(string="Toplam Kategori")
    
    error_message = fields.Text(string="Hata Mesajı")
    
    sync_date = fields.Datetime(string="Sync Tarihi")
    duration = fields.Float(string="Süre (sn)")
    
    # Ayarlar
    create_odoo_products = fields.Boolean(string="Odoo Ürün Oluştur", default=True,
        help="Getir ürünlerini otomatik olarak Odoo product.product olarak oluştur")
    update_prices = fields.Boolean(string="Fiyatları Güncelle", default=True)
    sync_to_pos = fields.Boolean(string="POS'a Aktar", default=True)
    
    def action_start_sync(self):
        """Senkronizasyonu başlat"""
        self.ensure_one()
        self.write({"state": "running", "sync_date": fields.Datetime.now()})
        
        try:
            start_time = datetime.now()
            
            # API'den menüyü çek
            api = self.env["getir.api"].sudo().search([("active", "=", True)], limit=1)
            if not api:
                raise UserError("Aktif Getir API yapılandırması bulunamadı.")
            
            menu_data = api.get_restaurant_menu()
            
            stats = self._process_menu_data(menu_data)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            self.write({
                "state": "done",
                "total_products": stats.get("total_products", 0),
                "created_products": stats.get("created_products", 0),
                "updated_products": stats.get("updated_products", 0),
                "total_options": stats.get("total_options", 0),
                "total_categories": stats.get("total_categories", 0),
                "duration": duration,
            })
            
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Menü Senkronizasyonu Tamamlandı",
                    "message": f"{stats.get('total_products', 0)} ürün, {stats.get('total_options', 0)} opsiyon senkronize edildi.",
                    "type": "success",
                },
            }
            
        except Exception as e:
            _logger.exception("Menu sync error: %s", e)
            self.write({
                "state": "error",
                "error_message": str(e),
            })
            raise UserError(f"Senkronizasyon hatası: {e}")

    def _process_menu_data(self, menu_data):
        """Menü verisini işle"""
        stats = {
            "total_products": 0,
            "created_products": 0,
            "updated_products": 0,
            "total_options": 0,
            "total_categories": 0,
        }
        
        MenuItem = self.env["getir.menu.item"].sudo()
        MenuOption = self.env["getir.menu.option"].sudo()
        MenuCategory = self.env["getir.menu.category"].sudo()
        ProductMap = self.env["getir.product.map"].sudo()
        Product = self.env["product.product"].sudo()
        
        # Menü yapısını parse et
        # Getir API'den dönen yapı: {"categories": [...], "products": [...]} veya doğrudan liste
        
        products = []
        categories = []
        
        if isinstance(menu_data, dict):
            products = menu_data.get("products", []) or menu_data.get("items", []) or []
            categories = menu_data.get("categories", []) or []
        elif isinstance(menu_data, list):
            products = menu_data
        
        # Kategorileri işle
        for cat_data in categories:
            cat_id = cat_data.get("_id") or cat_data.get("id") or ""
            if not cat_id:
                continue
                
            cat_name = cat_data.get("name", {})
            if isinstance(cat_name, dict):
                name_tr = cat_name.get("tr") or cat_name.get("en") or "Kategori"
                name_en = cat_name.get("en") or ""
            else:
                name_tr = str(cat_name) if cat_name else "Kategori"
                name_en = ""
            
            existing_cat = MenuCategory.search([("getir_category_id", "=", cat_id)], limit=1)
            
            cat_vals = {
                "name": name_tr,
                "name_en": name_en,
                "getir_category_id": cat_id,
                "chain_category_id": cat_data.get("chainCategoryId") or "",
                "is_active": cat_data.get("isActive", True),
                "sequence": cat_data.get("sortOrder") or cat_data.get("sequence") or 10,
            }
            
            if existing_cat:
                existing_cat.write(cat_vals)
            else:
                MenuCategory.create(cat_vals)
                stats["total_categories"] += 1
        
        # Ürünleri işle
        for prod_data in products:
            product_id = prod_data.get("_id") or prod_data.get("id") or ""
            if not product_id:
                continue
            
            prod_name = prod_data.get("name", {})
            if isinstance(prod_name, dict):
                name_tr = prod_name.get("tr") or prod_name.get("en") or "Ürün"
                name_en = prod_name.get("en") or ""
            else:
                name_tr = str(prod_name) if prod_name else "Ürün"
                name_en = ""
            
            prod_desc = prod_data.get("description", {})
            if isinstance(prod_desc, dict):
                description = prod_desc.get("tr") or prod_desc.get("en") or ""
            else:
                description = str(prod_desc) if prod_desc else ""
            
            # Kategori bilgisi
            category = prod_data.get("category", {}) or {}
            cat_id = category.get("_id") or category.get("id") or prod_data.get("categoryId") or ""
            cat_name_data = category.get("name", {})
            if isinstance(cat_name_data, dict):
                cat_name = cat_name_data.get("tr") or cat_name_data.get("en") or ""
            else:
                cat_name = str(cat_name_data) if cat_name_data else ""
            
            price = prod_data.get("price") or prod_data.get("defaultPrice") or 0.0
            
            # Mevcut kayıt var mı?
            existing = MenuItem.search([("getir_product_id", "=", product_id)], limit=1)
            
            item_vals = {
                "name": name_tr,
                "name_en": name_en,
                "getir_product_id": product_id,
                "chain_product_id": prod_data.get("chainProductId") or "",
                "category_id": cat_id,
                "category_name": cat_name,
                "chain_category_id": category.get("chainCategoryId") or "",
                "description": description,
                "price": price,
                "is_active": prod_data.get("isActive", True),
                "is_option_product": prod_data.get("isOptionProduct", False),
                "image_url": prod_data.get("imageUrl") or "",
                "sequence": prod_data.get("sortOrder") or 10,
                "last_sync": fields.Datetime.now(),
                "raw_data": json.dumps(prod_data, ensure_ascii=False),
            }
            
            if existing:
                existing.write(item_vals)
                menu_item = existing
                stats["updated_products"] += 1
            else:
                menu_item = MenuItem.create(item_vals)
                stats["created_products"] += 1
            
            stats["total_products"] += 1
            
            # Odoo ürünü oluştur/güncelle
            if self.create_odoo_products:
                self._sync_odoo_product(menu_item, ProductMap, Product)
            
            # Opsiyonları işle
            options = prod_data.get("options", []) or prod_data.get("optionCategories", []) or []
            for opt_cat in options:
                stats["total_options"] += self._process_options(menu_item, opt_cat, MenuOption)
        
        return stats

    def _sync_odoo_product(self, menu_item, ProductMap, Product):
        """Odoo ürünü oluştur veya güncelle"""
        # Önce mapping tablosuna bak
        mapping = ProductMap.search([
            ("getir_product_id", "=", menu_item.getir_product_id)
        ], limit=1)
        
        if mapping and mapping.product_id:
            # Mevcut ürünü güncelle
            if self.update_prices:
                mapping.product_id.write({
                    "list_price": menu_item.price,
                })
            menu_item.product_id = mapping.product_id.id
            return
        
        # Yeni ürün oluştur
        if not menu_item.product_id:
            # İsimle ara
            existing_product = Product.search([("name", "=", menu_item.name)], limit=1)
            
            if existing_product:
                product = existing_product
                if self.update_prices:
                    product.write({"list_price": menu_item.price})
            else:
                product = Product.create({
                    "name": menu_item.name,
                    "list_price": menu_item.price or 0.0,
                    "sale_ok": True,
                    "purchase_ok": False,
                    "type": "consu",
                    "available_in_pos": self.sync_to_pos,
                })
            
            menu_item.product_id = product.id
            
            # Mapping oluştur
            if not mapping:
                ProductMap.create({
                    "name": menu_item.name,
                    "getir_product_id": menu_item.getir_product_id,
                    "getir_chain_product_id": menu_item.chain_product_id or "",
                    "product_id": product.id,
                })

    def _process_options(self, menu_item, opt_cat_data, MenuOption):
        """Opsiyon kategorisi ve opsiyonları işle"""
        count = 0
        
        # Opsiyon kategorisi bilgileri
        opt_cat_id = opt_cat_data.get("_id") or opt_cat_data.get("id") or ""
        opt_cat_name = opt_cat_data.get("name", {})
        if isinstance(opt_cat_name, dict):
            cat_name_tr = opt_cat_name.get("tr") or opt_cat_name.get("en") or ""
        else:
            cat_name_tr = str(opt_cat_name) if opt_cat_name else ""
        
        min_count = opt_cat_data.get("minCount") or opt_cat_data.get("minSelection") or 0
        max_count = opt_cat_data.get("maxCount") or opt_cat_data.get("maxSelection") or 1
        is_required = opt_cat_data.get("isRequired", False)
        
        # Opsiyonları işle
        options = opt_cat_data.get("options", []) or opt_cat_data.get("items", []) or []
        
        for opt_data in options:
            opt_id = opt_data.get("_id") or opt_data.get("id") or ""
            if not opt_id:
                continue
            
            opt_name = opt_data.get("name", {})
            if isinstance(opt_name, dict):
                name_tr = opt_name.get("tr") or opt_name.get("en") or "Opsiyon"
                name_en = opt_name.get("en") or ""
            else:
                name_tr = str(opt_name) if opt_name else "Opsiyon"
                name_en = ""
            
            price = opt_data.get("price") or opt_data.get("additionalPrice") or 0.0
            
            # Mevcut var mı?
            existing = MenuOption.search([
                ("getir_option_id", "=", opt_id),
                ("menu_item_id", "=", menu_item.id),
            ], limit=1)
            
            opt_vals = {
                "name": name_tr,
                "name_en": name_en,
                "getir_option_id": opt_id,
                "chain_option_id": opt_data.get("chainOptionId") or "",
                "category_id": opt_cat_id,
                "category_name": cat_name_tr,
                "chain_category_id": opt_cat_data.get("chainCategoryId") or "",
                "price": price,
                "is_active": opt_data.get("isActive", True),
                "is_default": opt_data.get("isDefault", False),
                "is_required": is_required,
                "min_count": min_count,
                "max_count": max_count,
                "menu_item_id": menu_item.id,
                "sequence": opt_data.get("sortOrder") or 10,
            }
            
            if existing:
                existing.write(opt_vals)
            else:
                MenuOption.create(opt_vals)
            
            count += 1
        
        return count

    @api.model
    def action_quick_sync(self):
        """Hızlı senkronizasyon - ana menüden çağrılır"""
        sync = self.create({
            "name": f"Quick Sync - {fields.Datetime.now()}",
            "create_odoo_products": True,
            "update_prices": True,
            "sync_to_pos": True,
        })
        return sync.action_start_sync()
