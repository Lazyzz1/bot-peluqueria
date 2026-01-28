from datetime import datetime
from zoneinfo import ZoneInfo
import pytz

def ahora_utc():
    return datetime.now(ZoneInfo("UTC"))

def ahora_local(cliente_id, peluquerias):
    tz = ZoneInfo(peluquerias[cliente_id]["timezone"])
    return ahora_utc().astimezone(tz)

def local_a_utc(cliente_id, fecha_local, peluquerias):
    tz = ZoneInfo(peluquerias[cliente_id]["timezone"])
    return fecha_local.replace(tzinfo=tz).astimezone(ZoneInfo("UTC"))

def utc_a_local(cliente_id, fecha_utc, peluquerias):
    tz = ZoneInfo(peluquerias[cliente_id]["timezone"])
    return fecha_utc.astimezone(tz)

def crear_datetime_local(cliente_id, peluquerias, fecha, hora_str):
    """
    Es un datetime en el timezone del cliente
    
    Args:
        cliente_id: ID del cliente
        peluquerias: Dict de configuración
        fecha: objeto date
        hora_str: "09:00"
    
    Returns:
        datetime con timezone del cliente
    """

    tz_name = peluquerias[cliente_id]["timezone"]
    tz = pytz.timezone(tz_name)
    
    hora_int = int(hora_str.split(':')[0])
    minuto_int = int(hora_str.split(':')[1])
    
    dt_naive = datetime.combine(fecha, datetime.min.time()).replace(
        hour=hora_int,
        minute=minuto_int
    )
    
    return tz.localize(dt_naive)