"""
Webhooks de Pagos
Procesa notificaciones de LemonSqueezy y MercadoPago
"""

from flask import Blueprint, request, jsonify
from app.services.payment_service import payment_service
from app.services.whatsapp_service import whatsapp_service
from app.services.calendar_service import CalendarService
from datetime import datetime
import json

try:
    from app.core.database import guardar_pago, actualizar_estado_turno
    MONGODB_DISPONIBLE = True
except ImportError:
    MONGODB_DISPONIBLE = False
    def guardar_pago(*args, **kwargs): return None
    def actualizar_estado_turno(*args, **kwargs): return None

# Crear blueprint
payments_bp = Blueprint('payments', __name__)


# ==================== LEMONSQUEEZY WEBHOOK ====================

@payments_bp.route('/webhooks/lemonsqueezy', methods=['POST'])
def webhook_lemonsqueezy():
    """
    Webhook de LemonSqueezy
    Recibe notificaciones de pagos procesados
    """
    try:
        # Obtener datos del request
        payload = request.get_data()
        signature = request.headers.get('X-Signature', '')
        
        # Verificar firma
        if not payment_service.verificar_webhook_lemonsqueezy(payload, signature):
            print("❌ Firma inválida de LemonSqueezy")
            return jsonify({"error": "Invalid signature"}), 401
        
        # Parsear payload
        data = json.loads(payload)
        event_name = data.get('meta', {}).get('event_name')
        
        print(f"📨 Evento LemonSqueezy: {event_name}")
        
        # Procesar según tipo de evento
        if event_name == 'order_created':
            procesar_pago_lemonsqueezy(data)
        elif event_name == 'order_refunded':
            procesar_reembolso_lemonsqueezy(data)
        
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        print(f"❌ Error en webhook LemonSqueezy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def procesar_pago_lemonsqueezy(data):
    """
    Procesa un pago exitoso de LemonSqueezy
    
    Args:
        data: Datos del webhook
    """
    try:
        order = data.get('data', {})
        attributes = order.get('attributes', {})
        
        # Extraer información
        order_id = order.get('id')
        status = attributes.get('status')
        total = attributes.get('total')
        customer_email = attributes.get('user_email')
        
        # Obtener metadata del turno
        metadata = attributes.get('first_order_item', {}).get('metadata', {})
        
        if status == 'paid':
            print(f"✅ Pago LemonSqueezy confirmado: {order_id}")
            
            # Crear el turno en Google Calendar
            turno_info = {
                "peluqueria_key": metadata.get('peluqueria_key'),
                "cliente_nombre": metadata.get('cliente_nombre'),
                "cliente_telefono": metadata.get('cliente_telefono'),
                "servicio": metadata.get('servicio'),
                "fecha_hora": datetime.fromisoformat(metadata.get('fecha_hora')),
                "peluquero": metadata.get('peluquero'),
                "pagado": True,
                "monto_pagado": total,
                "payment_provider": "lemonsqueezy",
                "payment_id": order_id
            }
            
            # Confirmar turno
            confirmar_turno_con_pago(turno_info)
            
            # Guardar pago en DB si está disponible
            if MONGODB_DISPONIBLE:
                guardar_pago(
                    peluqueria_key=turno_info['peluqueria_key'],
                    payment_id=order_id,
                    provider='lemonsqueezy',
                    monto=total,
                    estado='paid',
                    metadata=metadata
                )
    
    except Exception as e:
        print(f"❌ Error procesando pago LemonSqueezy: {e}")
        import traceback
        traceback.print_exc()


def procesar_reembolso_lemonsqueezy(data):
    """Procesa un reembolso de LemonSqueezy"""
    try:
        order_id = data.get('data', {}).get('id')
        print(f"💰 Reembolso LemonSqueezy procesado: {order_id}")
        
        # Actualizar estado en DB
        if MONGODB_DISPONIBLE:
            actualizar_estado_turno(order_id, 'refunded')
        
        # Aquí podrías enviar notificación al cliente
    
    except Exception as e:
        print(f"❌ Error procesando reembolso: {e}")


# ==================== MERCADOPAGO WEBHOOK ====================

@payments_bp.route('/webhooks/mercadopago', methods=['POST'])
def webhook_mercadopago():
    """
    Webhook de MercadoPago
    Recibe notificaciones de pagos
    """
    try:
        data = request.get_json()
        
        # MercadoPago envía diferentes tipos de notificaciones
        tipo = data.get('type')
        
        print(f"📨 Notificación MercadoPago: {tipo}")
        
        if tipo == 'payment':
            payment_id = data.get('data', {}).get('id')
            
            if payment_id:
                # Obtener información del pago
                payment_info = payment_service.verificar_webhook_mercadopago(payment_id)
                
                if payment_info:
                    procesar_pago_mercadopago(payment_info)
        
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        print(f"❌ Error en webhook MercadoPago: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def procesar_pago_mercadopago(payment_info):
    """
    Procesa un pago de MercadoPago
    
    Args:
        payment_info: Información del pago obtenida de la API
    """
    try:
        payment_id = payment_info.get('id')
        status = payment_info.get('status')
        
        # Solo procesar pagos aprobados
        if status == 'approved':
            print(f"✅ Pago MercadoPago aprobado: {payment_id}")
            
            # Extraer metadata
            metadata = payment_info.get('metadata', {})
            
            turno_info = {
                "peluqueria_key": metadata.get('peluqueria_key'),
                "cliente_nombre": metadata.get('cliente_nombre'),
                "cliente_telefono": metadata.get('cliente_telefono'),
                "servicio": metadata.get('servicio'),
                "fecha_hora": datetime.fromisoformat(metadata.get('fecha_hora')),
                "peluquero": metadata.get('peluquero'),
                "pagado": True,
                "monto_pagado": payment_info.get('transaction_amount'),
                "payment_provider": "mercadopago",
                "payment_id": payment_id
            }
            
            # Confirmar turno
            confirmar_turno_con_pago(turno_info)
            
            # Guardar en DB
            if MONGODB_DISPONIBLE:
                guardar_pago(
                    peluqueria_key=turno_info['peluqueria_key'],
                    payment_id=payment_id,
                    provider='mercadopago',
                    monto=turno_info['monto_pagado'],
                    estado='approved',
                    metadata=metadata
                )
    
    except Exception as e:
        print(f"❌ Error procesando pago MercadoPago: {e}")
        import traceback
        traceback.print_exc()


# ==================== CONFIRMACIÓN DE TURNO ====================

def confirmar_turno_con_pago(turno_info):
    """
    Confirma el turno creando el evento en Google Calendar
    y enviando notificación al cliente
    
    Args:
        turno_info: Información del turno y pago
    """
    try:
        # Cargar config
        import json
        try:
            with open("config/clientes.json", "r") as f:
                PELUQUERIAS = json.load(f)
        except:
            with open("clientes.json", "r") as f:
                PELUQUERIAS = json.load(f)
        
        peluqueria_key = turno_info['peluqueria_key']
        config = PELUQUERIAS.get(peluqueria_key, {})
        
        # Crear evento en Google Calendar
        calendar_service = CalendarService(PELUQUERIAS)
        
        # Construir peluquero dict
        peluquero_dict = None
        if turno_info.get('peluquero'):
            peluqueros = config.get('peluqueros', [])
            for p in peluqueros:
                if p.get('nombre') == turno_info['peluquero']:
                    peluquero_dict = p
                    break
        
        evento = calendar_service.crear_evento_calendario(
            peluqueria_key,
            peluquero_dict or {},
            turno_info['cliente_nombre'],
            turno_info['cliente_telefono'],
            turno_info['fecha_hora'],
            duracion_minutos=30
        )
        
        if evento:
            print(f"✅ Turno creado en calendario: {evento['id']}")
            
            # Enviar confirmación por WhatsApp
            from app.bot.utils.formatters import formatear_fecha_espanol
            
            fecha_formateada = formatear_fecha_espanol(turno_info['fecha_hora'])
            hora = turno_info['fecha_hora'].strftime('%H:%M')
            
            mensaje = f"""✅ *¡Pago confirmado y turno reservado!*

👤 Cliente: {turno_info['cliente_nombre']}
📅 Fecha: {fecha_formateada}
🕐 Hora: {hora}
✂️ Servicio: {turno_info['servicio']}
💰 Pagado: ${turno_info['monto_pagado']:,.2f}

¡Te esperamos! 👈
{config.get('nombre', 'Peluquería')}"""
            
            whatsapp_service.enviar_mensaje(
                mensaje,
                f"whatsapp:{turno_info['cliente_telefono']}"
            )
            
            return True
    
    except Exception as e:
        print(f"❌ Error confirmando turno: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== PÁGINA DE ÉXITO/FALLO ====================

@payments_bp.route('/payment/success', methods=['GET'])
def payment_success():
    """Página de éxito después del pago"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pago Exitoso</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: #f0f9ff;
            }
            .container {
                max-width: 500px;
                margin: 0 auto;
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #10b981; }
            p { color: #666; line-height: 1.6; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✅ ¡Pago Exitoso!</h1>
            <p>Tu pago se ha procesado correctamente.</p>
            <p>Recibirás un mensaje de WhatsApp con la confirmación de tu turno.</p>
            <p>¡Gracias por tu reserva!</p>
        </div>
    </body>
    </html>
    """


@payments_bp.route('/payment/failure', methods=['GET'])
def payment_failure():
    """Página de fallo en el pago"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pago Fallido</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: #fef2f2;
            }
            .container {
                max-width: 500px;
                margin: 0 auto;
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #ef4444; }
            p { color: #666; line-height: 1.6; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>❌ Pago No Procesado</h1>
            <p>Hubo un problema al procesar tu pago.</p>
            <p>Por favor intenta nuevamente o contacta con nosotros.</p>
        </div>
    </body>
    </html>
    """


@payments_bp.route('/payment/pending', methods=['GET'])
def payment_pending():
    """Página de pago pendiente"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pago Pendiente</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: #fffbeb;
            }
            .container {
                max-width: 500px;
                margin: 0 auto;
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #f59e0b; }
            p { color: #666; line-height: 1.6; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⏳ Pago Pendiente</h1>
            <p>Tu pago está siendo procesado.</p>
            <p>Te notificaremos por WhatsApp cuando se confirme.</p>
        </div>
    </body>
    </html>
    """