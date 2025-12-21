"""
Configuración para desarrollo local
"""

import os
from dotenv import load_dotenv

# Cargar .env.local en lugar de .env
load_dotenv('.env.local')

# Configuración de desarrollo
DEBUG = True
TESTING = True
LOG_LEVEL = 'DEBUG'

# Deshabilitar recordatorios en desarrollo
ENABLE_REMINDERS = False

# Puerto para desarrollo
PORT = int(os.getenv('PORT', 3000))

print("🧪 Modo de desarrollo activado")
print(f"   Puerto: {PORT}")
print(f"   Recordatorios: {'Activos' if ENABLE_REMINDERS else 'Desactivados'}")