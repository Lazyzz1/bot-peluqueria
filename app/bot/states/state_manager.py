import os
import json
import redis
from datetime import datetime, date

# Railway inyecta REDIS_URL automáticamente
# En local, se usa localhost
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    r = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5
    )
    # Test de conexión
    r.ping()
    print("✅ Conectado a Redis")
except Exception as e:
    print(f"❌ Error conectando a Redis: {e}")
    r = None

STATE_TTL = 30 * 60  # 30 minutos

def get_state(user_id):
    """Obtiene el estado del usuario desde Redis"""
    if not r:
        print("⚠️ Redis no disponible")
        return None
    
    try:
        data = r.get(f"user_state:{user_id}")
        return json.loads(data) if data else None
    except Exception as e:
        print(f"❌ Error obteniendo estado: {e}")
        return None

def set_state(user_id, state):
    """Guarda el estado del usuario en Redis con TTL"""
    if not r:
        print("⚠️ Redis no disponible")
        return False
    
    try:
        state_serializado = serializar_estado(state)
        r.setex(
            f"user_state:{user_id}",
            STATE_TTL,
            json.dumps(state_serializado, ensure_ascii=False)
        )
        return True
    except Exception as e:
        print(f"❌ Error guardando estado: {e}")
        return False

def clear_state(user_id):
    """Elimina el estado del usuario"""
    if not r:
        return False
    
    try:
        r.delete(f"user_state:{user_id}")
        return True
    except Exception as e:
        print(f"❌ Error eliminando estado: {e}")
        return False

def serializar_estado(estado):
    """
    Convierte objetos datetime/date a strings ISO
    para guardar en Redis
    """
    estado_limpio = {}
    
    for key, value in estado.items():
        if isinstance(value, (datetime, date)):
            estado_limpio[key] = value.isoformat()
        elif isinstance(value, list):
            estado_limpio[key] = [
                v.isoformat() if isinstance(v, (datetime, date)) else v
                for v in value
            ]
        elif isinstance(value, dict):
            # Recursivo para dicts anidados
            estado_limpio[key] = serializar_estado(value)
        else:
            estado_limpio[key] = value
    
    return estado_limpio

def deserializar_estado(estado):
    """
    Convierte strings ISO de vuelta a datetime/date
    al leer de Redis (uso opcional, normalmente se hace manual)
    """
    if not estado:
        return None
    
    return estado

def obtener_todos_estados():
    """Obtiene todos los estados activos (útil para debug)"""
    if not r:
        return []
    
    try:
        keys = r.keys("user_state:*")
        estados = []
        
        for key in keys:
            data = r.get(key)
            if data:
                estados.append({
                    "user_id": key.replace("user_state:", ""),
                    "estado": json.loads(data)
                })
        
        return estados
    except Exception as e:
        print(f"❌ Error obteniendo estados: {e}")
        return []

def limpiar_estados_expirados():
    """
    Redis maneja esto automáticamente con TTL,
    pero esta función permite forzar limpieza si es necesario
    """
    if not r:
        return 0
    
    try:
        keys = r.keys("user_state:*")
        eliminados = 0
        
        for key in keys:
            ttl = r.ttl(key)
            # Si TTL es -1 (sin expiración) o muy alto, eliminarlo
            if ttl == -1 or ttl > STATE_TTL:
                r.delete(key)
                eliminados += 1
        
        return eliminados
    except Exception as e:
        print(f"❌ Error limpiando estados: {e}")
        return 0