"""
Webhook de WhatsApp
Recibe y procesa mensajes de WhatsApp vía Twilio
"""

from flask import Blueprint, request, jsonify
from app.bot.orchestrator import bot_orchestrator

# Crear blueprint
whatsapp_bp = Blueprint('whatsapp', __name__)


@whatsapp_bp.route('/webhook', methods=['POST'])
def webhook_whatsapp():
    """
    Webhook principal para recibir mensajes de WhatsApp
    Procesa mensajes entrantes de Twilio
    """
    try:
        # Obtener datos del request
        data = request.form.to_dict() if request.form else request.get_json()
        
        if not data:
            print("⚠️ Request vacío recibido")
            return "", 400
        
        # Extraer información del mensaje
        numero = data.get("From")  # whatsapp:+5492974210130
        texto = data.get("Body", "").strip()
        numero_destino = data.get("To")  # whatsapp:+14155238886

        # Detectar si hay archivos adjuntos (fotos, audios, videos, documentos)
        num_media = int(data.get("NumMedia", 0))
        media_type = data.get("MediaContentType0", "")  # ej: "image/jpeg", "audio/ogg"

        # Validar que al menos tengamos el número de origen
        if not numero:
            print(f"⚠️ Request sin numero de origen")
            return "", 400

        # Log del mensaje recibido
        print(f"\n{'='*60}")
        print(f"📨 MENSAJE RECIBIDO")
        print(f"{'='*60}")
        print(f"De: {numero}")
        print(f"A: {numero_destino}")
        print(f"Mensaje: {texto or '(sin texto)'}")
        if num_media:
            print(f"Media: {num_media} archivo(s) - {media_type}")
        print(f"{'='*60}\n")

        # Manejar mensajes sin texto (fotos, audios, videos, stickers)
        if not texto and num_media > 0:
            from app.services.whatsapp_service import whatsapp_service
            peluqueria_key_temp = detectar_peluqueria(numero_destino)

            if media_type.startswith("audio"):
                respuesta = (
                    "🎤 Recibí tu nota de voz, pero aún no puedo escucharla.\n\n"
                    "Por favor escribime tu consulta por texto y te respondo enseguida. ✍️"
                )
            elif media_type.startswith("image"):
                respuesta = (
                    "📷 Recibí tu imagen, pero aún no puedo verla.\n\n"
                    "Por favor escribime tu consulta por texto y te ayudo. ✍️"
                )
            elif media_type.startswith("video"):
                respuesta = (
                    "🎥 Recibí tu video, pero aún no puedo reproducirlo.\n\n"
                    "Por favor escribime tu consulta por texto. ✍️"
                )
            else:
                respuesta = (
                    "📎 Recibí tu archivo, pero aún no puedo procesarlo.\n\n"
                    "Por favor escribime tu consulta por texto. ✍️"
                )

            whatsapp_service.enviar_mensaje(respuesta, numero)
            print(f"📎 Media recibida de {numero} ({media_type}) - respuesta enviada")
            return "", 200

        # Si no hay texto ni media, ignorar silenciosamente
        if not texto:
            print(f"⚠️ Mensaje vacío de {numero} - ignorado")
            return "", 200
        
        # Detectar peluquería según número de Twilio
        peluqueria_key = detectar_peluqueria(numero_destino)
        
        if not peluqueria_key:
            print(f"❌ No se pudo identificar la peluquería para {numero_destino}")
            # Enviar mensaje de error al usuario
            from app.services.whatsapp_service import whatsapp_service
            whatsapp_service.enviar_mensaje(
                "Lo siento, hubo un error de configuración. Por favor contacta con soporte.",
                numero
            )
            return "", 404
        
        print(f"✅ Peluquería identificada: {peluqueria_key}")
        
        # Verificar suscripción activa
        from app.utils.verificar_suscripcion import verificar_suscripcion
        suscripcion = verificar_suscripcion(peluqueria_key)

        if not suscripcion["activa"]:
            print(f"⛔ Bot bloqueado para {peluqueria_key}: {suscripcion['motivo']}")
            # No respondemos nada — el dueño ya fue avisado cuando venció el trial
            return "", 200

        # Procesar mensaje con el orquestrador
        bot_orchestrator.procesar_mensaje(numero, texto, peluqueria_key)
        
        print(f"✅ Mensaje procesado correctamente\n")
        return "", 200
    
    except KeyError as e:
        print(f"❌ Error: Falta campo requerido - {e}")
        import traceback
        traceback.print_exc()
        return "", 400
    
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ ERROR EN WEBHOOK")
        print(f"{'='*60}")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        return "", 500


@whatsapp_bp.route('/webhook', methods=['GET'])
def webhook_verify():
    """
    Verificación del webhook (para algunos servicios que lo requieren)
    """
    return jsonify({"status": "ok", "message": "Webhook activo"}), 200


def detectar_peluqueria(numero_twilio):
    """
    Detecta qué peluquería según el número de Twilio que recibió el mensaje
    Sistema multi-tenant para SaaS
    
    Args:
        numero_twilio: Número de Twilio (ej: whatsapp:+14155238886)
    
    Returns:
        str: Key de la peluquería o None si no se encuentra
    """
    from app.bot.orchestrator import bot_orchestrator
    
    # Limpiar el número
    numero_limpio = numero_twilio.replace("whatsapp:", "").strip()
    
    print(f"🔍 Buscando peluquería para número: {numero_limpio}")
    
    # Buscar en configuración
    for key, config in bot_orchestrator.peluquerias.items():
        numero_config = config.get("numero_twilio", "").strip()
        
        if numero_config and numero_config == numero_limpio:
            print(f"✅ Match encontrado: {key} - {config.get('nombre')}")
            return key
    
    # Si no se encuentra, mostrar números registrados para debug
    print(f"❌ No se encontró peluquería para: {numero_limpio}")
    print(f"📋 Números registrados:")
    for key, config in bot_orchestrator.peluquerias.items():
        numero_reg = config.get("numero_twilio", "NO CONFIGURADO")
        print(f"   • {key}: {numero_reg}")
    
    return None


@whatsapp_bp.route('/webhook/status', methods=['POST'])
def webhook_status():
    """
    Recibe actualizaciones de estado de mensajes de Twilio
    (Opcional - para tracking de mensajes enviados/entregados/leídos)
    """
    try:
        data = request.form.to_dict() if request.form else request.get_json()
        
        message_sid = data.get("MessageSid")
        message_status = data.get("MessageStatus")
        
        print(f"📊 Estado de mensaje {message_sid}: {message_status}")
        
        # Aquí podrías guardar el estado en DB si lo necesitas
        # Por ejemplo: actualizar_estado_mensaje(message_sid, message_status)
        
        return "", 200
    
    except Exception as e:
        print(f"❌ Error en webhook de status: {e}")
        return "", 500