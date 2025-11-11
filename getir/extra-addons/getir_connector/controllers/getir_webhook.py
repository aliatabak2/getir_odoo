from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class GetirWebhook(http.Controller):

    @http.route('/newOrder', type='json', auth='public', methods=['POST'], csrf=False)
    def new_order(self, **kw):
        data = request.get_json_data()
        _logger.info("GETIR NEW ORDER: %s", data)
        request.env["getir.api"].sudo()._create_pos_order_from_getir(data)
        return {"status": "ok"}

    @http.route('/cancelOrder', type='json', auth='public', methods=['POST'], csrf=False)
    def cancel_order(self, **kw):
        data = request.get_json_data()
        _logger.info("GETIR CANCEL ORDER: %s", data)
        order_ref = f"Getir-{data.get('id')}"
        pos_order = request.env["pos.order"].sudo().search([("ref", "=", order_ref)], limit=1)
        if pos_order:
            pos_order.sudo().write({"state": "cancel"})
        return {"status": "ok"}

    @http.route('/courier', type='json', auth='public', methods=['POST'], csrf=False)
    def courier_notification(self, **kw):
        data = request.get_json_data()
        _logger.info("GETIR COURIER NOTIFICATION: %s", data)
        return {"status": "ok"}

    @http.route('/restaurant', type='json', auth='public', methods=['POST'], csrf=False)
    def restaurant_status(self, **kw):
        data = request.get_json_data()
        _logger.info("GETIR RESTAURANT STATUS: %s", data)
        return {"status": "ok"}
