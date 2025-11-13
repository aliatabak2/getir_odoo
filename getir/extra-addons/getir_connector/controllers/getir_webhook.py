from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class GetirWebhook(http.Controller):

    # YENİ SİPARİŞ
    @http.route(['/newOrder', '/getir/newOrder'], type='http', auth='public', methods=['POST'], csrf=False)
    def new_order(self, **kwargs):
        """
        Getir'den gelen yeni sipariş webhook'u.
        Postman / Getir -> JSON body -> Odoo
        """
        # Body'deki JSON'u oku
        data = request.get_json_data() or {}
        _logger.info("GETIR NEW ORDER: %s", data)

        api = request.env["getir.api"].sudo().search([], limit=1)
        if not api:
            _logger.error("Getir API yapılandırması bulunamadı.")
            return request.make_json_response({
                "success": False,
                "error": "Getir API yapılandırması bulunamadı."
            }, status=500)

        try:
            pos_order = api._create_pos_order_from_getir(data)
        except Exception as e:
            _logger.exception("Getir newOrder işleminde hata: %s", e)
            return request.make_json_response({
                "success": False,
                "error": str(e),
            }, status=500)

        return request.make_json_response({
            "success": True,
            "order_id": pos_order.id,
        })

    # SİPARİŞ İPTAL
    @http.route(['/cancelOrder', '/getir/cancelOrder'], type='http', auth='public', methods=['POST'], csrf=False)
    def cancel_order(self, **kwargs):
        """
        Getir sipariş iptali webhook'u.
        """
        data = request.get_json_data() or {}
        _logger.info("GETIR CANCEL ORDER: %s", data)

        order_ref = f"Getir-{data.get('id')}"
        pos_order = request.env["pos.order"].sudo().search(
            [("pos_reference", "=", order_ref)],
            limit=1,
        )
        if pos_order:
            pos_order.sudo().write({"state": "cancel"})
            _logger.info("Getir siparişi iptal edildi: %s", order_ref)
        else:
            _logger.warning("İptal edilecek POS siparişi bulunamadı: %s", order_ref)

        return request.make_json_response({"success": True})

    # KURYE DURUMU
    @http.route(['/courier', '/getir/courier'], type='http', auth='public', methods=['POST'], csrf=False)
    def courier_notification(self, **kwargs):
        """
        Kurye durumu bildirimi (Getir -> Odoo).
        """
        data = request.get_json_data() or {}
        _logger.info("GETIR COURIER NOTIFICATION: %s", data)
        # TODO: İleride pos.order içine kurye statüsü yazmak istersen burada işlersin
        return request.make_json_response({"success": True})

    # RESTORAN DURUMU
    @http.route(['/restaurant', '/getir/restaurant'], type='http', auth='public', methods=['POST'], csrf=False)
    def restaurant_status(self, **kwargs):
        """
        Restoran durumu bildirimi (Getir -> Odoo).
        """
        data = request.get_json_data() or {}
        _logger.info("GETIR RESTAURANT STATUS: %s", data)
        # TODO: Odoo tarafında restoranın online/offline statüsünü tutmak istersen
        return request.make_json_response({"success": True})
