"""
Configuración centralizada de la aplicación

⚠️ CAMBIO IMPORTANTE respecto al original:
PELUQUERIAS ya no se carga UNA sola vez desde config/clientes.json.
Ahora:
  1. Se carga clientes.json como "semilla" (sirve para dev_local y para
     no perder nada de lo que ya tenías a mano).
  2. Se combina con lo que haya en MongoDB (colección peluquerias_config),
     que es donde el aprovisionamiento automático va a escribir a los
     clientes nuevos.
  3. Un hilo en background refresca esa combinación cada cierto tiempo.

Esto es necesario porque antes, si agregabas un cliente a clientes.json
(o ahora, si el aprovisionamiento automático lo agrega a Mongo), el bot
corriendo en Railway no se enteraba hasta el próximo redeploy — todo el
código que usa `PELUQUERIAS[key]` sigue funcionando igual, porque
`PELUQUERIAS` sigue siendo el mismo objeto dict de siempre, solo que
ahora se actualiza en el lugar (in-place) en vez de crearse una sola vez.
"""
import os
import sys
import json
import threading
import time
from dotenv import load_dotenv
from zoneinfo import available_timezones

# Detectar modo de ejecución
MODO_DESARROLLO = 'run_local' in sys.argv[0] or os.getenv('FLASK_ENV') == 'development'

# Cargar variables de entorno según el modo
if MODO_DESARROLLO:
    print("=" * 60)
    print("🧪 MODO DESARROLLO ACTIVADO")
    print("=" * 60)
    load_dotenv('.env.local')
else:
    print("=" * 60)
    print("🚀 MODO PRODUCCIÓN")
    print("=" * 60)
    load_dotenv()


class Config:
    """Clase de configuración base"""

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')

    # Twilio/WhatsApp
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

    # Plantillas de WhatsApp
    USAR_PLANTILLAS = os.getenv("USAR_PLANTILLAS", "True").lower() == "true"
    TEMPLATE_CONFIRMACION = os.getenv("TEMPLATE_CONFIRMACION", "HXxxxxx")
    TEMPLATE_RECORDATORIO = os.getenv("TEMPLATE_RECORDATORIO", "HXxxxxx")
    TEMPLATE_NUEVO_TURNO = os.getenv("TEMPLATE_NUEVO_TURNO", "HXxxxxx")
    TEMPLATE_MODIFICADO = os.getenv("TEMPLATE_MODIFICADO", "HXxxxxx")

    # Google Calendar
    GOOGLE_SCOPES = ['https://www.googleapis.com/auth/calendar']

    # Archivos
    ARCHIVO_RECORDATORIOS = "recordatorios_enviados.json"
    ARCHIVO_ESTADOS = "user_states.json"
    ARCHIVO_CLIENTES = "clientes.json"

    # Directorios
    DIR_TOKENS = "tokens"
    DIR_CONFIG = "config"

    # MongoDB (opcional)
    MONGODB_URI = os.getenv("MONGODB_URI")
    MONGODB_DB = os.getenv("MONGODB_DB", "peluqueria_bot")

    # Redis (opcional)
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

    # Cada cuánto se refresca PELUQUERIAS desde Mongo (segundos)
    PELUQUERIAS_REFRESH_SEGUNDOS = int(os.getenv("PELUQUERIAS_REFRESH_SEGUNDOS", 60))

    @classmethod
    def validar(cls):
        """Valida que las configuraciones necesarias estén presentes"""
        if not all([cls.TWILIO_ACCOUNT_SID, cls.TWILIO_AUTH_TOKEN, cls.TWILIO_WHATSAPP_NUMBER]):
            raise ValueError("❌ Faltan variables de entorno de Twilio")

        if cls.USAR_PLANTILLAS:
            faltantes = [
                nombre for nombre, valor in {
                    "TEMPLATE_CONFIRMACION": cls.TEMPLATE_CONFIRMACION,
                    "TEMPLATE_RECORDATORIO": cls.TEMPLATE_RECORDATORIO,
                    "TEMPLATE_NUEVO_TURNO": cls.TEMPLATE_NUEVO_TURNO,
                    "TEMPLATE_MODIFICADO": cls.TEMPLATE_MODIFICADO,
                }.items() if not valor or valor == "HXxxxxx"
            ]
            if faltantes:
                print("⚠️ ADVERTENCIA: Faltan Content SIDs de WhatsApp:")
                for f in faltantes:
                    print(f"   - {f}")

        print("✅ Configuración validada correctamente")


