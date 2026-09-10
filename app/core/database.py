import os
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import pytz

# Conexión a MongoDB Atlas (gratis)
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["peluqueria_bot"]

# Colecciones
turnos_collection = db["turnos"]
clientes_collection = db["clientes"]
recordatorios_collection = db["recordatorios"]

# ==================== FUNCIONES PARA TURNOS ====================

def guardar_turno(peluqueria_key, telefono, cliente_nombre, servicio, fecha_hora, peluquero=None, precio=0, duracion=30, google_event_id=None):
    """Guarda un turno en MongoDB"""
    try:
        turno = {
            "peluqueria": peluqueria_key,
            "telefono": telefono,
            "cliente": cliente_nombre,
            "servicio": servicio,
            "fecha_hora": fecha_hora,
            "peluquero": peluquero["nombre"] if peluquero else None,
            "precio": precio,
            "duracion": duracion,
            "google_event_id": google_event_id,
            "estado": "confirmado",
            "creado_en": datetime.utcnow(),
            "actualizado_en": datetime.utcnow()
        }
        
        resultado = turnos_collection.insert_one(turno)
        print(f"✅ Turno guardado en MongoDB: {resultado.inserted_id}")
        return str(resultado.inserted_id)
    
    except Exception as e:
        print(f"❌ Error guardando turno: {e}")
        return None

def obtener_turnos_por_telefono(peluqueria_key, telefono):
    """Obtiene todos los turnos futuros de un cliente"""
    try:
        ahora = datetime.utcnow()
        
        turnos = turnos_collection.find({
            "peluqueria": peluqueria_key,
            "telefono": telefono,
            "fecha_hora": {"$gte": ahora},
            "estado": "confirmado"
        }).sort("fecha_hora", 1)
        
        return list(turnos)
    
    except Exception as e:
        print(f"❌ Error obteniendo turnos: {e}")
        return []

def cancelar_turno_db(turno_id):
    """Marca un turno como cancelado"""
    try:
        from bson.objectid import ObjectId
        
        resultado = turnos_collection.update_one(
            {"_id": ObjectId(turno_id)},
            {
                "$set": {
                    "estado": "cancelado",
                    "cancelado_en": datetime.utcnow()
                }
            }
        )
        
        return resultado.modified_count > 0
    
    except Exception as e:
        print(f"❌ Error cancelando turno: {e}")
        return False

def obtener_turnos_proximos_db(peluqueria_key, horas_anticipacion=24):
    """Obtiene turnos próximos para enviar recordatorios"""
    try:
        ahora = datetime.utcnow()
        tiempo_inicio = ahora + timedelta(hours=horas_anticipacion - 1)
        tiempo_fin = ahora + timedelta(hours=horas_anticipacion + 1)
        
        turnos = turnos_collection.find({
            "peluqueria": peluqueria_key,
            "fecha_hora": {
                "$gte": tiempo_inicio,
                "$lte": tiempo_fin
            },
            "estado": "confirmado"
        })
        
        return list(turnos)
    
    except Exception as e:
        print(f"❌ Error obteniendo turnos próximos: {e}")
        return []

# ==================== FUNCIONES PARA CLIENTES ====================

def guardar_cliente(telefono, nombre, peluqueria_key, preferencias=None):
    """Guarda o actualiza info del cliente"""
    try:
        cliente = {
            "telefono": telefono,
            "nombre": nombre,
            "peluqueria": peluqueria_key,
            "preferencias": preferencias or {},
            "primer_contacto": datetime.utcnow(),
            "ultimo_contacto": datetime.utcnow()
        }
        
        # Upsert: actualiza si existe, crea si no
        clientes_collection.update_one(
            {"telefono": telefono, "peluqueria": peluqueria_key},
            {"$set": cliente, "$setOnInsert": {"primer_contacto": datetime.utcnow()}},
            upsert=True
        )
        
        print(f"✅ Cliente guardado: {nombre}")
        return True
    
    except Exception as e:
        print(f"❌ Error guardando cliente: {e}")
        return False

