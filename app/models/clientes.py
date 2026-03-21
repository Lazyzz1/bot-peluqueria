from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class PlanEnum(str, Enum):
    argentina = "argentina"
    internacional = "internacional"


class EstadoPagoEnum(str, Enum):
    pendiente = "pendiente"
    pagado = "pagado"
    cancelado = "cancelado"


class PeluqueroContacto(BaseModel):
    nombre: str
    telefono: str  # WhatsApp con código de país


class ClienteCreate(BaseModel):
    # Datos personales
    nombre: str
    apellido: str
    email: EmailStr
    telefono: str  # WhatsApp del dueño

    # Datos del negocio
    nombre_negocio: str
    ubicacion: str
    horarios: str
    servicios: str  # texto libre: "Corte $5000, Tinte $12000..."

    # Equipo
    cantidad_peluqueros: int = Field(ge=1, le=5)
    peluqueros: List[PeluqueroContacto]

    # Plan elegido
    plan: PlanEnum


class ClienteDB(ClienteCreate):
    """Modelo tal como se guarda en MongoDB"""
    estado_pago: EstadoPagoEnum = EstadoPagoEnum.pendiente
    payment_id: Optional[str] = None        # ID del pago de MP o LemonSqueezy
    bot_configurado: bool = False
    creado_en: datetime = Field(default_factory=datetime.utcnow)
    actualizado_en: datetime = Field(default_factory=datetime.utcnow)


class ClienteResponse(BaseModel):
    id: str
    payment_url: str
    mensaje: str = "Datos guardados correctamente. Completá el pago para reservar tu lugar."