"""
Verificación de Suscripción
Controla si una peluquería tiene suscripción activa.

Flujo:
- Trial activo (7 días)     → bot responde normal
- Trial vencido             → avisa al dueño, 24hs de gracia, luego corta
- En gracia (24hs)          → bot responde normal, dueño ya fue avisado
- Gracia vencida sin pagar  → bot corta para todos
- Suscripción activa        → bot responde normal
- Cancelada                 → bot corta para todos
"""

import os
from datetime import datetime, timedelta
from app.core.database import clientes_collection
from app.services.whatsapp_service import whatsapp_service


def verificar_suscripcion(peluqueria_key: str) -> dict:
    """
    Verifica si la peluquería puede usar el bot.

    Returns:
        dict: {
            "activa": bool,
            "motivo": str,
            "dias_restantes": int | None,
        }
    """
    try:
        cliente = clientes_collection.find_one({"peluqueria_key": peluqueria_key})

        # No está en MongoDB → es demo/dev, dejar pasar siempre
        if not cliente:
            return {"activa": True, "motivo": "demo", "dias_restantes": None}

        estado_pago = cliente.get("estado_pago", "pendiente")
        ahora = datetime.utcnow()

        # ── Cancelada → cortar ──────────────────────────────────────
        if estado_pago == "cancelado":
            return {"activa": False, "motivo": "cancelado", "dias_restantes": None}

        # ── Pendiente (nunca pagó) → cortar ────────────────────────
        if estado_pago == "pendiente":
            return {"activa": False, "motivo": "pendiente", "dias_restantes": None}

        # ── Pagado → verificar trial y gracia ──────────────────────
        if estado_pago == "pagado":

            # Suscripción renovada activa → OK
            if cliente.get("suscripcion_activa", False):
                return {"activa": True, "motivo": "activa", "dias_restantes": None}

            trial_inicio = cliente.get("trial_inicio")
            if not trial_inicio:
                return {"activa": True, "motivo": "activa", "dias_restantes": None}

            fin_trial = trial_inicio + timedelta(days=7)

            # Dentro del trial → OK
            if ahora < fin_trial:
                dias = (fin_trial - ahora).days
                return {"activa": True, "motivo": "trial", "dias_restantes": max(dias, 0)}

            # Trial vencido → verificar período de gracia de 24hs
            gracia_inicio = cliente.get("gracia_inicio")

            if not gracia_inicio:
                # Primera vez que detectamos el vencimiento → iniciar gracia y avisar al dueño
                _iniciar_gracia_y_avisar(cliente, peluqueria_key)
                return {"activa": True, "motivo": "gracia", "dias_restantes": 0}

            fin_gracia = gracia_inicio + timedelta(hours=24)

            if ahora < fin_gracia:
                # Dentro de las 24hs de gracia → bot sigue respondiendo
                horas_restantes = int((fin_gracia - ahora).total_seconds() / 3600)
                return {"activa": True, "motivo": "gracia", "dias_restantes": horas_restantes}
            else:
                # Gracia vencida y sin pago → cortar todo
                return {"activa": False, "motivo": "gracia_vencida", "dias_restantes": 0}

        # Cualquier otro estado → dejar pasar (no bloquear por error)
        return {"activa": True, "motivo": "activa", "dias_restantes": None}

    except Exception as e:
        print(f"❌ Error verificando suscripción de {peluqueria_key}: {e}")
        # Si falla la verificación, no bloquear al bot
        return {"activa": True, "motivo": "error", "dias_restantes": None}


def _iniciar_gracia_y_avisar(cliente: dict, peluqueria_key: str):
    """
    Marca el inicio del período de gracia en MongoDB
    y le avisa al dueño por WhatsApp.
    """
    try:
        ahora = datetime.utcnow()

        # Guardar gracia_inicio en MongoDB
        clientes_collection.update_one(
            {"peluqueria_key": peluqueria_key},
            {"$set": {
                "gracia_inicio": ahora,
                "actualizado_en": ahora,
            }}
        )

        # Obtener teléfono del dueño y link de pago
        telefono_dueno = cliente.get("telefono", "")
        plan = cliente.get("plan", "argentina")
        payment_url = cliente.get("payment_url", "https://turnosbot-landing.vercel.app/#pricing")
        nombre_negocio = cliente.get("nombre_negocio", "tu negocio")

        if not telefono_dueno:
            print(f"⚠️ No hay teléfono del dueño para {peluqueria_key}")
            return

        mensaje = (
            f"⚠️ *TurnosBot - Período de prueba vencido*\n\n"
            f"Hola! Tu prueba gratuita de *{nombre_negocio}* venció.\n\n"
            f"El bot seguirá funcionando por *24 horas más*.\n"
            f"Para no perder el servicio, activá tu suscripción:\n\n"
            f"👉 {payment_url}\n\n"
            f"Precio: {'$24.500 ARS/mes' if plan == 'argentina' else '$34.50 USD/mes'}\n"
            f"¿Consultas? Escribinos al wa.me/5492975375667"
        )

        whatsapp_service.enviar_mensaje(mensaje, f"whatsapp:{telefono_dueno}")
        print(f"✅ Aviso de vencimiento enviado al dueño de {peluqueria_key}: {telefono_dueno}")

    except Exception as e:
        print(f"❌ Error iniciando gracia para {peluqueria_key}: {e}")