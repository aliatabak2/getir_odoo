from odoo import models, fields


class GetirCancelReason(models.Model):
    _name = "getir.cancel.reason"
    _description = "Getir Order Cancel Reasons"

    name = fields.Char(string="Sebep", required=True)
    getir_reason_id = fields.Char(string="Getir Reason ID", required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        ("getir_reason_id_unique", "unique(getir_reason_id)", "Bu Getir sebep ID zaten mevcut.")
    ]
