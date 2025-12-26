"""
Migration script to update existing Getir cancel reasons with correct API IDs.
Run this from Odoo shell or execute as a server action after module update.

Usage:
1. Open Odoo shell: python odoo-bin shell -d <database_name>
2. Copy and paste this script
"""

# Cancel reason ID mapping - old placeholder IDs to actual Getir API IDs
CANCEL_REASON_MAPPING = {
    'out_of_stock': '5c5b49a768f6a45d427f0a8e',      # Restoranda ürün eksik
    'kitchen_busy': '5c5b49b068f6a45d427f0a8f',      # Restoran yoğun
    'closing': '5c5b495768f6a45d427f0a8d',           # Restoran kapalı
    'technical_issue': '5f05b13f2765e85c5d0432d3',   # Restoran teknik problem
    'other': None,  # Bu kayıt silinecek veya başka bir ID ile değiştirilecek
}

# New cancel reasons to add
NEW_CANCEL_REASONS = [
    {'name': 'Müşteri adresi restoran servis alanı dışında', 'getir_reason_id': '5e1469f7916c7a55cfc2aede', 'sequence': 5},
    {'name': 'Restoranda kurye yok, müsait değil', 'getir_reason_id': '5f05b1392765e85c5d0432d2', 'sequence': 6},
    {'name': 'Hava muhalefeti', 'getir_reason_id': '5f0875342ce13c10cbf1c0e6', 'sequence': 7},
    {'name': 'Sipariş minimum sepet tutarı altında', 'getir_reason_id': '6088226bdaa34255a5693e23', 'sequence': 8},
]

def migrate_cancel_reasons(env):
    """Mevcut iptal sebeplerini gerçek Getir API ID'leri ile güncelle"""
    CancelReason = env['getir.cancel.reason']
    
    print("İptal sebepleri güncelleniyor...")
    
    # Update existing reasons
    for old_id, new_id in CANCEL_REASON_MAPPING.items():
        if new_id is None:
            continue
            
        reason = CancelReason.search([('getir_reason_id', '=', old_id)], limit=1)
        if reason:
            reason.write({'getir_reason_id': new_id})
            print(f"  ✓ Güncellendi: {reason.name} -> {new_id}")
    
    # Delete 'other' reason if exists (not a valid Getir reason)
    other_reason = CancelReason.search([('getir_reason_id', '=', 'other')], limit=1)
    if other_reason:
        other_reason.unlink()
        print("  ✓ 'Diğer' sebebi silindi (geçerli Getir ID'si yok)")
    
    # Add new reasons
    for reason_data in NEW_CANCEL_REASONS:
        existing = CancelReason.search([('getir_reason_id', '=', reason_data['getir_reason_id'])], limit=1)
        if not existing:
            CancelReason.create(reason_data)
            print(f"  ✓ Eklendi: {reason_data['name']}")
    
    env.cr.commit()
    print("\n✓ Tüm iptal sebepleri güncellendi!")

# Run migration
if 'env' in dir():
    migrate_cancel_reasons(env)
else:
    print("Bu script Odoo shell içinde çalıştırılmalıdır.")
    print("Kullanım: python odoo-bin shell -d <database_name>")
