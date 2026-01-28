"""
Webhook para recibir mensajes de WhatsApp (Twilio)
"""
from flask import Blueprint, request, jsonify
from app.bot.handlers.menu_handler import MenuHandler
from app.bot.states.state_manager import get_state, set_state
from app.core.config import PELUQUERIAS
from app.services.whatsapp_service import whatsapp_service

# Blueprint
whatsapp_bp = Blueprint('whatsapp', __name__)

# Handler del menú
menu_handler = MenuHandler(PELUQUERIAS)


@whatsapp_bp.route("/webhook", methods=["POST"])
def webhook_whatsapp():
    """
    Recibe mensajes desde WhatsApp vía Twilio
    
    Expected format:
    {
        "From": "whatsapp:+5492974210130",
        "Body": "hola",
        "To": "whatsapp:+14155238886"
    }
    """
    try:
        # Obtener datos del mensaje
        numero_origen = request.form.get("From", "")
        mensaje = request.form.get("Body", "").strip().lower()
        numero_destino = request.form.get("To", "")
        
        if not numero_origen or not mensaje:
            return jsonify({"error": "Datos incompletos"}), 400
        
        print(f"\n📱 Mensaje recibido de {numero_origen}: {mensaje}")
        
        # Limpiar número
        numero_limpio = numero_origen.replace("whatsapp:", "")
        
        # Determinar peluquería (por ahora usamos la primera)
        # TODO: Implementar routing multi-cliente
        peluqueria_key = list(PELUQUERIAS.keys())[0]
        config = PELUQUERIAS[peluqueria_key]
        
        # Obtener estado actual
        estado = get_state(numero_limpio) or {"paso": "menu"}
        paso_actual = estado.get("paso", "menu")
        
        print(f"📊 Estado actual: {paso_actual}")
        
        # Procesar comandos globales
        if mensaje in ["menu", "hola", "hi", "inicio"]:
            menu_handler.mostrar_menu(numero_origen, peluqueria_key)
            
            # Actualizar estado
            estado["paso"] = "menu"
            set_state(numero_limpio, estado)
            
            return jsonify({"status": "ok"}), 200
        
        # Procesar según el paso actual
        if paso_actual == "menu":
            # Usuario está en menú principal
            nuevo_paso = menu_handler.procesar_opcion(
                numero_origen,
                mensaje,
                peluqueria_key
            )
            
            # Actualizar estado si cambió
            if nuevo_paso != paso_actual:
                estado["paso"] = nuevo_paso
                set_state(numero_limpio, estado)
        
        elif paso_actual == "seleccionar_peluquero":
            # Usuario está seleccionando peluquero
            from app.bot.handlers.booking_handler import BookingHandler
            
            booking_handler = BookingHandler(PELUQUERIAS)
            booking_handler.procesar_seleccion_peluquero(
                numero_limpio,
                mensaje,
                peluqueria_key,
                numero_origen
            )
        
        elif paso_actual == "seleccionar_dia":
            # Usuario está seleccionando día
            from app.bot.handlers.booking_handler import BookingHandler
            
            booking_handler = BookingHandler(PELUQUERIAS)
            booking_handler.procesar_seleccion_dia(
                numero_limpio,
                mensaje,
                peluqueria_key,
                numero_origen
            )
        
        elif paso_actual == "seleccionar_hora":
            # Usuario está seleccionando hora
            from app.bot.handlers.booking_handler import BookingHandler
            
            booking_handler = BookingHandler(PELUQUERIAS)
            booking_handler.procesar_seleccion_hora(
                numero_limpio,
                mensaje,
                peluqueria_key,
                numero_origen
            )
        
        elif paso_actual == "ingresar_nombre":
            # Usuario está ingresando su nombre
            from app.bot.handlers.booking_handler import BookingHandler
            
            booking_handler = BookingHandler(PELUQUERIAS)
            booking_handler.procesar_nombre(
                numero_limpio,
                mensaje,
                peluqueria_key,
                numero_origen
            )
        
        elif paso_actual == "confirmar_cancelacion":
            # Usuario está confirmando cancelación
            from app.bot.handlers.cancellation_handler import CancellationHandler
            
            cancel_handler = CancellationHandler(PELUQUERIAS)
            cancel_handler.procesar_confirmacion(
                numero_limpio,
                mensaje,
                peluqueria_key,
                numero_origen
            )
        
        else:
            # Paso desconocido, volver al menú
            whatsapp_service.enviar_mensaje(
                "❌ Estado inválido. Escribí *menu* para empezar de nuevo.",
                numero_origen
            )
            
            estado["paso"] = "menu"
            set_state(numero_limpio, estado)
        
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        print(f"❌ Error en webhook: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({"error": str(e)}), 500


@whatsapp_bp.route("/webhook", methods=["GET"])
def verificar_webhook():
    """
    Verificación del webhook (usado por algunos proveedores)
    """
    return jsonify({"status": "ok"}), 200