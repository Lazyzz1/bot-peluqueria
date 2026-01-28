"""
Configuración centralizada de la aplicación
"""
import os
import sys
import json
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
    
    @classmethod
    def validar(cls):
        """Valida que las configuraciones necesarias estén presentes"""
        # Validar Twilio
        if not all([cls.TWILIO_ACCOUNT_SID, cls.TWILIO_AUTH_TOKEN, cls.TWILIO_WHATSAPP_NUMBER]):
            raise ValueError("❌ Faltan variables de entorno de Twilio")
        
        # Validar plantillas si están activas
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


def cargar_clientes():
    """Carga la configuración de clientes desde JSON"""
    ruta_clientes = os.path.join(Config.DIR_CONFIG, Config.ARCHIVO_CLIENTES)
    
    # Intentar cargar desde config/
    if not os.path.exists(ruta_clientes):
        # Fallback a raíz del proyecto
        ruta_clientes = Config.ARCHIVO_CLIENTES
    
    try:
        with open(ruta_clientes, "r", encoding="utf-8") as f:
            peluquerias = json.load(f)
        
        # Validar timezones
        for cliente_id, config in peluquerias.items():
            tz = config.get("timezone")
            if not tz:
                raise ValueError(f"❌ Cliente {cliente_id} no tiene timezone configurado")
            if tz not in available_timezones():
                raise ValueError(f"❌ Timezone inválido para {cliente_id}: {tz}")
        
        print(f"✅ Clientes cargados: {len(peluquerias)}")
        for key, config in peluquerias.items():
            print(f"   • {config['nombre']} ({key})")
        
        return peluquerias
        
    except FileNotFoundError:
        raise FileNotFoundError(f"❌ No se encontró {ruta_clientes}")
    except json.JSONDecodeError:
        raise ValueError(f"❌ {ruta_clientes} está corrupto")


# Inicializar
Config.validar()
PELUQUERIAS = cargar_clientes()

# Crear directorios necesarios
os.makedirs(Config.DIR_TOKENS, exist_ok=True)
os.makedirs(Config.DIR_CONFIG, exist_ok=True)