/** @odoo-module **/

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { useState } from "@odoo/owl";

/**
 * Getir sipariş iptali için popup
 * İptal sebebi seçimi ve not girişi sağlar
 */
export class GetirCancelPopup extends AbstractAwaitablePopup {
    static template = "getir_connector.GetirCancelPopup";
    static defaultProps = {
        confirmText: "Siparişi İptal Et",
        cancelText: "Vazgeç",
        title: "Getir Sipariş İptali",
        body: "",
    };

    setup() {
        super.setup();
        this.state = useState({
            selectedReasonId: "5c5b49a768f6a45d427f0a8e",
            note: "",
        });

        // İptal sebepleri - Getir panel'deki iki sebep
        this.cancelReasons = [
            {
                id: "5c5b49a768f6a45d427f0a8e",
                name: "Restoranda ürün eksik",
            },
            {
                id: "5f05b13f2765e85c5d0432d3",
                name: "Restoran teknik problem yaşıyor",
            },
        ];
    }

    selectReason(reasonId) {
        this.state.selectedReasonId = reasonId;
    }

    getPayload() {
        return {
            confirmed: true,
            reasonId: this.state.selectedReasonId,
            note: this.state.note,
        };
    }

    async confirm() {
        this.props.close(this.getPayload());
    }

    cancel() {
        this.props.close({ confirmed: false });
    }
}

console.log("[GETIR] GetirCancelPopup modülü yüklendi");
