
"""
Lista todos los clientes configurados
útil para ver un resumen rápido de tus clientes
"""

import json

with open("clientes.json", "r", encoding="utf-8") as f:
    clientes = json.load(f)

print("📋 CLIENTES CONFIGURADOS")
print("="*60)

for key, config in clientes.items():
    print(f"\n🔑 ID: {key}")
    print(f"📍 Nombre: {config['nombre']}")
    print(f"📅 Calendar: {config['calendar_id']}")
    print(f"🔐 Token: {config['token_file']}")
    print(f"✂️ Servicios: {len(config.get('servicios', []))}")
    if 'owner_email' in config:
        print(f"📧 Email: {config['owner_email']}")

print(f"\n📊 Total: {len(clientes)} clientes")