def obtener_cliente(telefono, peluqueria_key):
    """Obtiene info del cliente"""
    try:
        cliente = clientes_collection.find_one({
            "telefono": telefono,
            "peluqueria": peluqueria_key
        })
        return cliente
    
    except Exception as e:
        print(f"❌ Error obteniendo cliente: {e}")
        return None

# ==================== FUNCIONES PARA RECORDATORIOS ====================

def marcar_recordatorio_enviado(turno_id, tipo="24h"):
    """Marca un recordatorio como enviado"""
    try:
        from bson.objectid import ObjectId
        
        recordatorio = {
            "turno_id": ObjectId(turno_id),
            "tipo": tipo,
            "enviado_en": datetime.utcnow()
        }
        
        recordatorios_collection.insert_one(recordatorio)
        return True
    
    except Exception as e:
        print(f"❌ Error marcando recordatorio: {e}")
        return False

def recordatorio_ya_enviado(turno_id, tipo="24h"):
    """Verifica si ya se envió un recordatorio"""
    try:
        from bson.objectid import ObjectId
        
        existe = recordatorios_collection.find_one({
            "turno_id": ObjectId(turno_id),
            "tipo": tipo
        })
        
        return existe is not None
    
    except Exception as e:
        print(f"❌ Error verificando recordatorio: {e}")
        return False

# ==================== ESTADÍSTICAS ====================

def obtener_estadisticas(peluqueria_key, dias=30):
    """Obtiene estadísticas de turnos"""
    try:
        desde = datetime.utcnow() - timedelta(days=dias)
        
        pipeline = [
            {
                "$match": {
                    "peluqueria": peluqueria_key,
                    "creado_en": {"$gte": desde}
                }
            },
            {
                "$group": {
                    "_id": "$estado",
                    "cantidad": {"$sum": 1}
                }
            }
        ]
        
        resultados = list(turnos_collection.aggregate(pipeline))
        
        stats = {
            "confirmados": 0,
            "cancelados": 0,
            "completados": 0,
            "total": 0
        }
        
        for r in resultados:
            estado = r["_id"]
            cantidad = r["cantidad"]
            stats[estado] = cantidad
            stats["total"] += cantidad
        
        return stats
    
    except Exception as e:
        print(f"❌ Error obteniendo estadísticas: {e}")
        return None

# ==================== ÍNDICES (EJECUTAR UNA VEZ) ====================

def crear_indices():
    """Crea índices para optimizar consultas"""
    try:
        # Índice para buscar turnos por teléfono
        turnos_collection.create_index([
            ("peluqueria", 1),
            ("telefono", 1),
            ("fecha_hora", -1)
        ])
        
        # Índice para recordatorios
        turnos_collection.create_index([
            ("peluqueria", 1),
            ("fecha_hora", 1),
            ("estado", 1)
        ])
        
        # Índice para clientes
        clientes_collection.create_index([
            ("telefono", 1),
            ("peluqueria", 1)
        ], unique=True)
        
        print("✅ Índices creados correctamente")
    
    except Exception as e:
        print(f"❌ Error creando índices: {e}")

# Crear índices al importar (solo se ejecuta una vez)
if os.getenv("CREATE_INDEXES") == "true":
    crear_indices()


# ==================== CONFIG DINÁMICA DE PELUQUERÍAS (para automatización) ====================
# Nueva colección: acá vive la config que el bot necesita para atender a cada
# cliente (horarios, servicios, peluqueros, numero_twilio, calendar_id...).
# Es el reemplazo dinámico de config/clientes.json — se lee al arrancar y se
# refresca periódicamente (ver app/core/config.py), así un cliente nuevo
# aprovisionado automáticamente entra en producción sin reiniciar Railway.
peluquerias_config_collection = db["peluquerias_config"]


