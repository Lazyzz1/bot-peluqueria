"""
Capa de pagos — interfaz común para cobrar señas de turnos
============================================================

    TurnosBot
       │
       └── Sistema de pagos  (este paquete: app/services/pagos/)
              │
              ├── MercadoPagoProvider  (Argentina, ya implementado)
              ├── StripeProvider        (internacional, a futuro)
              └── ...otros proveedores futuros

Cada peluquería elige (campo "proveedor_pago" en su config) con qué
procesador cobra sus señas. booking_handler.py y el webhook de pagos NO
saben nada de MercadoPago ni de Stripe — solo hablan con esta interfaz.
"""

from abc import ABC, abstractmethod


class ProveedorDePagos(ABC):
    """Todo proveedor de pagos (MercadoPago, Stripe, etc.) implementa esto."""

    nombre: str = "base"

    @abstractmethod
    def url_de_conexion(self, peluqueria_key: str, redirect_state: str) -> str:
        """
        Devuelve la URL a la que hay que mandar al dueño del negocio para
        que conecte su propia cuenta (OAuth). Se manda por WhatsApp una
        sola vez, durante el aprovisionamiento.
        """
        raise NotImplementedError

    @abstractmethod
    def manejar_callback_conexion(self, args: dict) -> dict | None:
        """
        Se llama desde la ruta de callback cuando el dueño vuelve de
        autorizar. Debe devolver un dict con lo necesario para guardar la
        conexión (tokens, ids, lo que sea) o None si falló.
        """
        raise NotImplementedError

    @abstractmethod
    def crear_cobro_sena(self, peluqueria_key: str, turno_data: dict) -> dict | None:
        """
        Genera el link de pago de la seña.

        turno_data trae al menos:
            monto, turno_pendiente_id, cliente_nombre, cliente_telefono,
            cliente_email (opcional), descripcion

        Returns:
            {"url": str, "id": str} o None si el negocio no tiene esta
            forma de pago conectada / configurada.
        """
        raise NotImplementedError

    @abstractmethod
    def esta_conectado(self, peluqueria_key: str) -> bool:
        """Si el negocio ya conectó su cuenta con este proveedor."""
        raise NotImplementedError
