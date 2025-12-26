/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { GetirCancelPopup } from "@getir_connector/js/getir_cancel_popup";

// PosStore patch - Getir siparişlerini yükle
patch(PosStore.prototype, {
    async _loadInitialOrders() {
        await super._loadInitialOrders(...arguments);

        console.log("[GETIR] POS initial orders yüklendi, Getir siparişleri filtreleniyor...");

        const posOrdersModel = this.models.find(m => m.model === "pos.order");

        if (!posOrdersModel) {
            console.warn("[GETIR] this.models['pos.order'] bulunamadı.");
            return;
        }

        const allOrders = posOrdersModel.records || [];

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

// ControlButtons patch - Getir Actions menüsü
patch(ControlButtons.prototype, {
    /**
     * Mevcut sipariş Getir siparişi mi kontrol et
     */
    isGetirOrder() {
        const order = this.pos.get_order();
        if (!order) return false;

        const posRef = order.pos_reference || order.name || "";
        const isGetir = order.is_getir_order ||
            (typeof posRef === "string" && posRef.indexOf("Getir-") === 0);

        console.log("[GETIR] isGetirOrder check:", posRef, "->", isGetir);
        return isGetir;
    },

    /**
     * Getir iptal popup'ını aç
     */
    async openGetirCancelPopup() {
        const order = this.pos.get_order();
        if (!order) {
            this.notification.add(_t("Sipariş bulunamadı"), { type: "danger" });
            return;
        }

        const posRef = order.pos_reference || order.name || "";
        console.log("[GETIR] İptal popup açılıyor:", posRef);

        // Popup'ı aç
        const { confirmed, reasonId, note } = await this.popup.add(GetirCancelPopup, {
            title: _t("Getir Sipariş İptali"),
            body: posRef,
        });

        if (!confirmed) {
            console.log("[GETIR] İptal vazgeçildi");
            return;
        }

        console.log("[GETIR] İptal onaylandı:", reasonId, note);

        try {
            // Backend RPC çağrısı
            const result = await this.env.services.orm.call(
                "pos.order",
                "cancel_getir_order_with_reason",
                [[order.id], reasonId, note]
            );

            if (result && result.success) {
                this.notification.add(_t("Getir siparişi iptal edildi: ") + posRef, {
                    type: "success",
                });
                // Siparişi kaldır
                this.pos.removeOrder(order);
            } else {
                this.notification.add(_t("Sipariş iptal edilemedi: ") + (result?.error || ""), {
                    type: "danger",
                });
            }
        } catch (error) {
            console.error("[GETIR] İptal hatası:", error);
            this.notification.add(_t("Sipariş iptal edilemedi: ") + (error.message || error), {
                type: "danger",
            });
        }
    },
});

console.log("[GETIR] POS Getir modülü yüklendi - ControlButtons patch eklendi");
