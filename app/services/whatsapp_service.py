"""
Servicio de WhatsApp (Twilio)
Envío de mensajes de texto y mensajes con plantilla (Content API).

⚠️ ESTE ARCHIVO REEMPLAZA A app/services/whatsapp_service.py
El original que subiste es literalmente una copia de app/core/config.py
(confirmado con `git show`), y por eso `whatsapp_service` no existe como
símbolo importable. Todo el bot depende de este objeto, así que sin esto
el proyecto no puede enviar mensajes.

Reconstruido en base a cómo lo llama el resto del código:
  - whatsapp_service.enviar_mensaje(mensaje, numero)
  - whatsapp_service.enviar_con_plantilla(telefono=..., content_sid=..., variables={...})
(ver notification_service.py, booking_handler.py, test_plantillas.py, costo_mensaje.py)

Si tu implementación original hacía algo distinto o más específico
(reintentos, logging particular, etc.), decime y lo ajustamos —
esto cubre el contrato que usa el resto del código, pero no puedo
recuperar lógica que no esté reflejada en cómo se lo invoca.
"""

import os
import json
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


class WhatsAppService:
    """Envío de mensajes de WhatsApp vía Twilio."""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.numero_from = os.getenv("TWILIO_WHATSAPP_NUMBER")  # sin prefijo whatsapp:, ej "+15017122661"

        if not all([self.account_sid, self.auth_token, self.numero_from]):
            print("⚠️ WhatsAppService: faltan credenciales de Twilio en el entorno")
            self.client = None
        else:
            self.client = Client(self.account_sid, self.auth_token)

    @staticmethod
    def _normalizar(numero: str) -> str:
        """Asegura el prefijo whatsapp: sin duplicarlo."""
        numero = (numero or "").strip()
        if numero.startswith("whatsapp:"):
            return numero
        return f"whatsapp:{numero}"

    def enviar_mensaje(self, mensaje: str, numero: str):
        """
        Envía un mensaje de texto libre por WhatsApp.

        Args:
            mensaje: Texto a enviar
            numero: Número destino, con o sin prefijo "whatsapp:"

        Returns:
            El SID del mensaje si se envió, None si falló.
        """
        if not self.client:
            print("❌ WhatsAppService no configurado, no se puede enviar")
            return None

        try:
            msg = self.client.messages.create(
                from_=self._normalizar(self.numero_from),
                to=self._normalizar(numero),
                body=mensaje,
            )
            print(f"✅ WhatsApp enviado a {numero} — SID: {msg.sid}")
            return msg.sid

        except TwilioRestException as e:
            print(f"❌ Error de Twilio enviando a {numero}: {e}")
            return None
        except Exception as e:
            print(f"❌ Error inesperado enviando WhatsApp a {numero}: {e}")
            return None

    def enviar_con_plantilla(self, telefono: str, content_sid: str, variables: dict):
        """
        Envía un mensaje usando una plantilla (Content API) ya aprobada por Meta.

        Args:
            telefono: Número destino, con o sin prefijo "whatsapp:"
            content_sid: El Content SID de la plantilla (empieza con HX...)
            variables: Dict de variables posicionales, ej {"1": "Juan", "2": "Lunes"}

        Returns:
            El SID del mensaje si se envió, None si falló.
        """
        if not self.client:
            print("❌ WhatsAppService no configurado, no se puede enviar")
            return None

        if not content_sid or content_sid == "HXxxxxx":
            print("⚠️ content_sid no configurado, usando enviar_mensaje como fallback no aplica aquí")
            return None

        try:
            msg = self.client.messages.create(
                from_=self._normalizar(self.numero_from),
                to=self._normalizar(telefono),
                content_sid=content_sid,
                content_variables=json.dumps(variables),
            )
            print(f"✅ Plantilla {content_sid} enviada a {telefono} — SID: {msg.sid}")
            return msg.sid

        except TwilioRestException as e:
            print(f"❌ Error de Twilio (plantilla) enviando a {telefono}: {e}")
            return None
        except Exception as e:
            print(f"❌ Error inesperado enviando plantilla a {telefono}: {e}")
            return None


# Singleton — mismo patrón que payment_service, importado como instancia ya creada
whatsapp_service = WhatsAppService()
