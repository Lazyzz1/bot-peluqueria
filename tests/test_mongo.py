"""
Test de conexión a MongoDB Atlas
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# Cargar variables de entorno
load_dotenv()

def test_mongodb_connection():
    """Prueba la conexión a MongoDB"""
    
    print("🔍 Probando conexión a MongoDB Atlas...")
    print("=" * 60)
    
    # Obtener credenciales
    mongodb_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB_NAME", "peluqueria_bot")
    
    if not mongodb_uri:
        print("❌ ERROR: MONGODB_URI no está configurado en .env")
        return False
    
    print(f"📝 Database name: {db_name}")
    print(f"🔗 URI: {mongodb_uri[:30]}...{mongodb_uri[-20:]}")
    print()
    
    try:
        # Intentar conectar
        print("⏳ Conectando a MongoDB...")
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        
        # Verificar conexión
        client.admin.command('ping')
        print("✅ Conexión exitosa a MongoDB Atlas!")
        print()
        
        # Obtener base de datos
        db = client[db_name]
        print(f"📊 Base de datos: {db.name}")
        
        # Listar colecciones existentes
        collections = db.list_collection_names()
        if collections:
            print(f"📁 Colecciones existentes: {', '.join(collections)}")
        else:
            print("📁 No hay colecciones aún (se crearán automáticamente)")
        print()
        
        # Crear colección de test
        print("🧪 Creando documento de test...")
        test_collection = db['test']
        
        test_doc = {
            "tipo": "test",
            "mensaje": "Conexión exitosa desde test_mongodb.py",
            "timestamp": "2026-02-01"
        }
        
        result = test_collection.insert_one(test_doc)
        print(f"✅ Documento insertado con ID: {result.inserted_id}")
        
        # Leer documento
        found_doc = test_collection.find_one({"_id": result.inserted_id})
        print(f"✅ Documento leído: {found_doc['mensaje']}")
        
        # Limpiar test
        test_collection.delete_one({"_id": result.inserted_id})
        print("🗑️  Documento de test eliminado")
        print()
        
        # Información adicional
        print("=" * 60)
        print("📊 INFORMACIÓN DE LA BASE DE DATOS:")
        print("=" * 60)
        print(f"Servidor: {client.address}")
        print(f"Base de datos: {db_name}")
        print(f"Colecciones: {len(collections) if collections else 0}")
        print()
        
        # Cerrar conexión
        client.close()
        print("✅ Conexión cerrada correctamente")
        print()
        print("🎉 ¡TODO FUNCIONA CORRECTAMENTE!")
        
        return True
        
    except ConnectionFailure as e:
        print(f"❌ ERROR DE CONEXIÓN: {e}")
        print()
        print("💡 Posibles causas:")
        print("   1. URI incorrecta")
        print("   2. Usuario/password incorrecto")
        print("   3. IP no permitida en MongoDB Atlas")
        print("   4. Cluster pausado o eliminado")
        return False
        
    except OperationFailure as e:
        print(f"❌ ERROR DE AUTENTICACIÓN: {e}")
        print()
        print("💡 Verifica:")
        print("   1. Usuario y password correctos")
        print("   2. Usuario tiene permisos en la base de datos")
        return False
        
    except Exception as e:
        print(f"❌ ERROR INESPERADO: {e}")
        return False

if __name__ == "__main__":
    success = test_mongodb_connection()
    
    if success:
        print()
        print("✅ MongoDB está listo para usar con tu bot")
        print()
        print("📝 Próximos pasos:")
        print("   1. El bot creará automáticamente las colecciones:")
        print("      • turnos - Historial de reservas")
        print("      • usuarios - Info de clientes")
        print("      • logs - Registro de actividad")
        print("   2. No necesitas hacer nada más")
        print("   3. ¡Deploy tu bot a Railway!")
    else:
        print()
        print("❌ Necesitas corregir la configuración antes de continuar")
        print()
        print("🔧 Verifica:")
        print("   1. MONGODB_URI en .env")
        print("   2. IP permitida en MongoDB Atlas")
        print("   3. Usuario/password correctos")