"""
Script para activar un cliente nuevo en MongoDB
Ejecutalo cuando hayas configurado el bot y esté listo para empezar la prueba.

Uso:
    python scripts/activar_cliente.py

Lo que hace:
    1. Muestra los clientes pendientes en MongoDB
    2. Te deja elegir cuál activar
    3. Le asigna la peluqueria_key del clientes.json
    4. Pone estado "pagado" + trial_inicio = ahora
    5. El bot empieza a funcionar y los 7 días arrancan
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv()

# ── Conexión MongoDB ─────────────────────────────────────────
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["peluqueria_bot"]
clientes_collection = db["clientes"]

# ── Cargar clientes.json para obtener las peluqueria_keys ────
def cargar_peluquerias():
    for ruta in ["config/clientes.json", "clientes.json"]:
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                return json.load(f)
    print("❌ No se encontró clientes.json")
    return {}


def mostrar_clientes_pendientes():
    """Muestra todos los clientes que aún no fueron activados"""
    pendientes = list(clientes_collection.find({
        "$or": [
            {"estado_pago": "pendiente"},
            {"trial_inicio": {"$exists": False}},
            {"peluqueria_key": {"$exists": False}},
        ]
    }).sort("creado_en", -1))

    if not pendientes:
        print("\n✅ No hay clientes pendientes de activar.")
        return []

    print(f"\n📋 CLIENTES PENDIENTES DE ACTIVAR ({len(pendientes)}):")
    print("=" * 60)

    for i, c in enumerate(pendientes):
        creado = c.get("creado_en", "?")
        if isinstance(creado, datetime):
            creado = creado.strftime("%d/%m/%Y %H:%M")

        print(f"\n[{i + 1}] {c.get('nombre', '?')} {c.get('apellido', '?')}")
        print(f"    🏪 {c.get('nombre_negocio', '?')}")
        print(f"    📱 {c.get('telefono', '?')}")
        print(f"    ✉️  {c.get('email', '?')}")
        print(f"    💰 Plan: {c.get('plan', '?').upper()}")
        print(f"    📍 {c.get('ubicacion', '?')}")
        print(f"    📅 Registrado: {creado}")
        print(f"    🔑 ID: {c['_id']}")

    return pendientes


def activar_cliente():
    print("🚀 ACTIVAR CLIENTE - TurnosBot")
    print("=" * 60)

    pendientes = mostrar_clientes_pendientes()
    if not pendientes:
        return

    # Elegir cliente
    print("\n¿Qué número de cliente querés activar? (o 0 para salir): ", end="")
    try:
        eleccion = int(input().strip())
    except ValueError:
        print("❌ Número inválido")
        return

    if eleccion == 0:
        print("👋 Saliendo...")
        return

    if eleccion < 1 or eleccion > len(pendientes):
        print("❌ Número fuera de rango")
        return

    cliente = pendientes[eleccion - 1]
    cliente_id = cliente["_id"]

    print(f"\n✅ Seleccionado: {cliente.get('nombre')} {cliente.get('apellido')} - {cliente.get('nombre_negocio')}")

    # Elegir peluqueria_key
    peluquerias = cargar_peluquerias()
    if not peluquerias:
        print("❌ No se pudo cargar clientes.json")
        return

    # Filtrar las que no son demo ni dev
    keys_disponibles = [k for k in peluquerias.keys() if k not in ("dev_local", "cliente_001")]
    keys_disponibles_todas = list(peluquerias.keys())

    print(f"\n🔑 ¿Qué peluqueria_key le asignás? (del clientes.json)")
    print("   Esto conecta al cliente con su configuración del bot\n")

    for i, key in enumerate(keys_disponibles_todas):
        config = peluquerias[key]
        print(f"   [{i + 1}] {key} → {config.get('nombre', '?')}")

    print(f"\n   O escribí una key nueva que vayas a agregar al clientes.json")
    print("   Peluqueria key: ", end="")
    peluqueria_key = input().strip()

    if not peluqueria_key:
        print("❌ La peluqueria_key no puede estar vacía")
        return

    # Confirmar
    print(f"\n{'=' * 60}")
    print(f"📋 RESUMEN DE ACTIVACIÓN:")
    print(f"{'=' * 60}")
    print(f"Cliente:        {cliente.get('nombre')} {cliente.get('apellido')}")
    print(f"Negocio:        {cliente.get('nombre_negocio')}")
    print(f"Teléfono:       {cliente.get('telefono')}")
    print(f"Plan:           {cliente.get('plan', '?').upper()}")
    print(f"Peluqueria key: {peluqueria_key}")
    print(f"Trial inicio:   AHORA ({datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC)")
    print(f"Trial vence:    En 7 días")
    print(f"{'=' * 60}")
    print("\n¿Confirmás la activación? (s/n): ", end="")

    if input().strip().lower() != "s":
        print("❌ Operación cancelada")
        return

    # Activar en MongoDB
    ahora = datetime.utcnow()
    resultado = clientes_collection.update_one(
        {"_id": ObjectId(cliente_id)},
        {"$set": {
            "estado_pago":       "pagado",
            "peluqueria_key":    peluqueria_key,
            "trial_inicio":      ahora,
            "suscripcion_activa": False,
            "bot_configurado":   True,
            "gracia_inicio":     None,
            "actualizado_en":    ahora,
        }}
    )

    if resultado.modified_count > 0:
        print(f"\n✅ ¡Cliente activado exitosamente!")
        print(f"   El bot ya puede usarse para '{peluqueria_key}'")
        print(f"   Los 7 días de prueba arrancaron ahora")
        print(f"\n📋 PRÓXIMOS PASOS:")
        print(f"   1. Verificá que '{peluqueria_key}' esté en tu clientes.json")
        print(f"   2. Asegurate que el número de Twilio esté configurado")
        print(f"   3. Avisale al cliente que ya puede empezar a usarlo")
        print(f"\n⏰ El bot dejará de funcionar si no paga en 7 días")
        print(f"   (te va a llegar aviso por WhatsApp cuando venza)")
    else:
        print(f"\n❌ No se pudo actualizar el cliente. Verificá el ID.")


if __name__ == "__main__":
    try:
        activar_cliente()
    except KeyboardInterrupt:
        print("\n\n❌ Operación cancelada")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()