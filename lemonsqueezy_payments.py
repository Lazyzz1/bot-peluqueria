"""
Integración de Lemonsqueezy para pagos internacionales
FUNCIONA DESDE A
"""

import requests
import os
import hmac
import hashlib
from flask import request, jsonify
from datetime import datetime

# Configurar Lemonsqueezy
LEMONSQUEEZY_API_KEY = os.getenv("LEMONSQUEEZY_API_KEY")
LEMONSQUEEZY_STORE_ID = os.getenv("LEMONSQUEEZY_STORE_ID")
LEMONSQUEEZY_WEBHOOK_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET")

# Base URL de la API
API_BASE = "https://api.lemonsqueezy.com/v1"

# Headers para las peticiones
def get_headers():
    return {
        "Authorization": f"Bearer {LEMONSQUEEZY_API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json"
    }

# ==================== FUNCIONES AUXILIARES ====================

def crear_producto(nombre, precio, descripcion=""):
    """
    Crea un producto en Lemonsqueezy
    
    Args:
        nombre: Nombre del producto
        precio: Precio en centavos (9900 = USD $99)
        descripcion: Descripción del producto
    
    Returns:
        Product ID
    """
    try:
        data = {
            "data": {
                "type": "products",
                "attributes": {
                    "name": nombre,
                    "description": descripcion,
                    "price": precio,
                    "store_id": LEMONSQUEEZY_STORE_ID
                }
            }
        }
        
        response = requests.post(
            f"{API_BASE}/products",
            headers=get_headers(),
            json=data
        )
        
        if response.status_code == 201:
            product = response.json()
            return product['data']['id']
        else:
            print(f"❌ Error creando producto: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def crear_checkout(variant_id, customer_email=None, customer_phone=None):
    """
    Crea un checkout de Lemonsqueezy
    
    Args:
        variant_id: ID de la variante del producto
        customer_email: Email del cliente
        customer_phone: Teléfono del cliente
    
    Returns:
        Checkout URL
    """
    try:
        data = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "checkout_data": {
                        "email": customer_email,
                        "custom": {
                            "phone": customer_phone
                        }
                    },
                    "product_options": {
                        "redirect_url": f"{os.getenv('APP_URL', 'https://tu-dominio.railway.app')}/success-lemon",
                    },
                    "checkout_options": {
                        "button_color": "#25D366"
                    }
                },
                "relationships": {
                    "store": {
                        "data": {
                            "type": "stores",
                            "id": LEMONSQUEEZY_STORE_ID
                        }
                    },
                    "variant": {
                        "data": {
                            "type": "variants",
                            "id": str(variant_id)
                        }
                    }
                }
            }
        }
        
        response = requests.post(
            f"{API_BASE}/checkouts",
            headers=get_headers(),
            json=data
        )
        
        if response.status_code == 201:
            checkout = response.json()
            return checkout['data']['attributes']['url']
        else:
            print(f"❌ Error creando checkout: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def verificar_webhook_signature(payload, signature):
    """Verifica la firma del webhook de Lemonsqueezy"""
    try:
        expected_signature = hmac.new(
            LEMONSQUEEZY_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        print(f"❌ Error verificando firma: {e}")
        return False

def webhook_lemonsqueezy_handler(payload, signature, enviar_mensaje_func):
    """
    Maneja los webhooks de Lemonsqueezy
    
    Args:
        payload: Cuerpo de la petición
        signature: Firma del webhook
        enviar_mensaje_func: Función para enviar WhatsApp
    
    Returns:
        Event data o None
    """
    try:
        # Verificar firma
        if not verificar_webhook_signature(payload, signature):
            print("❌ Firma de webhook inválida")
            return None
        
        import json
        event = json.loads(payload)
        
        event_name = event.get('meta', {}).get('event_name')
        data = event.get('data', {})
        attributes = data.get('attributes', {})
        
        # 🆕 PEDIDO CREADO (Order Created)
        if event_name == 'order_created':
            order_id = data.get('id')
            customer_email = attributes.get('user_email')
            customer_name = attributes.get('user_name')
            customer_phone = attributes.get('custom_data', {}).get('phone')
            total = attributes.get('total') / 100  # Convertir de centavos
            
            print(f"✅ Pedido creado: {order_id}")
            print(f"   Cliente: {customer_name} ({customer_email})")
            print(f"   Total: USD ${total}")
            
            # 🆕 NOTIFICAR POR WHATSAPP
            if customer_phone and enviar_mensaje_func:
                mensaje = (
                    "🎉 *¡Bienvenido a TurnosBot!*\n\n"
                    "✅ Tu pago ha sido procesado exitosamente.\n\n"
                    f"📋 Resumen:\n"
                    f"• Total pagado: *USD ${total:.2f}*\n"
                    f"• Pedido: #{order_id}\n\n"
                    "📅 *Próximos pasos:*\n"
                    "1️⃣ En 24-48 horas configuraremos tu bot\n"
                    "2️⃣ Te enviaremos las credenciales de acceso\n"
                    "3️⃣ Coordinaremos la capacitación inicial\n\n"
                    "💬 Si tenés alguna duda, respondé este mensaje.\n\n"
                    "¡Gracias por confiar en nosotros! 💚"
                )
                
                try:
                    enviar_mensaje_func(mensaje, customer_phone)
                    print(f"📤 Notificación enviada a {customer_phone}")
                except Exception as e:
                    print(f"⚠️ Error enviando WhatsApp: {e}")
            
            return data
        
        # 🆕 SUSCRIPCIÓN CREADA
        elif event_name == 'subscription_created':
            subscription_id = data.get('id')
            customer_email = attributes.get('user_email')
            customer_name = attributes.get('user_name')
            
            print(f"✅ Suscripción creada: {subscription_id}")
            
            return data
        
        # 🆕 PAGO DE SUSCRIPCIÓN EXITOSO
        elif event_name == 'subscription_payment_success':
            subscription_id = data.get('id')
            customer_email = attributes.get('user_email')
            
            print(f"✅ Pago de suscripción exitoso: {subscription_id}")
            
            # Aquí podrías notificar por WhatsApp
            
            return data
        
        # 🆕 PAGO DE SUSCRIPCIÓN FALLIDO
        elif event_name == 'subscription_payment_failed':
            subscription_id = data.get('id')
            
            print(f"❌ Pago de suscripción fallido: {subscription_id}")
            
            # Notificar al cliente por WhatsApp
            
            return data
        
        # 🆕 SUSCRIPCIÓN CANCELADA
        elif event_name == 'subscription_cancelled':
            subscription_id = data.get('id')
            
            print(f"⚠️ Suscripción cancelada: {subscription_id}")
            
            return data
        
        return event
        
    except Exception as e:
        print(f"❌ Error en webhook: {e}")
        import traceback
        traceback.print_exc()
        return None

# ==================== ENDPOINTS PARA FLASK ====================

def agregar_rutas_lemonsqueezy(app):
    """Agrega las rutas de Lemonsqueezy a tu app Flask"""
    
    # 🆕 IMPORTAR FUNCIÓN DE WHATSAPP
    try:
        import sys
        bot_module = sys.modules.get('__main__')
        enviar_mensaje = getattr(bot_module, 'enviar_mensaje', None)
        
        if enviar_mensaje:
            print("✅ Función enviar_mensaje encontrada")
        else:
            print("⚠️ Función enviar_mensaje no encontrada")
    except Exception as e:
        print(f"⚠️ Error importando enviar_mensaje: {e}")
        enviar_mensaje = None
    
    @app.route('/create-lemon-checkout', methods=['POST'])
    def create_lemon_checkout():
        """Crea un checkout de Lemonsqueezy"""
        try:
            data = request.json
            variant_id = data.get('variantId')  # ID del producto en Lemonsqueezy
            customer_email = data.get('email')
            customer_phone = data.get('phone')
            
            if not variant_id:
                return jsonify({'error': 'Falta variantId'}), 400
            
            checkout_url = crear_checkout(
                variant_id=variant_id,
                customer_email=customer_email,
                customer_phone=customer_phone
            )
            
            if checkout_url:
                return jsonify({'url': checkout_url})
            else:
                return jsonify({'error': 'No se pudo crear el checkout'}), 500
        
        except Exception as e:
            print(f"❌ Error: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/webhook/lemonsqueezy', methods=['POST'])
    def lemonsqueezy_webhook():
        """Endpoint para webhooks de Lemonsqueezy"""
        try:
            payload = request.data
            signature = request.headers.get('X-Signature')
            
            if not signature:
                return jsonify({'error': 'Sin firma'}), 400
            
            event = webhook_lemonsqueezy_handler(payload, signature, enviar_mensaje)
            
            if event:
                return jsonify({'status': 'success'}), 200
            else:
                return jsonify({'error': 'Webhook inválido'}), 400
        
        except Exception as e:
            print(f"❌ Error en webhook: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/success-lemon')
    def success_lemon():
        """Página de éxito después del pago con Lemonsqueezy"""
        return """
        <html>
        <head>
            <title>✅ Pago Exitoso - TurnosBot</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    text-align: center;
                    padding: 50px;
                    background: linear-gradient(135deg, #25D366 0%, #128C7E 100%);
                    color: white;
                }
                .container {
                    background: white;
                    color: #333;
                    padding: 50px;
                    border-radius: 20px;
                    max-width: 600px;
                    margin: 0 auto;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                }
                h1 { color: #25D366; }
                .check {
                    font-size: 80px;
                    color: #25D366;
                    margin: 20px 0;
                }
                .btn {
                    background: #25D366;
                    color: white;
                    padding: 15px 40px;
                    text-decoration: none;
                    border-radius: 50px;
                    display: inline-block;
                    margin-top: 20px;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="check">✅</div>
                <h1>¡Pago Exitoso!</h1>
                <p style="font-size: 1.2rem; margin: 20px 0;">
                    Gracias por tu compra. Tu bot será configurado en las próximas 24-48 horas.
                </p>
                <p>📱 Recibirás un WhatsApp con los detalles de activación.</p>
                <a href="https://wa.me/5492974924147?text=Hola,%20acabo%20de%20realizar%20el%20pago%20con%20Lemonsqueezy" 
                   class="btn">
                    💬 Contactar Soporte
                </a>
                <br><br>
                <a href="/" style="color: #666; text-decoration: none;">
                    ← Volver al inicio
                </a>
            </div>
        </body>
        </html>
        """
    
    print("✅ Rutas de Lemonsqueezy agregadas")