"""
Servicio de Pagos
Integración con LemonSqueezy (internacional) y MercadoPago (Argentina)
"""

import os
import requests
import hmac
import hashlib
from datetime import datetime, timedelta


class PaymentService:
    """Servicio para gestionar pagos con múltiples proveedores"""
    
    def __init__(self):
        """Inicializa el servicio de pagos"""
        # LemonSqueezy (internacional)
        self.lemonsqueezy_api_key = os.getenv("LEMONSQUEEZY_API_KEY")
        self.lemonsqueezy_store_id = os.getenv("LEMONSQUEEZY_STORE_ID")
        self.lemonsqueezy_webhook_secret = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET")
        
        # MercadoPago (Argentina)
        self.mercadopago_access_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN")
        self.mercadopago_public_key = os.getenv("MERCADOPAGO_PUBLIC_KEY")
        self.mercadopago_webhook_secret = os.getenv("MERCADOPAGO_WEBHOOK_SECRET")
        
        # URLs
        self.app_url = os.getenv("APP_URL", "http://localhost:3000")
        
        print("💳 PaymentService inicializado")
        if self.lemonsqueezy_api_key:
            print("   ✅ LemonSqueezy configurado")
        if self.mercadopago_access_token:
            print("   ✅ MercadoPago configurado")
    
    # ==================== LEMONSQUEEZY (INTERNACIONAL) ====================
    
    def crear_checkout_lemonsqueezy(self, turno_data):
        """
        Crea un checkout de LemonSqueezy para pago internacional
        
        Args:
            turno_data: {
                "peluqueria_key": str,
                "cliente_nombre": str,
                "cliente_email": str,
                "cliente_telefono": str,
                "servicio": str,
                "precio": int,
                "fecha_hora": datetime,
                "peluquero": str
            }
        
        Returns:
            dict: {"url": str, "checkout_id": str} o None
        """
        if not self.lemonsqueezy_api_key:
            print("⚠️ LemonSqueezy no configurado")
            return None
        
        try:
            url = "https://api.lemonsqueezy.com/v1/checkouts"
            
            headers = {
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
                "Authorization": f"Bearer {self.lemonsqueezy_api_key}"
            }
            
            # Crear metadata para identificar el turno
            metadata = {
                "peluqueria_key": turno_data["peluqueria_key"],
                "cliente_nombre": turno_data["cliente_nombre"],
                "cliente_telefono": turno_data["cliente_telefono"],
                "servicio": turno_data["servicio"],
                "fecha_hora": turno_data["fecha_hora"].isoformat(),
                "peluquero": turno_data.get("peluquero", ""),
                "tipo": "reserva_turno"
            }
            
            payload = {
                "data": {
                    "type": "checkouts",
                    "attributes": {
                        "checkout_data": {
                            "email": turno_data.get("cliente_email", ""),
                            "name": turno_data["cliente_nombre"],
                            "custom": metadata
                        },
                        "product_options": {
                            "name": f"Turno - {turno_data['servicio']}",
                            "description": f"Reserva de turno con {turno_data.get('peluquero', 'peluquero')} el {turno_data['fecha_hora'].strftime('%d/%m/%Y %H:%M')}",
                            "redirect_url": f"{self.app_url}/payment/success",
                        },
                        "checkout_options": {
                            "button_color": "#10b981"
                        }
                    },
                    "relationships": {
                        "store": {
                            "data": {
                                "type": "stores",
                                "id": self.lemonsqueezy_store_id
                            }
                        },
                        "variant": {
                            "data": {
                                "type": "variants",
                                "id": self._get_or_create_variant_lemonsqueezy(
                                    turno_data["servicio"],
                                    turno_data["precio"]
                                )
                            }
                        }
                    }
                }
            }
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 201:
                data = response.json()
                checkout_url = data["data"]["attributes"]["url"]
                checkout_id = data["data"]["id"]
                
                print(f"✅ Checkout LemonSqueezy creado: {checkout_id}")
                return {
                    "url": checkout_url,
                    "checkout_id": checkout_id,
                    "provider": "lemonsqueezy"
                }
            else:
                print(f"❌ Error creando checkout LemonSqueezy: {response.text}")
                return None
        
        except Exception as e:
            print(f"❌ Error en crear_checkout_lemonsqueezy: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_or_create_variant_lemonsqueezy(self, servicio_nombre, precio):
        """
        Obtiene o crea una variante de producto en LemonSqueezy
        (simplificado - en producción deberías tener productos pre-creados)
        """
        # Por ahora retornamos un variant_id fijo
        # En producción, crearías productos en LemonSqueezy y usarías sus IDs
        return os.getenv("LEMONSQUEEZY_DEFAULT_VARIANT_ID", "123456")
    
    def verificar_webhook_lemonsqueezy(self, payload, signature):
        """
        Verifica la firma del webhook de LemonSqueezy
        
        Args:
            payload: Body del request (bytes)
            signature: Header X-Signature
        
        Returns:
            bool: True si la firma es válida
        """
        if not self.lemonsqueezy_webhook_secret:
            print("⚠️ Webhook secret no configurado")
            return False
        
        try:
            expected_signature = hmac.new(
                self.lemonsqueezy_webhook_secret.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
        
        except Exception as e:
            print(f"❌ Error verificando webhook: {e}")
            return False
    
    # ==================== MERCADOPAGO (ARGENTINA) ====================
    
    def crear_preferencia_mercadopago(self, turno_data):
        """
        Crea una preferencia de pago en MercadoPago
        
        Args:
            turno_data: Misma estructura que LemonSqueezy
        
        Returns:
            dict: {"url": str, "preference_id": str} o None
        """
        if not self.mercadopago_access_token:
            print("⚠️ MercadoPago no configurado")
            return None
        
        try:
            url = "https://api.mercadopago.com/checkout/preferences"
            
            headers = {
                "Authorization": f"Bearer {self.mercadopago_access_token}",
                "Content-Type": "application/json"
            }
            
            # Metadata para identificar el turno
            metadata = {
                "peluqueria_key": turno_data["peluqueria_key"],
                "cliente_nombre": turno_data["cliente_nombre"],
                "cliente_telefono": turno_data["cliente_telefono"],
                "servicio": turno_data["servicio"],
                "fecha_hora": turno_data["fecha_hora"].isoformat(),
                "peluquero": turno_data.get("peluquero", ""),
                "tipo": "reserva_turno"
            }
            
            payload = {
                "items": [
                    {
                        "title": f"Turno - {turno_data['servicio']}",
                        "description": f"Reserva con {turno_data.get('peluquero', 'peluquero')} el {turno_data['fecha_hora'].strftime('%d/%m/%Y %H:%M')}",
                        "quantity": 1,
                        "currency_id": "ARS",
                        "unit_price": float(turno_data["precio"])
                    }
                ],
                "payer": {
                    "name": turno_data["cliente_nombre"],
                    "email": turno_data.get("cliente_email", "cliente@email.com"),
                    "phone": {
                        "number": turno_data["cliente_telefono"]
                    }
                },
                "back_urls": {
                    "success": f"{self.app_url}/payment/success",
                    "failure": f"{self.app_url}/payment/failure",
                    "pending": f"{self.app_url}/payment/pending"
                },
                "auto_return": "approved",
                "notification_url": f"{self.app_url}/api/webhooks/mercadopago",
                "metadata": metadata,
                "expires": True,
                "expiration_date_from": datetime.now().isoformat(),
                "expiration_date_to": (datetime.now() + timedelta(hours=2)).isoformat()
            }
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 201:
                data = response.json()
                init_point = data["init_point"]  # URL de pago
                preference_id = data["id"]
                
                print(f"✅ Preferencia MercadoPago creada: {preference_id}")
                return {
                    "url": init_point,
                    "preference_id": preference_id,
                    "provider": "mercadopago"
                }
            else:
                print(f"❌ Error creando preferencia MercadoPago: {response.text}")
                return None
        
        except Exception as e:
            print(f"❌ Error en crear_preferencia_mercadopago: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def verificar_webhook_mercadopago(self, payment_id):
        """
        Verifica un pago de MercadoPago consultando su estado
        
        Args:
            payment_id: ID del pago
        
        Returns:
            dict: Información del pago o None
        """
        if not self.mercadopago_access_token:
            return None
        
        try:
            url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
            
            headers = {
                "Authorization": f"Bearer {self.mercadopago_access_token}"
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Error obteniendo pago: {response.text}")
                return None
        
        except Exception as e:
            print(f"❌ Error verificando pago: {e}")
            return None
    
    # ==================== REEMBOLSOS ====================
    
    def crear_reembolso_mercadopago(self, payment_id, monto=None):
        """
        Crea un reembolso en MercadoPago
        
        Args:
            payment_id: ID del pago a reembolsar
            monto: Monto a reembolsar (None = reembolso total)
        
        Returns:
            dict: Información del reembolso o None
        """
        if not self.mercadopago_access_token:
            return None
        
        try:
            url = f"https://api.mercadopago.com/v1/payments/{payment_id}/refunds"
            
            headers = {
                "Authorization": f"Bearer {self.mercadopago_access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {}
            if monto:
                payload["amount"] = float(monto)
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 201:
                refund_data = response.json()
                print(f"✅ Reembolso creado: {refund_data['id']}")
                return refund_data
            else:
                print(f"❌ Error creando reembolso: {response.text}")
                return None
        
        except Exception as e:
            print(f"❌ Error en crear_reembolso: {e}")
            return None
    
    def crear_reembolso_lemonsqueezy(self, order_id, monto=None):
        """
        Crea un reembolso en LemonSqueezy
        
        Args:
            order_id: ID de la orden
            monto: Monto a reembolsar (None = reembolso total)
        
        Returns:
            dict: Información del reembolso o None
        """
        if not self.lemonsqueezy_api_key:
            return None
        
        try:
            url = f"https://api.lemonsqueezy.com/v1/orders/{order_id}/refund"
            
            headers = {
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
                "Authorization": f"Bearer {self.lemonsqueezy_api_key}"
            }
            
            payload = {
                "data": {
                    "type": "refunds",
                    "attributes": {}
                }
            }
            
            if monto:
                payload["data"]["attributes"]["amount"] = int(monto * 100)  # Centavos
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 201:
                refund_data = response.json()
                print(f"✅ Reembolso LemonSqueezy creado")
                return refund_data
            else:
                print(f"❌ Error creando reembolso LemonSqueezy: {response.text}")
                return None
        
        except Exception as e:
            print(f"❌ Error en crear_reembolso_lemonsqueezy: {e}")
            return None
    
    # ==================== UTILIDADES ====================
    
    def detectar_pais(self, telefono):
        """
        Detecta el país según el código del teléfono
        
        Args:
            telefono: Número de teléfono
        
        Returns:
            str: 'AR' para Argentina, 'INTL' para internacional
        """
        telefono_limpio = telefono.replace("+", "").replace(" ", "").replace("-", "")
        
        # Argentina: +54
        if telefono_limpio.startswith("54"):
            return "AR"
        
        return "INTL"
    
    def obtener_proveedor_recomendado(self, telefono):
        """
        Recomienda el proveedor de pago según el país
        
        Args:
            telefono: Número de teléfono del cliente
        
        Returns:
            str: 'mercadopago' o 'lemonsqueezy'
        """
        pais = self.detectar_pais(telefono)
        
        if pais == "AR" and self.mercadopago_access_token:
            return "mercadopago"
        elif self.lemonsqueezy_api_key:
            return "lemonsqueezy"
        else:
            return None


# Instancia global
payment_service = PaymentService()