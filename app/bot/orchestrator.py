"""
Bot Orchestrator
Coordina todos los handlers y servicios del bot
"""

import os
import json
from app.bot.handlers.menu_handler import MenuHandler
from app.bot.handlers.booking_handler import BookingHandler
from app.bot.handlers.cancellation_handler import CancellationHandler
from app.bot.handlers.info_handler import InfoHandler
from app.services.whatsapp_service import whatsapp_service
from app.services.notification_service import inicializar_notification_service
from app.utils.calendar_utils import inicializar_calendar_utils
from app.bot.states.state_manager import get_state, set_state


class BotOrchestrator:
    """
    Orquestador principal del bot
    Coordina todos los handlers según el estado del usuario
    """
    
    def __init__(self, peluquerias_config):
        """
        Inicializa todos los handlers y servicios
        
        Args:
            peluquerias_config: Diccionario con configuración de clientes
        """
        self.peluquerias = peluquerias_config
        
        print("\n" + "="*60)
        print("🤖 INICIALIZANDO BOT ORCHESTRATOR")
        print("="*60)
        
        # Inicializar handlers
        print("📦 Inicializando handlers...")
        self.menu_handler = MenuHandler(peluquerias_config)
        print("   ✅ MenuHandler")
        
        self.booking_handler = BookingHandler(peluquerias_config)
        print("   ✅ BookingHandler")
        
        self.cancellation_handler = CancellationHandler(peluquerias_config)
        print("   ✅ CancellationHandler")
        
        self.info_handler = InfoHandler(peluquerias_config)
        print("   ✅ InfoHandler")
        
        # Inicializar utilidades globales
        print("🔧 Inicializando utilidades...")
        inicializar_calendar_utils(peluquerias_config)
        print("   ✅ CalendarUtils")
        
        # Inicializar servicio de notificaciones
        print("📢 Inicializando servicios...")
        templates_config = {
            "TEMPLATE_RECORDATORIO": os.getenv("TEMPLATE_RECORDATORIO"),
            "TEMPLATE_CONFIRMACION": os.getenv("TEMPLATE_CONFIRMACION"),
            "TEMPLATE_NUEVO_TURNO": os.getenv("TEMPLATE_NUEVO_TURNO")
        }
        
        self.notification_service = inicializar_notification_service(
            peluquerias_config,
            templates_config
        )
        print("   ✅ NotificationService")
        
        # Iniciar sistema de recordatorios en background (solo en producción)
        modo_desarrollo = os.getenv('FLASK_ENV') == 'development'
        if not modo_desarrollo:
            self.notification_service.iniciar_sistema_recordatorios()
            print("   ✅ Sistema de recordatorios activado")
        else:
            print("   ⏭️ Sistema de recordatorios desactivado (desarrollo)")
        
        print("="*60)
        print("✅ BOT ORCHESTRATOR INICIALIZADO CORRECTAMENTE")
        print(f"📊 Clientes configurados: {len(peluquerias_config)}")
        for key, config in peluquerias_config.items():
            print(f"   • {config.get('nombre', key)} ({key})")
        print("="*60 + "\n")
    
    def procesar_mensaje(self, numero, texto, peluqueria_key):
        """
        Procesa un mensaje entrante y lo dirige al handler apropiado
        
        Args:
            numero: Número de WhatsApp completo (con whatsapp:)
            texto: Texto del mensaje
            peluqueria_key: Identificador del cliente
        """
        try:
            numero_limpio = numero.replace("whatsapp:", "").strip()
            texto_lower = texto.lower()
            
            # Obtener o crear estado del usuario
            estado_usuario = get_state(numero_limpio)
            
            if not estado_usuario:
                # Usuario nuevo - crear estado inicial
                print(f"🆕 Nuevo usuario: {numero_limpio}")
                estado_usuario = {
                    "paso": "menu",
                    "peluqueria": peluqueria_key
                }
                set_state(numero_limpio, estado_usuario)
                
                # Mensaje de bienvenida
                self.menu_handler.mostrar_mensaje_bienvenida(peluqueria_key, numero)
                return
            
            # Usuario existente
            paso_actual = estado_usuario.get("paso", "menu")
            
            # Si estaba finalizado, reactivar
            if paso_actual == "finalizado":
                print(f"🔄 Reactivando usuario: {numero_limpio}")
                estado_usuario["paso"] = "menu"
                set_state(numero_limpio, estado_usuario)
                self.menu_handler.mostrar_mensaje_bienvenida(peluqueria_key, numero)
                return
            
            # Actualizar peluquería por si cambió
            estado_usuario["peluqueria"] = peluqueria_key
            set_state(numero_limpio, estado_usuario)
            
            # Comandos globales para volver al menú
            comandos_menu = [
                "menu", "menú", "inicio", "hola", "hi", "hey",
                "buenas", "buenos dias", "buenas tardes", "buen dia",
                "buenos días", "buenas noches"
            ]
            
            if texto_lower in comandos_menu:
                print(f"🏠 Comando de menú detectado: '{texto}'")
                estado_usuario["paso"] = "menu"
                set_state(numero_limpio, estado_usuario)
                self.menu_handler.mostrar_menu_principal(peluqueria_key, numero)
                return
            
            # Comando para cancelar operación actual
            if texto_lower in ["cancelar", "salir", "abortar", "stop", "volver"]:
                if paso_actual != "menu":
                    print(f"❌ Usuario canceló operación: {paso_actual}")
                    estado_usuario["paso"] = "menu"
                    set_state(numero_limpio, estado_usuario)
                    whatsapp_service.enviar_mensaje(
                        "❌ Operación cancelada.\n\nVolviendo al menú...",
                        numero
                    )
                    self.menu_handler.mostrar_menu_principal(peluqueria_key, numero)
                    return
            
            # Enrutar según estado
            print(f"📍 Estado actual: {paso_actual}")
            self._enrutar_mensaje(numero_limpio, texto, paso_actual, peluqueria_key, numero)
        
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"❌ ERROR EN PROCESAR_MENSAJE")
            print(f"{'='*60}")
            print(f"Usuario: {numero}")
            print(f"Texto: {texto}")
            print(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"{'='*60}\n")
            
            # Intentar enviar mensaje de error al usuario
            try:
                whatsapp_service.enviar_mensaje(
                    "❌ Ocurrió un error temporal.\n\n"
                    "Por favor escribí *menu* para reintentar.",
                    numero
                )
            except:
                pass
    
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
            print(f"❓ Opción inválida: {texto}")
            self.menu_handler.mostrar_opcion_invalida(numero, texto)
            self.menu_handler.mostrar_menu_principal(peluqueria_key, numero)
            return
        
        print(f"✅ Opción de menú: {texto}")
        
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


# Cargar configuración de clientes
try:
    with open("config/clientes.json", "r", encoding="utf-8") as f:
        PELUQUERIAS = json.load(f)
except FileNotFoundError:
    print("⚠️ Usando clientes.json en raíz")
    with open("clientes.json", "r", encoding="utf-8") as f:
        PELUQUERIAS = json.load(f)

# Instancia global del orquestador
bot_orchestrator = BotOrchestrator(PELUQUERIAS)