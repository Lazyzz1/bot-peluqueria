"""
Script para cancelar o reactivar un cliente manualmente.

Cuando usarlo:
- El cliente pidio cancelar y no sabe como hacerlo solo
- Queres dar de baja por incumplimiento de terminos
- MercadoPago no mando el webhook de cancelacion
- Queres reactivar un cliente que estaba cancelado
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["peluqueria_bot"]
col = db["clientes"]


def listar_activos():
    clientes = list(col.find({
        "estado_pago": {"$in": ["pagado", "pendiente"]},
        "bot_configurado": True,
    }).sort("creado_en", -1))

    if not clientes:
        print("\n No hay clientes activos.")
        return []

    print(f"\n CLIENTES ACTIVOS ({len(clientes)}):")
    print("=" * 60)
    for i, c in enumerate(clientes):
        suscripcion = c.get("suscripcion_activa", False)
        trial_inicio = c.get("trial_inicio")
        gracia = c.get("gracia_inicio")

        if trial_inicio and not suscripcion:
            dias = (datetime.utcnow() - trial_inicio).days
            estado_display = f"TRIAL (dia {dias}/7)"
        elif suscripcion:
            estado_display = "ACTIVO"
        elif gracia:
            estado_display = "EN GRACIA"
        else:
            estado_display = c.get("estado_pago", "?").upper()

        print(f"\n[{i + 1}] {c.get('nombre', '?')} {c.get('apellido', '?')}")
        print(f"    Negocio: {c.get('nombre_negocio', '?')}")
        print(f"    Key:     {c.get('peluqueria_key', 'sin asignar')}")
        print(f"    Tel:     {c.get('telefono', '?')}")
        print(f"    Plan:    {c.get('plan', '?').upper()}")
        print(f"    Estado:  {estado_display}")
    return clientes


def cancelar(cliente, motivo="Cancelacion manual"):
    ahora = datetime.utcnow()
    res = col.update_one(
        {"_id": ObjectId(cliente["_id"])},
        {"$set": {
            "estado_pago":        "cancelado",
            "suscripcion_activa": False,
            "cancelado_en":       ahora,
            "motivo_cancelacion": motivo,
            "actualizado_en":     ahora,
        }}
    )
    if res.modified_count > 0:
        print(f"\n Cliente cancelado: {cliente.get('nombre_negocio')}")
        print(f"   El bot deja de responder inmediatamente")
        print(f"   Motivo: {motivo}")
        # Avisar al dueno
        telefono = cliente.get("telefono", "")
        if telefono:
            try:
                from app.services.whatsapp_service import whatsapp_service
                nombre_negocio = cliente.get("nombre_negocio", "tu negocio")
                payment_url = cliente.get("payment_url", "https://turnosbot-landing.vercel.app/#pricing")
                mensaje = (
                    f"TurnosBot - Servicio cancelado\n\n"
                    f"El servicio de {nombre_negocio} fue cancelado.\n\n"
                    f"Si queres reactivarlo:\n"
                    f"{payment_url}\n\n"
                    f"Consultas: wa.me/5492974924147"
                )
                whatsapp_service.enviar_mensaje(mensaje, f"whatsapp:{telefono}")
                print(f"   Aviso enviado al cliente: {telefono}")
            except Exception as e:
                print(f"   No se pudo enviar WhatsApp: {e}")
    else:
        print(f"\n No se pudo cancelar.")


def reactivar(cliente):
    ahora = datetime.utcnow()
    res = col.update_one(
        {"_id": ObjectId(cliente["_id"])},
        {"$set": {
            "estado_pago":        "pagado",
            "suscripcion_activa": True,
            "gracia_inicio":      None,
            "cancelado_en":       None,
            "motivo_cancelacion": None,
            "actualizado_en":     ahora,
        }}
    )
    if res.modified_count > 0:
        print(f"\n Cliente reactivado: {cliente.get('nombre_negocio')}")
        print(f"   El bot vuelve a responder inmediatamente")
    else:
        print(f"\n No se pudo reactivar.")


def main():
    print("GESTION DE CLIENTES - TurnosBot")
    print("=" * 60)
    print("\nQue queres hacer?")
    print("1. Cancelar cliente")
    print("2. Reactivar cliente cancelado")
    print("0. Salir")
    print("\nOpcion: ", end="")

    try:
        accion = int(input().strip())
    except ValueError:
        print("Opcion invalida")
        return

    if accion == 0:
        return

    if accion == 1:
        clientes = listar_activos()
        if not clientes:
            return
        print("\nNumero de cliente a cancelar (0 salir): ", end="")
        try:
            n = int(input().strip())
        except ValueError:
            return
        if n == 0 or n > len(clientes):
            return
        c = clientes[n - 1]
        print(f"\nVas a CANCELAR: {c.get('nombre_negocio')}")
        print("Motivo (Enter = 'Cancelacion manual'): ", end="")
        motivo = input().strip() or "Cancelacion manual"
        print("Confirmas? (s/n): ", end="")
        if input().strip().lower() != "s":
            print("Cancelado")
            return
        cancelar(c, motivo)

    elif accion == 2:
        cancelados = list(col.find({"estado_pago": "cancelado"}).sort("cancelado_en", -1))
        if not cancelados:
            print("\n No hay clientes cancelados.")
            return
        print(f"\n CLIENTES CANCELADOS ({len(cancelados)}):")
        print("=" * 60)
        for i, c in enumerate(cancelados):
            fecha = c.get("cancelado_en", "?")
            if isinstance(fecha, datetime):
                fecha = fecha.strftime("%d/%m/%Y")
            print(f"\n[{i + 1}] {c.get('nombre_negocio', '?')}")
            print(f"    Cancelado: {fecha}")
            print(f"    Motivo: {c.get('motivo_cancelacion', '?')}")
        print("\nNumero de cliente a reactivar (0 salir): ", end="")
        try:
            n = int(input().strip())
        except ValueError:
            return
        if n == 0 or n > len(cancelados):
            return
        c = cancelados[n - 1]
        print(f"\nConfirmas reactivar: {c.get('nombre_negocio')}? (s/n): ", end="")
        if input().strip().lower() != "s":
            print("Cancelado")
            return
        reactivar(c)
    else:
        print("Opcion invalida")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelado")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()