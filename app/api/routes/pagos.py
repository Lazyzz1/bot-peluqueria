"""
Rutas de conexión de pagos
===========================
El dueño de cada negocio conecta su propia cuenta de pago (MercadoPago
por ahora) siguiendo un link que le mandamos por WhatsApp durante el
aprovisionamiento automático. No requiere que abra la landing ni nada del
lado del frontend — es directo contra este backend.
"""

from flask import Blueprint, request, redirect

from app.services.pagos import obtener_proveedor
from app.services.whatsapp_service import whatsapp_service
from app.core.database import clientes_collection, guardar_config_peluqueria
import os

pagos_bp = Blueprint('pagos', __name__)


@pagos_bp.route('/pagos/conectar/<proveedor_nombre>', methods=['GET'])
def conectar(proveedor_nombre):
    """
    Ej: /api/pagos/conectar/mercadopago?peluqueria_key=peluqueria_el_estilo_a1b2
    Redirige al dueño a la pantalla de autorización del proveedor.
    """
    peluqueria_key = request.args.get('peluqueria_key')
    if not peluqueria_key:
        return "Falta peluqueria_key", 400

    proveedor = obtener_proveedor(proveedor_nombre)
    if not proveedor:
        return f"Proveedor '{proveedor_nombre}' no soportado todavía", 400

    url = proveedor.url_de_conexion(peluqueria_key, redirect_state=peluqueria_key)
    return redirect(url)


@pagos_bp.route('/pagos/callback/<proveedor_nombre>', methods=['GET'])
def callback(proveedor_nombre):
    """A donde vuelve el dueño después de autorizar en MercadoPago/Stripe/etc."""
    proveedor = obtener_proveedor(proveedor_nombre)
    if not proveedor:
        return f"Proveedor '{proveedor_nombre}' no soportado todavía", 400

    resultado = proveedor.manejar_callback_conexion(request.args)

    if not resultado:
        return _pagina_html(
            "❌ No pudimos conectar tu cuenta",
            "Algo falló. Pedile a quien te dio de alta que te reenvíe el link.",
        )

    peluqueria_key = resultado.get("peluqueria_key")

    # A partir de ahora el bot va a pedir seña en las reservas de este negocio
    guardar_config_peluqueria(peluqueria_key, {
        "requiere_pago": True,
        "proveedor_pago": proveedor.nombre,
    })

    # Avisar al dueño por WhatsApp
    cliente = clientes_collection.find_one({"peluqueria_key": peluqueria_key})
    if cliente and cliente.get("telefono"):
        whatsapp_service.enviar_mensaje(
            f"✅ ¡Listo! Conectaste tu cuenta de {proveedor.nombre.capitalize()}.\n\n"
            f"A partir de ahora, cuando un cliente saque un turno, la seña "
            f"se va a acreditar directo en tu cuenta.",
            f"whatsapp:{cliente['telefono']}",
        )

    # Avisar al admin
    admin = os.getenv("ADMIN_WHATSAPP", "")
    if admin:
        whatsapp_service.enviar_mensaje(
            f"🔗 {peluqueria_key} conectó su cuenta de {proveedor.nombre}",
            f"whatsapp:{admin}",
        )

    return _pagina_html(
        "✅ Cuenta conectada",
        "Ya podés cerrar esta ventana. Te avisamos por WhatsApp.",
    )


def _pagina_html(titulo: str, mensaje: str) -> str:
    """Página mínima de confirmación — no depende del frontend de Next.js."""
    return f"""
    <html>
      <head><meta charset="utf-8"><title>{titulo}</title></head>
      <body style="font-family: sans-serif; background:#121212; color:#fff;
                    display:flex; align-items:center; justify-content:center;
                    height:100vh; text-align:center; padding:2rem;">
        <div>
          <h1>{titulo}</h1>
          <p>{mensaje}</p>
        </div>
      </body>
    </html>
    """
