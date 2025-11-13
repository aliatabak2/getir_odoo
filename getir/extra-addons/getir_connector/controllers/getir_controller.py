from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class GetirWebhookController(http.Controller):
    @http.route(['/newOrder'], type='json', auth='user', methods=['POST'], csrf=False)
    def getir_new_order_json(self, **payload):
        return self._handle_new_order(payload)

    @http.route(['/newOrder'], type='json', auth='user', methods=['POST'], csrf=False)


    def new_order(self, **kw):
        """Getir'den gelen yeni sipariş"""
        try:
            payload = request.jsonrequest
            _logger.info("Yeni Getir Siparişi Alındı: %s", payload)

            api = request.env['getir.api'].sudo().search([], limit=1)
            if not api:
                return {"success": False, "error": "Getir API yapılandırması bulunamadı."}

            pos_order = api._create_pos_order_from_getir(payload)
            return {"success": True, "order_id": pos_order.id}

        except Exception as e:
            _logger.error("Getir newOrder hata: %s", str(e))
            return {"success": False, "error": str(e)}

    @http.route(['/cancelOrder'], type='json', auth='public', methods=['POST'], csrf=False)
    def cancel_order(self, **kwargs):
        """Getir sipariş iptali"""
        payload = request.jsonrequest
        _logger.info("Getir Sipariş İptali Alındı: %s", payload)
        # TODO: burada pos_order.cancel() ileride eklenecek
        return {"success": True}

    @http.route(['/courier'], type='json', auth='public', methods=['POST'], csrf=False)
    def courier_update(self, **kwargs):
        """Kurye durumu bildirimi"""
        payload = request.jsonrequest
        _logger.info("Kurye durumu: %s", payload)
        return {"success": True}

    @http.route(['/restaurant'], type='json', auth='public', methods=['POST'], csrf=False)
    def restaurant_status(self, **kwargs):
        """Restoran durumu bildirimi"""
        payload = request.jsonrequest
        _logger.info("Restoran durumu: %s", payload)
        return {"success": True}
