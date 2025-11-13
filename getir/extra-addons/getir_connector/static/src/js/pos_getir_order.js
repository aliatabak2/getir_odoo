/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async _loadInitialOrders() {
        await this._super(...arguments);
        // Getir siparişleriyle ilgili log
        console.log("Getir siparişleri yükleniyor...");

        // Filtre: 'Getir-' ref içeren siparişleri al
        const getirOrders = this.models['pos.order'].records.filter(order => order.ref && order.ref.startsWith("Getir-"));
        console.log("Getir siparişleri bulundu:", getirOrders.length);
        // POS Store’a ekle (görünür hale getirmek için)
        for (const o of getirOrders) {
            if (!this.db.get_order(o.id)) {
                this.db.add_order(o.id, o);
            }
        }
    },
});
