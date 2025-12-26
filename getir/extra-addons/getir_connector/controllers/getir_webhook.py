from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
import json
import logging
import time
import hmac
import hashlib

_logger = logging.getLogger(__name__)


class GetirWebhook(http.Controller):

    # ----------------------------------------------------------------------
    # 🟣 SIGNATURE DOĞRULAMA (HMAC-SHA256)
   # ----------------------------------------------------------------------
    def _verify_signature(self, raw_body):
        """
        Getir webhook signature doğrulaması.
        Şimdilik test secret key kullanıyor. Production'da gerçek key girilecek.
        """

        secret_key = request.env['ir.config_parameter'].sudo().get_param('getir.api_secret')

        # Eğer secret yoksa doğrulama devre dışı → geliştirme ortamı
        if not secret_key:
            _logger.warning("⚠ Getir SECRET KEY tanımlı değil (signature doğrulama pasif).")
            return True

        signature = request.httprequest.headers.get("X-Getir-Signature")
        timestamp = request.httprequest.headers.get("X-Getir-Timestamp")

        if not signature or not timestamp:
            _logger.warning("❌ Signature veya Timestamp header eksik.")
            return False

        # Timestamp geçerlilik kontrolü (5 dakika tolerans)
        try:
            ts = int(timestamp)
            if abs(int(time.time()) - ts) > 300:
                _logger.warning("❌ Timestamp zaman aşımına uğramış.")
                return False
        except:
            return False

        # Hesaplanacak signature (body + timestamp)
        text = f"{timestamp}.{raw_body}".encode("utf-8")
        calc = hmac.new(secret_key.encode("utf-8"), text, hashlib.sha256).hexdigest()

        if calc != signature:
            _logger.error("❌ Signature doğrulanamadı!")
            return False

        return True

    # ----------------------------------------------------------------------
    # Basit test endpoint
    # ----------------------------------------------------------------------
    @http.route('/getir/test_order', type='http', auth='public', csrf=False)
    def xxx_test(self):
        return http.Response(
            json.dumps({"success": True, "message": "Test başarılı!"}),
            status=200,
            content_type="application/json"
        )


    # ----------------------------------------------------------------------
    # 🟣 NEW ORDER
    # ----------------------------------------------------------------------
    @http.route('/getir/newOrder', type='http', auth='public', methods=['POST'], csrf=False)
    def new_order_long(self, **kw):
        return self._new_order_handler()

    @http.route('/newOrder', type='http', auth='public', methods=['POST'], csrf=False)
    def new_order_short(self, **kw):
        return self._new_order_handler()

    def _new_order_handler(self):
        raw = request.httprequest.data.decode("utf-8")
        _logger.info("### RAW BODY: %s", raw)

        # 🔐 SIGNATURE CHECK
        if not self._verify_signature(raw):
            return http.Response(
                json.dumps({"success": False, "error": "Signature doğrulanamadı"}),
                status=403,
                content_type="application/json"
            )

        # JSON PARSE
        try:
            payload = json.loads(raw)
        except Exception:
            return http.Response(
                json.dumps({"success": False, "error": "Gönderilen body geçerli JSON değil."}),
                status=400,
                content_type="application/json"
            )

        # ID CHECK
        if not payload.get("id") and not payload.get("_id"):
            return http.Response(
                json.dumps({"success": False, "error": "Getir Order ID (id/_id) eksik."}),
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

    # ----------------------------------------------------------------------
    # 🟣 CANCEL ORDER
    # ----------------------------------------------------------------------
    @http.route(['/getir/cancelOrder', '/cancelOrder'], type='http', auth='public', csrf=False, methods=['POST'])
    def cancel_order(self):
        raw = request.httprequest.data.decode("utf-8")

        # Signature kontrolü
        if not self._verify_signature(raw):
            return http.Response(
                json.dumps({"success": False, "error": "Signature doğrulanamadı"}),
                status=403,
                content_type="application/json"
            )

        payload = json.loads(raw or "{}")
        _logger.info("GETIR CANCEL ORDER PAYLOAD: %s", payload)

        order_id = str(payload.get("id") or payload.get("orderId"))
        if not order_id:
            return http.Response(
                json.dumps({"success": False, "error": "orderId bulunamadı."}),
                status=400,
                content_type="application/json"
            )

        getir_ref = f"Getir-{order_id}"

        getir_order = request.env["getir.order"].sudo().search([
            ("name", "=", getir_ref)
        ], limit=1)

        if not getir_order:
            return http.Response(
                json.dumps({"success": False, "error": "Sipariş bulunamadı"}),
                status=404,
                content_type="application/json"
            )

        # POS siparişi iptal et
        if getir_order.pos_order_id:
            getir_order.pos_order_id.sudo().write({"state": "cancel"})

        getir_order.status = "cancelled"

        return http.Response(
            json.dumps({"success": True, "message": "İptal işlendi."}),
            status=200,
            content_type="application/json"
        )

    # ----------------------------------------------------------------------
    # 🟣 COURIER STATUS
    # ----------------------------------------------------------------------
    @http.route(['/getir/courier', '/courier'], type='http', auth='public', csrf=False, methods=['POST'])
    def courier(self):
        raw = request.httprequest.data.decode("utf-8")

        if not self._verify_signature(raw):
            return http.Response(
                json.dumps({"success": False, "error": "Signature doğrulanamadı"}),
                status=403,
                content_type="application/json"
            )

        payload = json.loads(raw or "{}")
        _logger.info("GETIR COURIER STATUS: %s", payload)

        order_id = str(payload.get("orderId"))
        courier_status = payload.get("courierStatus")

        getir_order = request.env["getir.order"].sudo().search([
            ("getir_id", "=", order_id)
        ], limit=1)

        if getir_order:
            getir_order.status = f"courier:{courier_status}"

        return http.Response(
            json.dumps({"success": True}),
            status=200,
            content_type="application/json"
        )

    # ----------------------------------------------------------------------
    # 🟣 RESTORAN DURUMU
    # ----------------------------------------------------------------------
    @http.route(['/getir/restaurant', '/restaurant'], type='http', auth='public', csrf=False, methods=['POST'])
    def restaurant(self):
        raw = request.httprequest.data.decode("utf-8")

        if not self._verify_signature(raw):
            return http.Response(
                json.dumps({"success": False, "error": "Signature doğrulanamadı"}),
                status=403,
                content_type="application/json"
            )

        payload = json.loads(raw or "{}")
        _logger.info("GETIR RESTAURANT STATUS PAYLOAD: %s", payload)

        return http.Response(
            json.dumps({"success": True}),
            status=200,
            content_type="application/json"
        )
