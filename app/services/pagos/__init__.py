"""
Registry de proveedores de pago.

booking_handler.py y el webhook llaman SOLO a obtener_proveedor() — no
conocen a MercadoPago ni a Stripe. Agregar un proveedor nuevo el día de
mañana es: crear stripe_provider.py implementando ProveedorDePagos, y
sumarlo acá.
"""

from app.services.pagos.mercadopago_provider import MercadoPagoProvider

_PROVEEDORES = {
    "mercadopago": MercadoPagoProvider(),
    # "stripe": StripeProvider(),  # cuando se sume pagos internacionales
}


def obtener_proveedor(nombre: str):
    """nombre: 'mercadopago', 'stripe', etc. — viene de config['proveedor_pago']"""
    return _PROVEEDORES.get(nombre)


def proveedores_disponibles() -> list:
    return list(_PROVEEDORES.keys())
