"""
Entry point principal de la aplicación
"""
import os
import threading
from app import create_app
from app.core.config import MODO_DESARROLLO

# Crear la aplicación Flask
app = create_app()

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 BOT DE PELUQUERÍA MULTI-CLIENTE")
    print("=" * 60)
    
    # Iniciar sistema de recordatorios solo en producción
    if not MODO_DESARROLLO:
        from app.services.notification_service import iniciar_recordatorios
        
        hilo_recordatorios = threading.Thread(
            target=iniciar_recordatorios,
            daemon=True
        )
        hilo_recordatorios.start()
        print("✅ Sistema de recordatorios activado")
    else:
        print("🧪 Recordatorios desactivados en desarrollo")
    
    # Puerto dinámico para deployment
    port = int(os.environ.get("PORT", 3000))
    print(f"🚀 Servidor iniciando en puerto {port}")
    print("=" * 60)
    
    # Ejecutar servidor
    app.run(
        host="0.0.0.0",
        port=port,
        debug=MODO_DESARROLLO
    )