def _validar_timezones(peluquerias: dict, origen: str):
    for cliente_id, config in peluquerias.items():
        tz = config.get("timezone")
        if not tz:
            print(f"⚠️ Cliente {cliente_id} ({origen}) no tiene timezone, se omite")
            continue
        if tz not in available_timezones():
            print(f"⚠️ Timezone inválido para {cliente_id} ({origen}): {tz}, se omite")


def cargar_clientes_json() -> dict:
    """Carga la semilla de clientes desde config/clientes.json (dev_local, etc.)"""
    ruta_clientes = os.path.join(Config.DIR_CONFIG, Config.ARCHIVO_CLIENTES)
    if not os.path.exists(ruta_clientes):
        ruta_clientes = Config.ARCHIVO_CLIENTES

    try:
        with open(ruta_clientes, "r", encoding="utf-8") as f:
            peluquerias = json.load(f)
        _validar_timezones(peluquerias, "clientes.json")
        return peluquerias
    except FileNotFoundError:
        print(f"⚠️ No se encontró {ruta_clientes} (seguimos solo con Mongo, si hay)")
        return {}
    except json.JSONDecodeError:
        print(f"⚠️ {ruta_clientes} está corrupto, se ignora")
        return {}


def cargar_clientes_mongo() -> dict:
    """Carga la config dinámica desde MongoDB (donde escribe el aprovisionamiento automático)."""
    try:
        from app.core.database import obtener_todas_las_config_peluquerias
        peluquerias = obtener_todas_las_config_peluquerias()
        _validar_timezones(peluquerias, "mongo")
        return peluquerias
    except Exception as e:
        print(f"⚠️ No se pudo cargar peluquerias desde Mongo: {e}")
        return {}


def cargar_clientes() -> dict:
    """Combina clientes.json (semilla) + Mongo (dinámico). Mongo pisa al json si hay conflicto de key."""
    combinado = {}
    combinado.update(cargar_clientes_json())
    combinado.update(cargar_clientes_mongo())

    print(f"✅ Clientes cargados: {len(combinado)}")
    for key, config in combinado.items():
        nombre = config.get('nombre', key)
        print(f"   • {nombre} ({key})")

    return combinado


# Inicializar
Config.validar()
PELUQUERIAS = cargar_clientes()

# Claves que vinieron de Mongo en el último refresh (para poder dar de baja
# clientes desactivados sin tocar los que vienen de clientes.json)
_claves_mongo_actuales = set(cargar_clientes_mongo().keys())


def _refrescar_periodicamente():
    """Actualiza PELUQUERIAS in-place cada Config.PELUQUERIAS_REFRESH_SEGUNDOS."""
    global _claves_mongo_actuales
    while True:
        time.sleep(Config.PELUQUERIAS_REFRESH_SEGUNDOS)
        try:
            nuevas = cargar_clientes_mongo()

            # Sacar las que estaban por Mongo y ya no vienen más (desactivadas)
            for key in list(PELUQUERIAS.keys()):
                if key in _claves_mongo_actuales and key not in nuevas:
                    print(f"🗑️ Peluquería {key} ya no está activa en Mongo, se quita de PELUQUERIAS")
                    PELUQUERIAS.pop(key, None)

            # Agregar/actualizar in-place — el mismo objeto dict, así todo el
            # código que ya tiene una referencia a PELUQUERIAS ve los cambios
            PELUQUERIAS.update(nuevas)
            _claves_mongo_actuales = set(nuevas.keys())

            if nuevas:
                print(f"🔄 PELUQUERIAS refrescado desde Mongo ({len(nuevas)} activos)")

        except Exception as e:
            print(f"❌ Error refrescando PELUQUERIAS: {e}")


def iniciar_refresco_peluquerias():
    """Arranca el hilo de refresco. Llamar una vez desde app/__init__.py."""
    hilo = threading.Thread(
        target=_refrescar_periodicamente,
        daemon=True,
        name="RefrescoPeluqueriasThread",
    )
    hilo.start()
    print(f"✅ Hilo de refresco de PELUQUERIAS iniciado (cada {Config.PELUQUERIAS_REFRESH_SEGUNDOS}s)")


# Crear directorios necesarios
os.makedirs(Config.DIR_TOKENS, exist_ok=True)
os.makedirs(Config.DIR_CONFIG, exist_ok=True)
