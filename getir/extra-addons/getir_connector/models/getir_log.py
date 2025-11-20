import json
from odoo import models, fields, api


class GetirLog(models.Model):
    _name = "getir.log"
    _description = "Getir API Log"
    _order = "create_date desc"

    name = fields.Char(string="Name", default="/", required=True)
    endpoint = fields.Char(string="Endpoint")
    method = fields.Char(string="HTTP Method")
    request_payload = fields.Text(string="Request Payload")
    response_payload = fields.Text(string="Response Payload")
    http_status = fields.Integer(string="HTTP Status")
    success = fields.Boolean(default=False)
    error_message = fields.Char(string="Error")

    order_id = fields.Many2one("getir.order", string="Getir Order")

    @api.model
    def create_log(self, endpoint, request_data, response_data, http_status=None, method=None, order=None, error=None):
        """Helper - GetirAPI.call burayı kullanacak."""
        if isinstance(request_data, (dict, list)):
            request_data = json.dumps(request_data, ensure_ascii=False, indent=2)
        if isinstance(response_data, (dict, list)):
            response_data = json.dumps(response_data, ensure_ascii=False, indent=2)

        vals = {
            "name": endpoint or "/",
            "endpoint": endpoint or "",
            "method": method or "",
            "request_payload": request_data or "",
            "response_payload": response_data or "",
            "http_status": http_status or 0,
            "success": http_status is not None and http_status < 400,
            "error_message": error or "",
            "order_id": order.id if order else False,
        }
        return self.create(vals)
