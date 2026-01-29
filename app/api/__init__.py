"""
Aplicación Flask - Factory Pattern
Inicializa la aplicación y registra blueprints
"""

from flask import Flask
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()


def create_app():
    """
    Factory para crear la aplicación Flask
    
    Returns:
        Flask: Aplicación configurada
    """
    app = Flask(__name__)
    
    # Configuración
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['JSON_AS_ASCII'] = False  # Para caracteres UTF-8
    
    # Registrar blueprints
    register_blueprints(app)
    
    # Registrar error handlers
    register_error_handlers(app)
    
    return app


def register_blueprints(app):
    """Registra todos los blueprints de la aplicación"""
    
    # Webhook de WhatsApp
    from app.api.webhooks.whatsapp import whatsapp_bp
    app.register_blueprint(whatsapp_bp, url_prefix='/api')
    
    # Webhooks de Pagos
    from app.api.webhooks.payments import payments_bp
    app.register_blueprint(payments_bp, url_prefix='/api')
    
    # Health check
    from app.api.routes.health import health_bp
    app.register_blueprint(health_bp)
    
    # Rutas estáticas (landing page)
    try:
        from app.api.routes.static import static_bp
        app.register_blueprint(static_bp)
    except ImportError:
        print("⚠️ static_bp no disponible (opcional)")
    
    print("✅ Blueprints registrados correctamente")


def register_error_handlers(app):
    """Registra manejadores de errores globales"""
    
    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Not found"}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        print(f"❌ Error 500: {error}")
        return {"error": "Internal server error"}, 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        print(f"❌ Excepción no manejada: {error}")
        import traceback
        traceback.print_exc()
        return {"error": "An unexpected error occurred"}, 500