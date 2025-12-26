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

    def unlink(self):
        """
        POS siparişi silinmeden önce, eğer Getir siparişiyse
        Getir API'ye iptal gönder.
        """
        for order in self:
            self._cancel_getir_if_needed(order)
        
        return super().unlink()

    def write(self, vals):
        """
        State 'cancel' olarak değişirse Getir siparişini iptal et.
        """
        result = super().write(vals)
        
        # State 'cancel' olarak değiştiyse
        if vals.get('state') == 'cancel':
            for order in self:
                self._cancel_getir_if_needed(order)
        
        return result

    def action_pos_order_cancel(self):
        """
        POS sipariş iptal action'ı - Getir siparişini de iptal et.
        """
        for order in self:
            self._cancel_getir_if_needed(order)
        
        # Orijinal metodu çağır (varsa)
        if hasattr(super(), 'action_pos_order_cancel'):
            return super().action_pos_order_cancel()
        else:
            return self.write({'state': 'cancel'})

    def _cancel_getir_if_needed(self, order):
        """
        Eğer verilen sipariş bir Getir siparişiyse, Getir'e iptal gönder.
        """
        getir_order = None
        order_ref = ""
        
        # Getir siparişi mi kontrol et
        if order.is_getir_order and order.getir_order_id:
            getir_order = order.getir_order_id
            order_ref = getir_order.name
        elif order.pos_reference and order.pos_reference.startswith('Getir-'):
            getir_order = self.env['getir.order'].sudo().search([
                ('name', '=', order.pos_reference)
            ], limit=1)
            order_ref = order.pos_reference
        
        if not getir_order:
            return
        
        # Henüz iptal edilmemişse iptal et
        if getir_order.state in ('cancelled', 'delivered'):
            _logger.info("Getir siparişi zaten iptal/teslim edilmiş: %s", order_ref)
            return
        
        try:
            _logger.info("POS'tan Getir siparişi iptal ediliyor: %s", order_ref)
            
            # Default iptal sebebi bul
            cancel_reason = self.env['getir.cancel.reason'].sudo().search([
                ('active', '=', True)
            ], limit=1)
            
            if cancel_reason:
                getir_order.sudo().do_cancel(
                    reason_id=cancel_reason.id,
                    note="POS'tan sipariş iptal edildi",
                    product_id=None
                )
                _logger.info("Getir siparişi başarıyla iptal edildi: %s", order_ref)
            else:
                _logger.warning("İptal sebebi bulunamadı: %s", order_ref)
        except Exception as e:
            _logger.error("Getir iptal hatası (%s): %s", order_ref, e)

    def cancel_getir_order_from_pos(self):
        """
        POS frontend'den çağrılabilecek RPC metodu.
        Getir siparişini iptal eder.
        """
        self.ensure_one()
        _logger.info("cancel_getir_order_from_pos çağrıldı: %s", self.pos_reference)
        self._cancel_getir_if_needed(self)
        return {'success': True}

    def cancel_getir_order_with_reason(self, reason_id, note=""):
        """
        POS frontend'den çağrılabilecek RPC metodu.
        Getir siparişini belirtilen sebep ve notla iptal eder.
        
        :param reason_id: Getir cancel reason ID (MongoDB ObjectID string)
        :param note: İptal notu
        """
        self.ensure_one()
        _logger.info("cancel_getir_order_with_reason çağrıldı: %s, reason=%s", self.pos_reference, reason_id)
        
        getir_order = None
        order_ref = ""
        
        # Getir siparişi mi kontrol et
        if self.is_getir_order and self.getir_order_id:
            getir_order = self.getir_order_id
            order_ref = getir_order.name
        elif self.pos_reference and self.pos_reference.startswith('Getir-'):
            getir_order = self.env['getir.order'].sudo().search([
                ('name', '=', self.pos_reference)
            ], limit=1)
            order_ref = self.pos_reference
        
        if not getir_order:
            _logger.warning("Getir siparişi bulunamadı: %s", self.pos_reference)
            return {'success': False, 'error': 'Getir siparişi bulunamadı'}
        
        # Henüz iptal edilmemişse iptal et
        if getir_order.state in ('cancelled', 'delivered'):
            _logger.info("Getir siparişi zaten iptal/teslim edilmiş: %s", order_ref)
            return {'success': False, 'error': 'Sipariş zaten iptal/teslim edilmiş'}
        
        try:
            # Getir API'den cancel reason'ı bul
            cancel_reason = self.env['getir.cancel.reason'].sudo().search([
                ('getir_reason_id', '=', reason_id),
                ('active', '=', True)
            ], limit=1)
            
            if not cancel_reason:
                # Reason bulunamazsa ilk aktif reason'ı kullan
                cancel_reason = self.env['getir.cancel.reason'].sudo().search([
                    ('active', '=', True)
                ], limit=1)
            
            if cancel_reason:
                getir_order.sudo().do_cancel(
                    reason_id=cancel_reason.id,
                    note=note or "POS'tan sipariş iptal edildi",
                    product_id=None
                )
                _logger.info("Getir siparişi başarıyla iptal edildi: %s", order_ref)
                
                # POS siparişini de iptal et
                self.write({'state': 'cancel'})
                
                return {'success': True}
            else:
                _logger.warning("İptal sebebi bulunamadı: %s", order_ref)
                return {'success': False, 'error': 'İptal sebebi bulunamadı'}
                
        except Exception as e:
            _logger.error("Getir iptal hatası (%s): %s", order_ref, e)
            return {'success': False, 'error': str(e)}

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

