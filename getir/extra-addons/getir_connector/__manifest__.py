{
    "name": "getir_connector",
    "version": "18.0.1.0.0",
    "summary": "Full Getir Yemek Integration for Odoo 18 (Orders, Menu, Status, POS Sync)",
    "author": "Waresky",
    "category": "Point of Sale",
    "website": "https://waresky.com",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "point_of_sale",
        "pos_restaurant",
        "pos_sale",
        "product",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/getir_api_views.xml",
        "views/getir_order_views.xml",
        "views/getir_log_views.xml",
        "views/getir_menu_views.xml",
    ],
  "assets": {
    "point_of_sale.assets": [
        "getir_connector/static/src/js/pos_getir_order.js",
        "getir_connector/static/src/xml/pos_order_inherit.xml",
    ],
},

    "installable": True,
    "application": True,
    "auto_install": False,
}
