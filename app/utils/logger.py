"""
Sistema de logging centralizado para TurnosBot
Uso: from app.utils.logger import logger, log_error, log_turno, log_pago

Niveles:
- logger.debug()   → detalles internos (solo en desarrollo)
- logger.info()    → eventos normales
- logger.warning() → algo raro pero no crítico
- logger.error()   → errores que necesitan atención
- logger.critical()→ falla total del sistema
"""

import logging
import os
import traceback
from datetime import datetime

# ── Formato ──────────────────────────────────────────────────
# En Railway los logs se ven así:
# 2026-04-10 03:14:22 | ERROR    | webhook.payments | Pago fallido cliente_001
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Nivel según entorno ───────────────────────────────────────
NIVEL = logging.DEBUG if os.getenv("FLASK_ENV") == "development" else logging.INFO


def get_logger(nombre: str) -> logging.Logger:
    """
    Crea un logger con el nombre del módulo.
    Uso: logger = get_logger(__name__)
    """
    log = logging.getLogger(nombre)

    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        log.addHandler(handler)
        log.setLevel(NIVEL)
        log.propagate = False

    return log


# Logger global del sistema
logger = get_logger("turnosbot")


# ── Helpers para eventos comunes ──────────────────────────────

def log_error(modulo: str, mensaje: str, exc: Exception = None):
    """Registra un error con traceback opcional."""
    log = get_logger(modulo)
    if exc:
        log.error(f"{mensaje} | {type(exc).__name__}: {exc}")
        log.debug(traceback.format_exc())
    else:
        log.error(mensaje)


def log_turno(accion: str, peluqueria_key: str, telefono: str, detalle: str = ""):
    """Registra eventos de turnos."""
    log = get_logger("turnos")
    log.info(f"[{accion.upper()}] peluqueria={peluqueria_key} tel={telefono} {detalle}".strip())


def log_pago(evento: str, provider: str, cliente_id: str, monto=None, estado: str = ""):
    """Registra eventos de pagos."""
    log = get_logger("pagos")
    monto_str = f"monto={monto}" if monto else ""
    log.info(f"[{evento.upper()}] provider={provider} cliente={cliente_id} {monto_str} estado={estado}".strip())


def log_whatsapp(accion: str, numero: str, peluqueria_key: str = "", ok: bool = True):
    """Registra envíos de WhatsApp."""
    log = get_logger("whatsapp")
    nivel = logging.INFO if ok else logging.WARNING
    log.log(nivel, f"[{accion.upper()}] a={numero} peluqueria={peluqueria_key} ok={ok}")


def log_suscripcion(evento: str, peluqueria_key: str, detalle: str = ""):
    """Registra eventos de suscripciones."""
    log = get_logger("suscripciones")
    log.info(f"[{evento.upper()}] peluqueria={peluqueria_key} {detalle}".strip())