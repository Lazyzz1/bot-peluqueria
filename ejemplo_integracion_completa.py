"""
Ejemplo de Integración Completa
Muestra cómo usar todos los handlers juntos
"""

import os
import json
from flask import Flask, request, jsonify

# Handlers
from app.bot.handlers.menu_handler import MenuHandler
from app.bot.handlers.booking_handler import BookingHandler
from app.bot.handlers.cancellation_handler import CancellationHandler
from app.bot.handlers.info_handler import InfoHandler

# Services
from app.services.whatsapp_service import whatsapp_service
from app.services.notification_service import inicializar_notification_service

# Utils
from app.utils.calendar_utils import inicializar_calendar_utils
from app.bot.states.state_manager import get_state, set_state

# Cargar configuración
with open("clientes.json", "r", encoding="utf-8") as f:
    PELUQUERIAS = json.load(f)

# Inicializar la app Flask
app = Flask(__name__)


class BotOrchestrator:
    """
    Orquestador principal del bot
    Coordina todos los handlers según el estado del usuario
    """
    
    def __init__(self, peluquerias_config):
        """
        Inicializa todos los handlers
        
        Args:
            peluquerias_config: Diccionario con configuración de clientes
        """
        self.peluquerias = peluquerias_config
        
        # Inicializar handlers
        self.menu_handler = MenuHandler(peluquerias_config)
        self.booking_handler = BookingHandler(peluquerias_config)
        self.cancellation_handler = CancellationHandler(peluquerias_config)
        self.info_handler = InfoHandler(peluquerias_config)
        
        # Inicializar utilidades globales
        inicializar_calendar_utils(peluquerias_config)
        
        # Inicializar servicio de notificaciones
        templates_config = {
            "TEMPLATE_RECORDATORIO": os.getenv("TEMPLATE_RECORDATORIO"),
            "TEMPLATE_CONFIRMACION": os.getenv("TEMPLATE_CONFIRMACION")
        }
        self.notification_service = inicializar_notification_service(
            peluquerias_config,
            templates_config
        )
        
        # Iniciar sistema de recordatorios en background
        self.notification_service.iniciar_sistema_recordatorios()
        
        print("✅ BotOrchestrator inicializado correctamente")
    
    def procesar_mensaje(self, numero, texto, peluqueria_key):
        """
        Procesa un mensaje entrante y lo dirige al handler apropiado
        
        Args:
            numero: Número de WhatsApp completo (con whatsapp:)
            texto: Texto del mensaje
            peluqueria_key: Identificador del cliente
        """
        numero_limpio = numero.replace("whatsapp:", "").strip()
        
        # Obtener o crear estado del usuario
        estado_usuario = get_state(numero_limpio)
        
        if not estado_usuario:
            # Usuario nuevo - crear estado inicial
            estado_usuario = {
                "paso": "menu",
                "peluqueria": peluqueria_key
            }
            set_state(numero_limpio, estado_usuario)
        
        # Actualizar peluquería por si cambió
        estado_usuario["peluqueria"] = peluqueria_key
        
        # Comandos globales para volver al menú
        comandos_menu = [
            "menu", "menú", "inicio", "hola", "hi", "hey",
            "buenas", "buenos dias", "buenas tardes", "buen dia"
        ]
        
        if texto.lower() in comandos_menu:
            estado_usuario["paso"] = "menu"
            set_state(numero_limpio, estado_usuario)
            self.menu_handler.mostrar_menu_principal(peluqueria_key, numero)
            return
        
        # Obtener estado actual
        paso_actual = estado_usuario.get("paso", "menu")
        
        # Enrutar según estado
        self._enrutar_mensaje(numero_limpio, texto, paso_actual, peluqueria_key, numero)
    
    def _enrutar_mensaje(self, numero_limpio, texto, paso, peluqueria_key, numero):
        """
        Enruta el mensaje al handler apropiado según el paso/estado
        
        Args:
            numero_limpio: Número sin prefijo
            texto: Texto del mensaje
            paso: Estado actual del usuario
            peluqueria_key: Identificador del cliente
            numero: Número completo
        """
        # MENÚ PRINCIPAL
        if paso == "menu":
            self._procesar_opcion_menu(numero_limpio, texto, peluqueria_key, numero)
        
        # FLUJO DE RESERVA
        elif paso == "seleccionar_peluquero":
            self.booking_handler.procesar_seleccion_peluquero(
                numero_limpio, texto, peluqueria_key, numero
            )
        
        elif paso == "seleccionar_dia":
            self.booking_handler.procesar_seleccion_dia(
                numero_limpio, texto, peluqueria_key, numero
            )
        
        elif paso == "seleccionar_horario":
            self.booking_handler.procesar_seleccion_horario(
                numero_limpio, texto, numero
            )
        
        elif paso == "nombre":
            self.booking_handler.procesar_nombre_cliente(
                numero_limpio, texto, peluqueria_key, numero
            )
        
        elif paso == "servicio":
            self.booking_handler.procesar_seleccion_servicio(
                numero_limpio, texto, peluqueria_key, numero
            )
        
        # FLUJO DE CANCELACIÓN
        elif paso == "seleccionar_turno_cancelar":
            self.cancellation_handler.procesar_seleccion_turno(
                numero_limpio, texto, peluqueria_key, numero
            )
        
        elif paso == "confirmar_cancelacion":
            self.cancellation_handler.procesar_confirmacion(
                numero_limpio, texto, peluqueria_key, numero
            )
        
        # FLUJO DE REAGENDAR
        elif paso == "seleccionar_turno_reagendar":
            self.info_handler.procesar_seleccion_turno_reagendar(
                numero_limpio, texto, numero
            )
        
        # Estado desconocido - resetear a menú
        else:
            print(f"⚠️ Estado desconocido: {paso} - Reseteando a menú")
            estado_usuario = get_state(numero_limpio) or {}
            estado_usuario["paso"] = "menu"
            set_state(numero_limpio, estado_usuario)
            whatsapp_service.enviar_mensaje(
                "❓ Hubo un error. Volvamos al inicio.\n\n",
                numero
            )
            self.menu_handler.mostrar_menu_principal(peluqueria_key, numero)
    
    def _procesar_opcion_menu(self, numero_limpio, texto, peluqueria_key, numero):
        """
        Procesa la opción seleccionada del menú principal
        
        Args:
            numero_limpio: Número sin prefijo
            texto: Opción seleccionada (1-7, 0)
            peluqueria_key: Identificador del cliente
            numero: Número completo
        """
        # Verificar que sea una opción válida
        if texto not in ["0", "1", "2", "3", "4", "5", "6", "7"]:
            whatsapp_service.enviar_mensaje(
                f"❓ No entendí '{texto}'\n\n",
                numero
            )
            self.menu_handler.mostrar_menu_principal(peluqueria_key, numero)
            return
        
        # Procesar cada opción
        if texto == "0":  # Salir
            self._procesar_salir(numero_limpio, peluqueria_key, numero)
        
        elif texto == "1":  # Pedir turno
            self.booking_handler.iniciar_reserva(numero_limpio, peluqueria_key, numero)
        
        elif texto == "2":  # Ver turnos
            self.info_handler.procesar_ver_turnos(numero_limpio, peluqueria_key, numero)
        
        elif texto == "3":  # Cancelar turno
            self.cancellation_handler.iniciar_cancelacion(numero_limpio, peluqueria_key, numero)
        
        elif texto == "4":  # Servicios
            self.info_handler.procesar_servicios(peluqueria_key, numero)
        
        elif texto == "5":  # Reagendar
            self.info_handler.procesar_reagendar_inicio(numero_limpio, peluqueria_key, numero)
        
        elif texto == "6":  # FAQ
            self.info_handler.procesar_faq(numero, peluqueria_key)
        
        elif texto == "7":  # Ubicación
            self.info_handler.procesar_ubicacion(peluqueria_key, numero)
    
    def _procesar_salir(self, numero_limpio, peluqueria_key, numero):
        """Procesa la opción de salir del menú"""
        config = self.peluquerias.get(peluqueria_key, {})
        
        whatsapp_service.enviar_mensaje(
            "👋 ¡Gracias por contactarnos!\n\n"
            "Cuando quieras volver, escribí *hola* o *menu*\n\n"
            f"*{config.get('nombre', 'Peluquería')}* 👈",
            numero
        )
        
        # Actualizar estado
        estado_usuario = get_state(numero_limpio) or {}
        estado_usuario["paso"] = "finalizado"
        set_state(numero_limpio, estado_usuario)


