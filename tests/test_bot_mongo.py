"""
Test de integración MongoDB + Bot
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime

load_dotenv()

def test_bot_mongodb():
    """Simula guardado de turno como lo hace el bot"""
    
    mongodb_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB_NAME", "peluqueria_bot")
    
    client = MongoClient(mongodb_uri)
    db = client[db_name]
    
    # Simular guardado de turno
    turno_test = {
        "telefono": "+5491112345678",
        "peluqueria_key": "cliente_001",
        "turno_data": {
            "peluquero": "Victoria",
            "fecha": "2026-02-10",
            "hora": "15:00",
            "servicio": "Corte clásico",
            "nombre_cliente": "Juan Pérez"
        },
        "payment_id": "test_payment_123",
        "fecha_creacion": datetime.now(),
        "tipo": "test_integracion"
    }
    
    print("💾 Guardando turno de test...")
    result = db.turnos.insert_one(turno_test)
    print(f"✅ Turno guardado con ID: {result.inserted_id}")
    
    # Leer turno
    turno_leido = db.turnos.find_one({"_id": result.inserted_id})
    print(f"✅ Turno recuperado: {turno_leido['turno_data']['nombre_cliente']}")
    
    # Limpiar
    db.turnos.delete_one({"_id": result.inserted_id})
    print("🗑️  Turno de test eliminado")
    
    client.close()
    print("\n✅ ¡Integración bot + MongoDB funciona correctamente!")

if __name__ == "__main__":
    test_bot_mongodb()