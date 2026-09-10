"""
Servicio de Aprovisionamiento Automático
=========================================
Reemplaza el trabajo manual de activar_cliente.py + editar clientes.json +
configurar el número de Twilio a mano.

Se dispara desde app/api/webhooks/payments.py cuando:
  - MercadoPago confirma que una suscripción quedó "authorized" (arrancó el trial)
  - LemonSqueezy confirma el equivalente

Hace, en orden:
  1. Genera una peluqueria_key única
  2. Compra un número de Twilio (US, igual que tu número actual +1262...,
     así evitamos el trámite de "bundle regulatorio" que pide Twilio para
     números locales de Argentina)
  3. Registra ese número como WhatsApp Sender bajo tu WABA ya verificada
     (Senders API v2 — queda en estado OFFLINE/PENDING unos minutos hasta
     que Meta lo aprueba, eso NO lo podemos acelerar)
  4. Crea un Google Calendar nuevo (usando el master_token que ya usás
     para todos los clientes — no hace falta que el cliente autorice nada)
  5. Arma la config completa del bot con los datos que ya cargó el cliente
     en el formulario, y la guarda en Mongo (peluquerias_config)
  6. Te avisa a vos por WhatsApp

⚠️ PUNTOS A VERIFICAR ANTES DE PRODUCCIÓN (no pude probarlos en vivo,
no tengo acceso de red a Twilio/MercadoPago/Google desde donde escribo esto):

  - El campo `profile` del payload de Senders API v2 (nombre del negocio,
    categoría, descripción) — confirmé sender_id/configuration/webhook
    contra la documentación actual de Twilio, pero no el detalle fino de
    `profile`. Antes de ir a producción, hacé una prueba con UN número y
    mirá la respuesta real de la API para ajustar esos nombres de campo
    si hace falta.
  - twilio==8.11.0 (tu requirements.txt) es de fines de 2023, probablemente
    NO tenga helpers para la Senders API v2 (es muy nueva). Por eso acá
    pego contra el endpoint REST directo con `requests` en vez del SDK.
  - La compra de números por API consume dinero real de tu cuenta de
    Twilio apenas se ejecuta — probalo primero en un número de test o con
    un tope de gasto configurado en Twilio.
"""

import os
import re
import json
import unicodedata
from datetime import datetime, timedelta

import requests
from twilio.rest import Client as TwilioClient

from app.core.database import (
    clientes_collection,
    guardar_config_peluqueria,
    eliminar_config_peluqueria,
)
from app.services.whatsapp_service import whatsapp_service

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest
except ImportError:
    build = None


DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


# ==================== 1. PELUQUERIA KEY ====================

def generar_peluqueria_key(nombre_negocio: str, cliente_id: str) -> str:
    """Genera un key legible y único, ej: 'peluqueria_el_estilo_a1b2'."""
    texto = unicodedata.normalize("NFKD", nombre_negocio or "negocio")
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-zA-Z0-9]+", "_", texto).strip("_").lower()
    texto = texto[:40] or "negocio"
    sufijo = str(cliente_id)[-4:]
    return f"{texto}_{sufijo}"


# ==================== 2. PARSEO DE HORARIOS Y SERVICIOS ====================
# El formulario junta horarios/servicios como texto libre (lo que tipeó el
# cliente en el paso 2), pero el bot necesita una estructura por día.
# Primero probamos con reglas simples (rápido, gratis) y si no entendemos
# el texto, devolvemos un horario por defecto en vez de fallar.
# Si más adelante querés algo más robusto para texto raro, se puede pasar
# por Claude (Haiku) como hacés en MineCore — dejé el gancho comentado
# más abajo (`_parsear_con_claude`) para cuando quieras sumar ANTHROPIC_API_KEY.

HORARIO_DEFAULT = {d: [["09:00", "19:00"]] if d != "domingo" else [] for d in DIAS_SEMANA}

_RANGO_DIAS = {
    "lunes a viernes": ["lunes", "martes", "miercoles", "jueves", "viernes"],
    "lunes a sabado": ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"],
    "lunes a sábado": ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"],
}


