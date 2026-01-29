"""
Entry Point de la Aplicación
Ejecuta el servidor Flask
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Agregar el directorio actual al path para imports
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

# Crear la aplicación
app = create_app()

if __name__ == "__main__":
    # Determinar modo
    modo_desarrollo = os.getenv('FLASK_ENV') == 'development'
    
    # Puerto dinámico (para deployment en Render/Railway/Heroku)
    port = int(os.environ.get("PORT", 3000))
    
    print("\n" + "="*60)
    if modo_desarrollo:
        print("🧪 MODO DESARROLLO")
    else:
        print("🚀 MODO PRODUCCIÓN")
    print("="*60)
    print(f"🌐 Servidor iniciando en puerto {port}")
    print(f"📡 Host: 0.0.0.0")
    print(f"🐛 Debug: {modo_desarrollo}")
    print("="*60 + "\n")
    
    # Iniciar servidor
    app.run(
        host="0.0.0.0",
        port=port,
        debug=modo_desarrollo,
        use_reloader=modo_desarrollo  # Solo reload en desarrollo
    )