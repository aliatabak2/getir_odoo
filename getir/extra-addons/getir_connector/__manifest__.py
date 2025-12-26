{
    "name": "Getir Connector",
    "version": "18.0.3.0.0",
    "summary": "Full Getir Yemek Integration for Odoo 18 (Orders, Menu Sync, Status, POS)",
    "description": """
        Getir Yemek entegrasyonu:
        - Sipariş alma ve yönetimi (verify, prepare, handover, deliver)
        - Menü senkronizasyonu (Getir'den ürünleri çekme)
        - POS status kontrolü
        - Restoran açık/kapalı/yoğunluk durumu
        - Ürün stok durumu yönetimi
        - Fiş/fatura yükleme
        - Webhook desteği
    """,
    "author": "Waresky",
    "category": "Point of Sale",
    "website": "https://waresky.com",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "mail",
        "point_of_sale",
        "pos_restaurant",
        "pos_sale",
        "product",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/getir_cancel_views.xml",
        "views/getir_menu_sync_views.xml",
        "views/getir_api_views.xml",
        "views/getir_order_views.xml",
        "views/getir_log_views.xml",
        "views/getir_menu_views.xml",
    ],
    "assets": {
        "point_of_sale.assets": [
            "getir_connector/static/src/js/getir_cancel_popup.js",
            "getir_connector/static/src/js/pos_getir_order.js",
            "getir_connector/static/src/xml/getir_cancel_popup.xml",
            "getir_connector/static/src/xml/pos_order_inherit.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
