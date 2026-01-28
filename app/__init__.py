"""
Inicialización de la aplicación Flask
"""
from flask import Flask
from app.core.config import Config


def create_app():
    """
    Factory para crear la aplicación Flask
    
    Returns:
        Flask: Instancia configurada de Flask
    """
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Registrar blueprints
    from app.api.webhooks.whatsapp import whatsapp_bp
    from app.api.routes.health import health_bp
    
    app.register_blueprint(whatsapp_bp, url_prefix='/api/whatsapp')
    app.register_blueprint(health_bp, url_prefix='/api')
    
    # Registrar página estática (opcional)
    try:
        from app.api.routes.static import static_bp
        app.register_blueprint(static_bp)
    except ImportError:
        pass
    
    print("✅ Aplicación Flask inicializada")
    
    return app