# Inicializar el orquestador
bot = BotOrchestrator(PELUQUERIAS)


# ==================== WEBHOOK DE WHATSAPP ====================

@app.route("/webhook", methods=["POST"])
def webhook_whatsapp():
    """
    Webhook principal para recibir mensajes de WhatsApp
    """
    try:
        data = request.get_json()
        
        # Extraer datos del mensaje
        numero = data.get("From")  # whatsapp:+5492974210130
        texto = data.get("Body", "").strip()
        numero_destino = data.get("To")  # whatsapp:+14155238886
        
        if not numero or not texto:
            return "", 400
        
        # Detectar peluquería según número de Twilio
        peluqueria_key = detectar_peluqueria(numero_destino)
        
        if not peluqueria_key:
            print(f"❌ No se pudo identificar la peluquería para {numero_destino}")
            return "", 404
        
        print(f"📨 Mensaje recibido de {numero} para {peluqueria_key}: {texto}")
        
        # Procesar mensaje
        bot.procesar_mensaje(numero, texto, peluqueria_key)
        
        return "", 200
    
    except Exception as e:
        print(f"❌ Error en webhook: {e}")
        import traceback
        traceback.print_exc()
        return "", 500


def detectar_peluqueria(numero_twilio):
    """
    Detecta qué peluquería según el número de Twilio
    
    Args:
        numero_twilio: Número de Twilio que recibió el mensaje
    
    Returns:
        str: Key de la peluquería o None
    """
    numero_limpio = numero_twilio.replace("whatsapp:", "").strip()
    
    for key, config in PELUQUERIAS.items():
        numero_config = config.get("numero_twilio", "").strip()
        if numero_config and numero_config == numero_limpio:
            return key
    
    return None


# ==================== HEALTH CHECK ====================

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "handlers": {
            "menu": "✅",
            "booking": "✅",
            "cancellation": "✅",
            "info": "✅"
        },
        "services": {
            "whatsapp": "✅",
            "calendar": "✅",
            "notifications": "✅"
        }
    }), 200


# ==================== MAIN ====================

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 BOT DE PELUQUERÍA - ARQUITECTURA MODULAR")
    print("=" * 60)
    print(f"✅ Clientes cargados: {len(PELUQUERIAS)}")
    for key, config in PELUQUERIAS.items():
        print(f"   • {config['nombre']} ({key})")
    print("=" * 60)
    print("✅ Handlers inicializados:")
    print("   • MenuHandler")
    print("   • BookingHandler")
    print("   • CancellationHandler")
    print("   • InfoHandler")
    print("=" * 60)
    print("✅ Servicios activos:")
    print("   • WhatsApp Service")
    print("   • Calendar Service")
    print("   • Notification Service")
    print("=" * 60)
    
    # Puerto dinámico
    port = int(os.environ.get("PORT", 3000))
    print(f"🚀 Servidor iniciando en puerto {port}")
    print("=" * 60)
    
    # Iniciar servidor
    app.run(host="0.0.0.0", port=port, debug=False)