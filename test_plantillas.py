# test_plantillas.py
from twilio.rest import Client
import os
from dotenv import load_dotenv
import json

load_dotenv()

client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN")
)

# Tus Content SIDs
TEMPLATES = {
    "confirmacion": "HX687ab90c71136841a0dbdb6510acdfb2",  # Reemplazar con tus SIDs reales
    "recordatorio": "HXe4e9cfacce945f16c72c42c8a85c9503",
    "nuevo_turno": "HX1ec8cd8147c8e3f5ef1eb2341b17c4db",
    "modificado": "HX16405a5a40b1e4618096147efe8a3464"
}

def test_plantilla(nombre, content_sid, variables, telefono_test):
    """Prueba una plantilla"""
    print(f"\n🧪 Probando plantilla: {nombre}")
    print(f"   SID: {content_sid}")
    print(f"   Variables: {variables}")
    
    try:
        message = client.messages.create(
            from_=f'whatsapp:{os.getenv("TWILIO_WHATSAPP_NUMBER")}',
            to=f'whatsapp:{telefono_test}',
            content_sid=content_sid,
            content_variables=json.dumps(variables)
        )
        
        print(f"✅ Enviado - SID: {message.sid}")
        print(f"   Status: {message.status}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# Tu número para pruebas
MI_NUMERO = "+5492974924147"

# Test 1: Confirmación
test_plantilla(
    "Confirmación",
    TEMPLATES["confirmacion"],
    {
        "1": "Juan Test",
        "2": "Lunes 23/12",
        "3": "15:00",
        "4": "Corte clásico",
        "5": "Peluquería Demo"
    },
    MI_NUMERO
)

# Test 2: Recordatorio
test_plantilla(
    "Recordatorio",
    TEMPLATES["recordatorio"],
    {
        "1": "Juan Test",
        "2": "Martes 24/12",
        "3": "14:00",
        "4": "Barba y bigote"
    },
    MI_NUMERO
)

# Test 3: Nuevo turno (para peluquero)
test_plantilla(
    "Nuevo turno",
    TEMPLATES["nuevo_turno"],
    {
        "1": "María López",
        "2": "Miércoles 25/12",
        "3": "16:30",
        "4": "Tintura"
    },
    MI_NUMERO
)

# Test 4: Modificado
test_plantilla(
    "Turno modificado",
    TEMPLATES["modificado"],
    {
        "1": "Pedro García",
        "2": "Jueves 26/12",
        "3": "11:00",
        "4": "Corte moderno"
    },
    MI_NUMERO
)

print("\n✅ Tests completados")