{
    "name": "Getir Connector",
    "version": "18.0.1.0.0",
    "summary": "Getir Yemek API entegrasyonu (login + POS bağlantısı)",
    "depends": ["base", "point_of_sale", "pos_restaurant"],

    "data": [
        "views/getir_api_views.xml",
        "security/ir.model.access.csv",
        "views/pos_order_inherit_views.xml",
    ],

    "assets": {
        "point_of_sale.assets": [
            "getir_connector/static/src/js/pos_getir_order.js",
            "getir_connector/static/src/xml/pos_order_ingerit.xml",
        ],
    },

    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
