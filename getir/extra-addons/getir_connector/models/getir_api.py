import requests
import json
import logging
from datetime import datetime, timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GetirAPI(models.Model):
    _name = "getir.api"
    _description = "Getir Yemek API Configuration"

    name = fields.Char(default="Getir API", required=True)

    app_secret_key = fields.Char(required=True)
    restaurant_secret_key = fields.Char(required=True)

    token = fields.Char(readonly=True)
    token_expire = fields.Datetime(string="Token Expire Time")

    api_url = fields.Char(
        default="https://food-external-api-gateway.development.getirapi.com",
        required=True,
    )

    active = fields.Boolean(default=True)

    # -------------------------------------------
    # LOGIN
    # -------------------------------------------
    def action_login(self):
        url = f"{self.api_url}/auth/login"
        payload = {
            "appSecretKey": self.app_secret_key,
            "restaurantSecretKey": self.restaurant_secret_key,
        }
        headers = {"Content-Type": "application/json"}

        res = requests.post(url, json=payload, timeout=20)

        if res.status_code != 200:
            raise UserError(f"Login failed: {res.text}")

        data = res.json()
        token = data.get("token") or data.get("data", {}).get("token")

        self.write({
            "token": token,
            "token_expire": datetime.utcnow() + timedelta(hours=1),
        })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Getir API",
                "message": "Login success. Token received.",
                "type": "success",
            },
        }

    # -------------------------------------------
    # TOKEN CHECK
    # -------------------------------------------
    def _ensure_token(self):
        if not self.token or not self.token_expire or self.token_expire < datetime.utcnow():
            self.action_login()

    # -------------------------------------------
    # API CALL WRAPPER
    # -------------------------------------------
    def call(self, method, endpoint, data=None, json_data=None, params=None, headers=None, files=None):
        self._ensure_token()

        url = f"{self.api_url}{endpoint}"

        hdrs = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        if headers:
            hdrs.update(headers)

        try:
            res = requests.request(
                method=method,
                url=url,
                json=json_data,
                data=data,
                params=params,
                files=files,
                headers=hdrs,
                timeout=30,
            )
        except Exception as e:
            self.env["getir.log"].create_log(endpoint, data or json_data, None, f"Error: {e}")
            raise UserError(str(e))

        # Log
        self.env["getir.log"].create_log(endpoint, data or json_data, res.text, res.status_code)

        if res.status_code >= 400:
            raise UserError(f"Getir API Error {res.status_code}: {res.text}")

        return res.json() if "application/json" in res.headers.get("Content-Type", "") else res.text
    # -------------------------------------------