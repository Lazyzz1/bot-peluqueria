"""
State Manager - Gestión de Estados de Usuario con Redis
Versión Mejorada - Enero 2026
"""

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
    print("   Verifica que Redis esté corriendo o que REDIS_URL sea correcto")
    r = None

STATE_TTL = 30 * 60  # 30 minutos

def get_state(user_id):
    """
    Obtiene el estado del usuario desde Redis
    
    Args:
        user_id: Identificador único del usuario (número de teléfono limpio)
    
    Returns:
        dict: Estado del usuario o None si no existe
    """
    if not r:
        print("⚠️ Redis no disponible")
        return None
    
    try:
        data = r.get(f"user_state:{user_id}")
        return json.loads(data) if data else None
    except Exception as e:
        print(f"❌ Error obteniendo estado de {user_id}: {e}")
        return None

def set_state(user_id, state):
    """
    Guarda el estado del usuario en Redis con TTL
    
    Args:
        user_id: Identificador único del usuario
        state: Diccionario con el estado a guardar
    
    Returns:
        bool: True si se guardó correctamente
    """
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
        print(f"❌ Error guardando estado de {user_id}: {e}")
        return False

def clear_state(user_id):
    """
    Elimina el estado del usuario
    
    Args:
        user_id: Identificador único del usuario
    
    Returns:
        bool: True si se eliminó correctamente
    """
    if not r:
        return False
    
    try:
        r.delete(f"user_state:{user_id}")
        return True
    except Exception as e:
        print(f"❌ Error eliminando estado de {user_id}: {e}")
        return False

def renovar_ttl(user_id):
    """
    Renueva el TTL del estado sin modificar los datos
    Útil cuando el usuario está activo en la conversación
    
    Args:
        user_id: Identificador único del usuario
    
    Returns:
        bool: True si se renovó el TTL
    """
    if not r:
        return False
    
    try:
        key = f"user_state:{user_id}"
        if r.exists(key):
            r.expire(key, STATE_TTL)
            return True
        return False
    except Exception as e:
        print(f"❌ Error renovando TTL de {user_id}: {e}")
        return False

def serializar_estado(estado):
    """
    Convierte objetos datetime/date a strings ISO para guardar en Redis
    Maneja recursivamente dicts y listas anidadas
    
    Args:
        estado: Diccionario con el estado (puede contener datetime/date)
    
    Returns:
        dict: Estado serializado (todos los valores JSON-compatibles)
    """
    if not isinstance(estado, dict):
        return estado
    
    estado_limpio = {}
    
    for key, value in estado.items():
        if isinstance(value, (datetime, date)):
            # Convertir datetime/date a ISO string
            estado_limpio[key] = value.isoformat()
        
        elif isinstance(value, list):
            # Manejar listas que puedan contener dicts o datetime
            estado_limpio[key] = []
            for item in value:
                if isinstance(item, dict):
                    estado_limpio[key].append(serializar_estado(item))  # Recursivo
                elif isinstance(item, (datetime, date)):
                    estado_limpio[key].append(item.isoformat())
                else:
                    estado_limpio[key].append(item)
        
        elif isinstance(value, dict):
            # Recursivo para dicts anidados
            estado_limpio[key] = serializar_estado(value)
        
        else:
            # Otros tipos (str, int, bool, etc.)
            estado_limpio[key] = value
    
    return estado_limpio

def deserializar_estado(estado):
    """
    Convierte strings ISO de vuelta a datetime/date al leer de Redis
    (Uso opcional, normalmente se hace manual según necesidad)
    
    Args:
        estado: Estado leído de Redis
    
    Returns:
        dict: Estado con datetime/date convertidos (opcional)
    """
    if not estado:
        return None
    
    # Por ahora retornar tal cual
    # En el futuro se puede agregar conversión automática si es necesario
    return estado

def obtener_todos_estados():
    """
    Obtiene todos los estados activos (útil para debug o admin)
    
    Returns:
        list: Lista de estados activos con user_id
    """
    if not r:
        return []
    
    try:
        keys = r.keys("user_state:*")
        estados = []
        
        for key in keys:
            data = r.get(key)
            if data:
                user_id = key.replace("user_state:", "")
                estados.append({
                    "user_id": user_id,
                    "estado": json.loads(data),
                    "ttl": r.ttl(key)
                })
        
        return estados
    except Exception as e:
        print(f"❌ Error obteniendo estados: {e}")
        return []

def contar_usuarios_activos():
    """
    Cuenta cuántos usuarios tienen estado activo
    
    Returns:
        int: Número de usuarios activos
    """
    if not r:
        return 0
    
    try:
        keys = r.keys("user_state:*")
        return len(keys)
    except Exception as e:
        print(f"❌ Error contando usuarios: {e}")
        return 0

def limpiar_estados_expirados():
    """
    Redis maneja esto automáticamente con TTL,
    pero esta función permite forzar limpieza si es necesario
    
    Returns:
        int: Número de estados eliminados
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
        
        if eliminados > 0:
            print(f"🧹 Limpiados {eliminados} estados expirados")
        
        return eliminados
    except Exception as e:
        print(f"❌ Error limpiando estados: {e}")
        return 0

def get_redis_health():
    """
    Verifica el estado de salud de Redis
    
    Returns:
        dict: Estado de Redis (para health check)
    """
    if not r:
        return {
            "status": "disconnected",
            "mensaje": "Redis no disponible"
        }
    
    try:
        r.ping()
        usuarios_activos = contar_usuarios_activos()
        
        return {
            "status": "ok",
            "mensaje": "Redis funcionando correctamente",
            "usuarios_activos": usuarios_activos,
            "redis_url": REDIS_URL.split("@")[1] if "@" in REDIS_URL else "localhost"
        }
    except Exception as e:
        return {
            "status": "error",
            "mensaje": str(e)
        }

# Exportar cliente Redis para otros módulos
redis_client = r

def get_redis_client():
    """
    Retorna el cliente Redis para uso en otros módulos
    
    Returns:
        Redis: Cliente Redis o None
    """
    return r