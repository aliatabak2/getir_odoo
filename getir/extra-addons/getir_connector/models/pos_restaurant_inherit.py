from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class GetirRestaurantSetup(models.Model):
    _inherit = "pos.order"

    @api.model
    def create_getir_floor_and_table(self):
        """
        Odoo 18 için floor/table oluşturma.
        Masa numarası (table_number) zorunlu olduğu için 999 kullanıyoruz.
        """
        env = self.env

        Floor = env['restaurant.floor']
        Table = env['restaurant.table']

        # değişken HER KOŞULDA tanımlı olsun
        getir_floor = None
        getir_table = None

        # 1) GETIR floor
        try:
            getir_floor = Floor.search([("name", "=", "Getir")], limit=1)
            if not getir_floor:
                getir_floor = Floor.create({
                    "name": "Getir",
                    "sequence": 50,
                    "active": True,
                })
                _logger.info("Getir floor oluşturuldu. ID = %s", getir_floor.id)
            else:
                _logger.info("Getir floor bulundu. ID = %s", getir_floor.id)
        except Exception as e:
            _logger.error("Floor oluşturulurken hata: %s", e)

        # 2) GETIR TABLE
        try:
            getir_table = Table.search([('table_number', '=', 999)], limit=1)
            if not getir_table:
                create_vals = {
                    "table_number": 999,   # ← burası düzeltilmeli
                    "seats": 0,
                    "active": True,
                    "shape": "square",
                    "width": 120,
                    "height": 120,
                    "position_h": 200,
                    "position_v": 200,
                    "color": "#8e44ad",
                }


                if getir_floor:
                    create_vals["floor_id"] = getir_floor.id

                getir_table = Table.create(create_vals)
                _logger.info("Getir table oluşturuldu. ID = %s", getir_table.id)
            else:
                _logger.info("Getir table bulundu. ID = %s", getir_table.id)
        except Exception as e:
            _logger.error("Table oluşturulurken hata: %s", e)

        return getir_table
