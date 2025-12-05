from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)



class GetirWebhook(http.Controller):
    @http.route('/getir/test_order', type='http', auth='public', methods=['POST'], csrf=False)
    def xxx_test(self, **kw):
        return "OK"
    # ----------------------------------------------------------------------

    @http.route('/getir/newOrder', type='json', auth='public', methods=['POST'], csrf=False)
    def new_order_long(self, **kw):
        return self._new_order_handler()

    @http.route('/newOrder', type='json', auth='public', methods=['POST'], csrf=False)
    def new_order_short(self, **kw):
        return self._new_order_handler()

    def _new_order_handler(self):
        raw = request.httprequest.data.decode("utf-8")
        _logger.info("### RAW BODY: %s", raw)

        # JSON PARSE
        try:
            payload = json.loads(raw)
        except Exception:
            return http.Response(
                json.dumps({
                    "success": False,
                    "error": "Gönderilen body geçerli JSON değil."
                }),
                status=400,
                content_type="application/json"
            )

        # ID CHECK
        if not payload.get("id") and not payload.get("_id"):
            return http.Response(
                json.dumps({
                    "success": False,
                    "error": "Getir Order ID (id/_id) eksik."
                }),
                status=400,
                content_type="application/json"
            )

        try:
            getir_order = request.env["getir.order"].sudo().create_from_payload(payload)

            return http.Response(
                json.dumps({
                    "success": True,
                    "order_name": getir_order.name,
                    "getir_id": getir_order.getir_id,
                }),
                status=200,
                content_type="application/json"
            )

        except UserError as e:
            return http.Response(
                json.dumps({"success": False, "error": str(e)}),
                status=400,
                content_type="application/json"
            )

        except Exception as e:
            _logger.exception("Beklenmeyen hata: %s", e)
            return http.Response(
                json.dumps({"success": False, "error": "Sunucu hatası."}),
                status=500,
                content_type="application/json"
            )

                    #routes = request.env['ir.http']._get_routes()
#                   [x for x in routes if 'getir' in x]

                    #   tail -f var/log/odoo/odoo.log
                    #
    # ----------------------------------------------------------------------
    # 🟣 SİPARİŞ İPTAL / CANCEL
    # ----------------------------------------------------------------------
    @http.route(['/getir/cancelOrder', '/cancelOrder'], type='json', auth='public', csrf=False, methods=['POST'])
    def cancel_order(self):
        payload = request.jsonrequest or {}
        _logger.info("GETIR CANCEL ORDER PAYLOAD: %s", payload)

        order_id = str(payload.get("id") or payload.get("orderId"))
        if not order_id:
            return {"success": False, "error": "orderId bulunamadı."}

        getir_ref = f"Getir-{order_id}"

        getir_order = request.env["getir.order"].sudo().search([
            ("name", "=", getir_ref)
        ], limit=1)

        if not getir_order:
            return {"success": False, "error": "Sipariş bulunamadı"}

        # POS siparişi iptal et
        if getir_order.pos_order_id:
            getir_order.pos_order_id.sudo().write({"state": "cancel"})

        # Getir tarafına iptal sebebi iletilecek endpoint: /food-orders/{id}/cancel
        # Biz burada sadece kaydediyoruz
        getir_order.status = "cancelled"

        return {"success": True, "message": "İptal işlendi."}

    # ----------------------------------------------------------------------
    # 🟣 KURYE DURUMU
    # ----------------------------------------------------------------------
    @http.route(['/getir/courier', '/courier'], type='json', auth='public', csrf=False, methods=['POST'])
    def courier(self):
        payload = request.jsonrequest or {}
        _logger.info("GETIR COURIER STATUS: %s", payload)

       

        order_id = str(payload.get("orderId"))
        courier_status = payload.get("courierStatus")

        getir_order = request.env["getir.order"].sudo().search([
            ("getir_id", "=", order_id)
        ], limit=1)

        if getir_order:
            getir_order.status = f"courier:{courier_status}"

        return {"success": True}

    # ----------------------------------------------------------------------
    # 🟣 RESTORAN DURUMU (open/close)
    # ----------------------------------------------------------------------
    @http.route(['/getir/restaurant', '/restaurant'], type='json', auth='public', csrf=False, methods=['POST'])
    def restaurant(self):
        payload = request.jsonrequest or {}
        _logger.info("GETIR RESTAURANT STATUS PAYLOAD: %s", payload)

        # Örn: {"status": 100} = açık, 200 = kapalı
        return {"success": True}
