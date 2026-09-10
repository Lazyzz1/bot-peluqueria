"""
Proveedor de pagos: MercadoPago (Argentina)
=============================================
Usa el flujo OAuth "Authorization Code" de MercadoPago para que CADA
negocio conecte su PROPIA cuenta. La seña se cobra con el access_token
del negocio (no el tuyo), así que la plata cae directo en su cuenta —
vos nunca la tenés en la tuya.

Verificado contra la documentación oficial de MercadoPago (developers.
mercadopago.com, sección OAuth) al momento de escribir esto:

  1) Mandás al dueño a:
     https://auth.mercadopago.com/authorization
         ?client_id=TU_APP_ID
         &response_type=code
         &platform_id=mp
         &state=...
         &redirect_uri=...

  2) MP te devuelve un `code` en el redirect_uri (válido 10 min, un solo uso)

  3) Lo canjeás en POST https://api.mercadopago.com/oauth/token con
     grant_type=authorization_code — la respuesta trae:
         access_token, refresh_token, user_id, public_key, expires_in

  4) Para cobrar, creás la preferencia de siempre pero con
     Authorization: Bearer <access_token DEL NEGOCIO> — la plata liquida
     en su cuenta. Si en algún momento querés cobrar comisión, se agrega
     el campo `marketplace_fee` al payload.

⚠️ Necesitás una Aplicación registrada en MercadoPago Developers (distinta
de tu access token personal actual) para tener TWILIO_WABA... digo,
MERCADOPAGO_CLIENT_ID y MERCADOPAGO_CLIENT_SECRET. Se crea gratis desde
tu panel de desarrollador.

⚠️ El access_token del negocio dura 180 días y HAY que refrescarlo con
el refresh_token antes de que expire (ver `_access_token_valido`) — dejé
la lógica de refresh, pero no pude probarla en vivo.
"""

import os
import requests
from datetime import datetime, timedelta

from app.services.pagos.base import ProveedorDePagos
from app.core.database import (
    guardar_conexion_pago,
    obtener_conexion_pago,
    crear_turno_pendiente_pago,
)

MP_AUTH_URL = "https://auth.mercadopago.com/authorization"
MP_TOKEN_URL = "https://api.mercadopago.com/oauth/token"
MP_PREFERENCE_URL = "https://api.mercadopago.com/checkout/preferences"


class MercadoPagoProvider(ProveedorDePagos):
    nombre = "mercadopago"

    def __init__(self):
        self.client_id = os.getenv("MERCADOPAGO_CLIENT_ID")
        self.client_secret = os.getenv("MERCADOPAGO_CLIENT_SECRET")
        self.app_url = os.getenv("APP_URL", os.getenv("WEBHOOK_URL", ""))
        self.redirect_uri = f"{self.app_url}/api/pagos/callback/mercadopago"

    # ---------- Conexión (OAuth) ----------

    def url_de_conexion(self, peluqueria_key: str, redirect_state: str) -> str:
        return (
            f"{MP_AUTH_URL}?client_id={self.client_id}"
            f"&response_type=code&platform_id=mp"
            f"&state={redirect_state}"
            f"&redirect_uri={self.redirect_uri}"
        )

    def manejar_callback_conexion(self, args: dict) -> dict | None:
        code = args.get("code")
        peluqueria_key = args.get("state")
        if not code or not peluqueria_key:
            return None

        try:
            resp = requests.post(MP_TOKEN_URL, json={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            }, timeout=20)

            if not resp.ok:
                print(f"❌ Error canjeando code de MP: {resp.status_code} {resp.text}")
                return None

            data = resp.json()
            conexion = {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "user_id": data.get("user_id"),
                "public_key": data.get("public_key"),
                "expires_at": (datetime.utcnow() + timedelta(seconds=data.get("expires_in", 15552000))).isoformat(),
            }
            guardar_conexion_pago(peluqueria_key, self.nombre, conexion)
            return {"peluqueria_key": peluqueria_key, **conexion}

        except Exception as e:
            print(f"❌ Error en manejar_callback_conexion (MP): {e}")
            return None

    def esta_conectado(self, peluqueria_key: str) -> bool:
        return obtener_conexion_pago(peluqueria_key, self.nombre) is not None

    # ---------- Refresco de token ----------

    def _access_token_valido(self, conexion: dict) -> str | None:
        """Devuelve un access_token vigente, refrescándolo si hace falta."""
        expira = conexion.get("expires_at")
        if expira and datetime.fromisoformat(expira) > datetime.utcnow() + timedelta(days=1):
            return conexion["access_token"]

        # Refrescar
        try:
            resp = requests.post(MP_TOKEN_URL, json={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": conexion.get("refresh_token"),
            }, timeout=20)
            if not resp.ok:
                print(f"❌ Error refrescando token de MP: {resp.text}")
                return conexion.get("access_token")  # probamos con el viejo, por las dudas

            data = resp.json()
            nueva_conexion = {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_at": (datetime.utcnow() + timedelta(seconds=data.get("expires_in", 15552000))).isoformat(),
            }
            guardar_conexion_pago(conexion["peluqueria_key"], self.nombre, nueva_conexion)
            return nueva_conexion["access_token"]
        except Exception as e:
            print(f"❌ Error inesperado refrescando token de MP: {e}")
            return conexion.get("access_token")

    # ---------- Cobro de la seña ----------

    def crear_cobro_sena(self, peluqueria_key: str, turno_data: dict) -> dict | None:
        conexion = obtener_conexion_pago(peluqueria_key, self.nombre)
        if not conexion:
            print(f"⚠️ {peluqueria_key} no tiene MercadoPago conectado")
            return None

        conexion["peluqueria_key"] = peluqueria_key
        access_token = self._access_token_valido(conexion)
        if not access_token:
            return None

        turno_pendiente_id = turno_data["turno_pendiente_id"]

        payload = {
            "items": [{
                "title": turno_data.get("descripcion", "Seña de turno"),
                "quantity": 1,
                "currency_id": "ARS",
                "unit_price": float(turno_data["monto"]),
            }],
            "payer": {
                "name": turno_data.get("cliente_nombre", ""),
                "phone": {"number": turno_data.get("cliente_telefono", "")},
            },
            "back_urls": {
                "success": f"{self.app_url}/payment/success",
                "failure": f"{self.app_url}/payment/failure",
                "pending": f"{self.app_url}/payment/pending",
            },
            "auto_return": "approved",
            "notification_url": f"{self.app_url}/api/webhooks/mercadopago",
            "external_reference": turno_pendiente_id,
            "metadata": {
                "tipo": "reserva_turno_sena",
                "turno_pendiente_id": turno_pendiente_id,
                "peluqueria_key": peluqueria_key,
            },
            "expires": True,
            "expiration_date_from": datetime.utcnow().isoformat(),
            "expiration_date_to": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
        }

        try:
            resp = requests.post(
                MP_PREFERENCE_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
            if resp.status_code != 201:
                print(f"❌ Error creando preferencia (seña) para {peluqueria_key}: {resp.text}")
                return None

            data = resp.json()
            return {"url": data["init_point"], "id": data["id"]}

        except Exception as e:
            print(f"❌ Error inesperado creando cobro de seña: {e}")
            return None