def _normalizar_texto(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    return t.lower().strip()


def parsear_horarios(texto: str) -> dict:
    """
    Convierte texto tipo:
        "Lunes a Viernes: 9:00 - 19:00\\nSábados: 9:00 - 14:00"
    en:
        {"lunes": [["09:00","19:00"]], ..., "sabado": [["09:00","14:00"]], "domingo": []}

    Si no logra parsear ninguna línea, devuelve HORARIO_DEFAULT (mejor un
    horario razonable que dejar el negocio sin horarios cargados).
    """
    resultado = {}
    if not texto:
        return dict(HORARIO_DEFAULT)

    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    patron_hora = re.compile(r"(\d{1,2}):?(\d{2})?\s*-\s*(\d{1,2}):?(\d{2})?")

    for linea in lineas:
        linea_norm = _normalizar_texto(linea)
        match_hora = patron_hora.search(linea_norm)
        if not match_hora:
            continue

        h1, m1, h2, m2 = match_hora.groups()
        inicio = f"{int(h1):02d}:{m1 or '00'}"
        fin = f"{int(h2):02d}:{m2 or '00'}"

        dias_de_la_linea = []
        for patron, dias in _RANGO_DIAS.items():
            if patron in linea_norm:
                dias_de_la_linea = dias
                break
        if not dias_de_la_linea:
            for dia in DIAS_SEMANA:
                dia_singular = dia if dia != "sabado" else "sabado"
                if dia in linea_norm or (dia == "sabado" and "sabado" in linea_norm) or (dia == "miercoles" and "miercoles" in linea_norm):
                    dias_de_la_linea.append(dia)

        for dia in dias_de_la_linea:
            resultado.setdefault(dia, []).append([inicio, fin])

    for dia in DIAS_SEMANA:
        resultado.setdefault(dia, [] if dia == "domingo" else HORARIO_DEFAULT[dia])

    if not any(resultado.get(d) for d in DIAS_SEMANA):
        print("⚠️ No se pudo interpretar el texto de horarios, uso default")
        return dict(HORARIO_DEFAULT)

    return resultado


def parsear_servicios(texto: str) -> list:
    """
    Convierte texto tipo:
        "Corte de cabello - $5.000\\nTinte completo - $12.000\\nBarba - $3.000"
    en:
        [{"nombre": "Corte de cabello", "precio": 5000, "duracion": 30}, ...]

    duracion queda en 30 min por default (el formulario no lo pide hoy;
    el cliente lo puede ajustar después).
    """
    servicios = []
    if not texto:
        return servicios

    patron = re.compile(r"^(.+?)\s*[-–:]\s*\$?\s*([\d.,]+)")
    for linea in texto.split("\n"):
        linea = linea.strip()
        if not linea:
            continue
        m = patron.match(linea)
        if not m:
            servicios.append({"nombre": linea, "precio": 0, "duracion": 30})
            continue
        nombre = m.group(1).strip()
        precio_str = m.group(2).replace(".", "").replace(",", "")
        try:
            precio = int(precio_str)
        except ValueError:
            precio = 0
        servicios.append({"nombre": nombre, "precio": precio, "duracion": 30})

    return servicios


# ==================== 3. GOOGLE CALENDAR ====================

def crear_calendario_google(nombre_negocio: str, timezone: str) -> str | None:
    """
    Crea un calendario nuevo (secundario) bajo tu cuenta master, la misma
    que ya usás para cliente_001 y dev_local (mismo tokens/master_token.json).
    No requiere que el cliente autorice nada — es un calendario TUYO,
    dedicado a ese negocio.

    Returns:
        calendar_id (ej: "abc123...@group.calendar.google.com") o None si falló.
    """
    if build is None:
        print("❌ Librerías de Google no disponibles")
        return None

    token_path = "tokens/master_token.json"
    if not os.path.exists(token_path):
        print(f"❌ No se encontró {token_path}")
        return None

    try:
        creds = Credentials.from_authorized_user_file(
            token_path, ["https://www.googleapis.com/auth/calendar"]
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        service = build("calendar", "v3", credentials=creds)

        calendario = service.calendars().insert(body={
            "summary": nombre_negocio,
            "timeZone": timezone,
        }).execute()

        calendar_id = calendario["id"]
        print(f"✅ Calendario creado para {nombre_negocio}: {calendar_id}")
        return calendar_id

    except Exception as e:
        print(f"❌ Error creando calendario para {nombre_negocio}: {e}")
        return None


# ==================== 4. TWILIO: COMPRAR NÚMERO ====================

def comprar_numero_twilio(pais: str = "US") -> str | None:
    """
    Compra un número de Twilio con capacidad SMS+Voice (necesaria para
    verificar el sender de WhatsApp). Por default en US, igual que tu
    número actual, para no depender del bundle regulatorio que pide
    Twilio para números locales de Argentina.

    Returns:
        Número en formato E.164 (ej "+15017122661") o None si falló.
    """
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        print("❌ Faltan credenciales de Twilio")
        return None

    client = TwilioClient(sid, token)

    try:
        disponibles = client.available_phone_numbers(pais).local.list(
            sms_enabled=True, voice_enabled=True, limit=1
        )
        if not disponibles:
            print(f"❌ No hay números disponibles en {pais}")
            return None

        numero_elegido = disponibles[0].phone_number

        numero_comprado = client.incoming_phone_numbers.create(
            phone_number=numero_elegido,
        )
        print(f"✅ Número Twilio comprado: {numero_comprado.phone_number}")
        return numero_comprado.phone_number

    except Exception as e:
        print(f"❌ Error comprando número de Twilio: {e}")
        return None


def liberar_numero_twilio(numero: str) -> bool:
    """Da de baja un número de Twilio (para reusar el gasto si el cliente cancela en trial)."""
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    client = TwilioClient(sid, token)

    try:
        for numero_twilio in client.incoming_phone_numbers.list(phone_number=numero):
            numero_twilio.delete()
            print(f"✅ Número {numero} liberado")
            return True
        print(f"⚠️ No se encontró el número {numero} para liberar")
        return False
    except Exception as e:
        print(f"❌ Error liberando número {numero}: {e}")
        return False


# ==================== 5. TWILIO: SENDERS API v2 (WhatsApp) ====================

SENDERS_API_URL = "https://messaging.twilio.com/v2/Channels/Senders"


def registrar_whatsapp_sender(numero: str, nombre_negocio: str) -> dict | None:
    """
    Registra el número como WhatsApp Sender bajo tu WABA ya verificada.
    Usa la Senders API v2 directo por REST (el SDK twilio==8.11.0 es
    anterior a esta API). Requiere TWILIO_WABA_ID en el entorno.

    ⚠️ Revisá los nombres exactos de los campos de "profile" contra la
    documentación de Twilio antes de confiar en esto en producción — ver
    nota al principio del archivo.

    Returns:
        dict con {"sid": ..., "status": ...} o None si falló.
    """
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    waba_id = os.getenv("TWILIO_WABA_ID")
    webhook_base = os.getenv("WEBHOOK_URL", "")  # URL pública de este backend en Railway

    if not waba_id:
        print("❌ Falta TWILIO_WABA_ID en el entorno")
        return None

    payload = {
        "sender_id": f"whatsapp:{numero}",
        "configuration": {
            "waba_id": waba_id,
        },
        "webhook": {
            "callback_url": f"{webhook_base}/api/webhook",
            "callback_method": "POST",
        },
        "profile": {
            # VERIFICAR: nombres de campo exactos contra la doc de Twilio
            "name": nombre_negocio,
        },
    }

    try:
        resp = requests.post(
            SENDERS_API_URL,
            auth=(sid, token),
            json=payload,
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            print(f"❌ Error registrando sender: {resp.status_code} {resp.text}")
            return None

        data = resp.json()
        print(f"✅ Sender registrado: {data.get('sid')} — estado inicial: {data.get('status')}")
        return {"sid": data.get("sid"), "status": data.get("status")}

    except Exception as e:
        print(f"❌ Error inesperado registrando sender: {e}")
        return None


def consultar_estado_sender(sender_sid: str) -> str | None:
    """GET del sender para chequear si ya pasó a ONLINE. Podés llamarlo desde
    un cron/reintento, o mejor, configurar el status callback de Twilio para
    que te avise solo (ver 'webhook' en el payload de arriba)."""
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    try:
        resp = requests.get(f"{SENDERS_API_URL}/{sender_sid}", auth=(sid, token), timeout=15)
        if resp.ok:
            return resp.json().get("status")
    except Exception as e:
        print(f"❌ Error consultando sender {sender_sid}: {e}")
    return None


# ==================== 6. ORQUESTACIÓN ====================

def aprovisionar_cliente(cliente_id: str) -> bool:
    """
    Punto de entrada principal. Llamalo desde el webhook cuando el pago
    quede autorizado (ver app/api/webhooks/payments.py).
    """
    from bson import ObjectId

    cliente = clientes_collection.find_one({"_id": ObjectId(cliente_id)})
    if not cliente:
        print(f"❌ No se encontró cliente {cliente_id} para aprovisionar")
        return False

    if cliente.get("bot_configurado"):
        print(f"ℹ️ Cliente {cliente_id} ya estaba aprovisionado, no repito")
        return True

    nombre_negocio = cliente.get("nombre_negocio", "Negocio")
    timezone = cliente.get("timezone", "America/Argentina/Buenos_Aires")

    peluqueria_key = generar_peluqueria_key(nombre_negocio, cliente_id)

    # 1) Calendario
    calendar_id = crear_calendario_google(nombre_negocio, timezone)

    # 2) Número + sender de WhatsApp
    numero = comprar_numero_twilio()
    sender_info = registrar_whatsapp_sender(numero, nombre_negocio) if numero else None

    # 3) Horarios y servicios estructurados
    horarios = parsear_horarios(cliente.get("horarios", ""))
    servicios = parsear_servicios(cliente.get("servicios", ""))

    peluqueros = []
    for p in cliente.get("peluqueros", []):
        peluqueros.append({
            "nombre": p.get("nombre", ""),
            "telefono": p.get("telefono", ""),
            "horarios": horarios,  # por default heredan el horario del negocio
        })

    config_bot = {
        "_key": peluqueria_key,
        "nombre": nombre_negocio,
        "numero_twilio": numero,
        "twilio_sender_sid": sender_info.get("sid") if sender_info else None,
        "twilio_sender_status": sender_info.get("status") if sender_info else "error",
        "calendar_id": calendar_id,
        "token_file": "tokens/master_token.json",
        "owner_email": cliente.get("email", ""),
        "timezone": timezone,
        "idioma": "es",
        "moneda": "ARS" if cliente.get("plan") == "argentina" else "USD",
        "ubicacion": cliente.get("ubicacion", ""),
        "horarios": horarios,
        "faq": {},
        "servicios": servicios,
        "peluqueros": peluqueros,
        "requiere_pago": False,  # se activa solo cuando conecte su MercadoPago
        "proveedor_pago": "mercadopago",
        "activo": True,
    }

    guardar_config_peluqueria(peluqueria_key, config_bot)

    clientes_collection.update_one(
        {"_id": ObjectId(cliente_id)},
        {"$set": {
            "peluqueria_key": peluqueria_key,
            "bot_configurado": True,
            "actualizado_en": datetime.utcnow(),
        }},
    )

    # Avisos
    admin = os.getenv("ADMIN_WHATSAPP", "")
    if admin:
        estado_num = "✅ listo" if numero else "❌ FALLÓ LA COMPRA DEL NÚMERO — revisar a mano"
        estado_cal = "✅ listo" if calendar_id else "❌ falló, revisar a mano"
        whatsapp_service.enviar_mensaje(
            f"🤖 *Aprovisionamiento automático*\n\n"
            f"🏪 {nombre_negocio} ({peluqueria_key})\n"
            f"📱 Número: {numero or '—'} — {estado_num}\n"
            f"📅 Calendario: {estado_cal}\n"
            f"📶 Estado del sender de WhatsApp: {sender_info.get('status') if sender_info else 'error'} "
            f"(puede tardar unos minutos en pasar a ONLINE)",
            f"whatsapp:{admin}",
        )

    telefono_dueno = cliente.get("telefono", "")
    if telefono_dueno and numero:
        webhook_base = os.getenv("WEBHOOK_URL", "")
        link_conectar_mp = f"{webhook_base}/api/pagos/conectar/mercadopago?peluqueria_key={peluqueria_key}"
        whatsapp_service.enviar_mensaje(
            f"🎉 ¡Tu bot de {nombre_negocio} ya está casi listo!\n\n"
            f"En unos minutos vas a poder recibir turnos por WhatsApp en "
            f"tu nuevo número: {numero}\n\n"
            f"Un paso más: si querés que el bot le pida una seña a tus "
            f"clientes al reservar (va directo a tu cuenta, no pasa por "
            f"nosotros), conectá tu MercadoPago acá:\n{link_conectar_mp}",
            f"whatsapp:{telefono_dueno}",
        )

    return bool(numero and calendar_id)


def liberar_recursos_si_estaba_en_trial(cliente_id: str) -> None:
    """
    Se llama cuando una suscripción se cancela/pausa. Si el cliente
    canceló ANTES de haber tenido un cobro exitoso (o sea, seguía en
    trial), liberamos el número de Twilio y damos de baja su config del
    bot para poder reusar el número en el próximo cliente.

    Si ya había tenido cobros reales (`ultimo_cobro` seteado), NO lo
    tocamos automáticamente — eso lo maneja verificar_suscripcion.py
    con el período de gracia habitual.
    """
    from bson import ObjectId

    cliente = clientes_collection.find_one({"_id": ObjectId(cliente_id)})
    if not cliente:
        return

    ya_tuvo_cobro_real = bool(cliente.get("ultimo_cobro"))
    if ya_tuvo_cobro_real:
        print(f"ℹ️ Cliente {cliente_id} ya había pagado antes, no libero recursos")
        return

    numero = cliente.get("numero_twilio") or None
    peluqueria_key = cliente.get("peluqueria_key")

    # El numero_twilio se guardó en peluquerias_config, no en clientes_collection —
    # lo buscamos ahí si hace falta
    if not numero and peluqueria_key:
        from app.core.database import peluquerias_config_collection
        config = peluquerias_config_collection.find_one({"_key": peluqueria_key})
        numero = config.get("numero_twilio") if config else None

    if numero:
        liberar_numero_twilio(numero)

    if peluqueria_key:
        eliminar_config_peluqueria(peluqueria_key)

    print(f"✅ Recursos liberados para cliente {cliente_id} (canceló durante el trial)")