def guardar_config_peluqueria(peluqueria_key: str, config: dict) -> bool:
    """Crea o actualiza la config completa de una peluquería (upsert)."""
    try:
        config = dict(config)
        config["actualizado_en"] = datetime.utcnow()
        peluquerias_config_collection.update_one(
            {"_key": peluqueria_key},
            {"$set": config, "$setOnInsert": {"creado_en": datetime.utcnow()}},
            upsert=True,
        )
        print(f"✅ Config de peluquería guardada: {peluqueria_key}")
        return True
    except Exception as e:
        print(f"❌ Error guardando config de {peluqueria_key}: {e}")
        return False


def obtener_todas_las_config_peluquerias() -> dict:
    """
    Devuelve todas las peluquerías activas en el formato que espera PELUQUERIAS,
    ej: {"peluqueria_el_estilo": {...}, "peluqueria_roca": {...}}
    """
    try:
        resultado = {}
        for doc in peluquerias_config_collection.find({"activo": {"$ne": False}}):
            key = doc.pop("_key", None)
            doc.pop("_id", None)
            doc.pop("creado_en", None)
            doc.pop("actualizado_en", None)
            if key:
                resultado[key] = doc
        return resultado
    except Exception as e:
        print(f"❌ Error obteniendo config de peluquerías: {e}")
        return {}


def eliminar_config_peluqueria(peluqueria_key: str) -> bool:
    """Da de baja una peluquería (soft-delete, no borra el historial)."""
    try:
        peluquerias_config_collection.update_one(
            {"_key": peluqueria_key},
            {"$set": {"activo": False, "actualizado_en": datetime.utcnow()}},
        )
        return True
    except Exception as e:
        print(f"❌ Error eliminando config de {peluqueria_key}: {e}")
        return False


# ==================== CAPA DE PAGOS: conexiones y turnos pendientes ====================
conexiones_pago_collection = db["conexiones_pago"]
turnos_pendientes_pago_collection = db["turnos_pendientes_pago"]


def guardar_conexion_pago(peluqueria_key: str, proveedor: str, datos: dict) -> bool:
    """Guarda/actualiza las credenciales de un negocio con un proveedor de pagos."""
    try:
        datos = dict(datos)
        datos["actualizado_en"] = datetime.utcnow()
        conexiones_pago_collection.update_one(
            {"peluqueria_key": peluqueria_key, "proveedor": proveedor},
            {"$set": datos, "$setOnInsert": {"creado_en": datetime.utcnow()}},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"❌ Error guardando conexión de pago ({peluqueria_key}/{proveedor}): {e}")
        return False


def obtener_conexion_pago(peluqueria_key: str, proveedor: str) -> dict | None:
    return conexiones_pago_collection.find_one({"peluqueria_key": peluqueria_key, "proveedor": proveedor})


def crear_turno_pendiente_pago(datos: dict) -> str:
    """
    Guarda todo lo necesario para crear la reserva una vez que se confirme
    el pago de la seña (fecha_hora, cliente, servicios, peluquero, etc).
    Returns: el id (string) del documento creado.
    """
    datos = dict(datos)
    datos["estado"] = "pendiente"
    datos["creado_en"] = datetime.utcnow()
    resultado = turnos_pendientes_pago_collection.insert_one(datos)
    return str(resultado.inserted_id)


def obtener_turno_pendiente_pago(turno_pendiente_id: str) -> dict | None:
    try:
        return turnos_pendientes_pago_collection.find_one({"_id": ObjectId(turno_pendiente_id)})
    except Exception:
        return None


def actualizar_estado_turno_pendiente(turno_pendiente_id: str, estado: str) -> None:
    try:
        turnos_pendientes_pago_collection.update_one(
            {"_id": ObjectId(turno_pendiente_id)},
            {"$set": {"estado": estado, "actualizado_en": datetime.utcnow()}},
        )
    except Exception as e:
        print(f"❌ Error actualizando turno pendiente {turno_pendiente_id}: {e}")
