/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async _loadInitialOrders() {
        // Önce orijinal sipariş yükleme mantığını çalıştır
        await super._loadInitialOrders(...arguments);

        console.log("[GETIR] POS initial orders yüklendi, Getir siparişleri filtreleniyor...");

        // backend’den gelen pos.order kayıtları
        const posOrdersModel = this.models.find(m => m.model === "pos.order");

        if (!posOrdersModel) {
            console.warn("[GETIR] this.models['pos.order'] bulunamadı.");
            return;
        }

        const allOrders = posOrdersModel.records || [];

        // Getir referanslı siparişler: ref veya pos_reference 'Getir-' ile başlıyorsa
        const getirOrders = allOrders.filter((order) => {
            const ref = order.ref || order.pos_reference || "";
            return typeof ref === "string" && ref.indexOf("Getir-") === 0;
        });

        console.log(`[GETIR] POS Store içinde bulunan Getir siparişi sayısı: ${getirOrders.length}`);

        for (const order of getirOrders) {
            if (!this.db.get_order(order.id)) {
                this.db.add_order(order.id, order);
            }
        }
    },
});
