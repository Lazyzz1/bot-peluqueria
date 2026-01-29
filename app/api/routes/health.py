"""
Health Check Endpoint
Verifica el estado de la aplicación y sus servicios
"""

from flask import Blueprint, jsonify
import os

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Endpoint de health check
    Verifica que la aplicación esté funcionando correctamente
    
    Returns:
        JSON con estado de la aplicación y sus componentes
    """
    try:
        # Verificar componentes básicos
        checks = {
            "app": check_app(),
            "config": check_config(),
            "handlers": check_handlers(),
            "services": check_services()
        }
        
        # Determinar estado general
        all_ok = all(check["status"] == "ok" for check in checks.values())
        status = "healthy" if all_ok else "degraded"
        status_code = 200 if all_ok else 503
        
        return jsonify({
            "status": status,
            "checks": checks,
            "version": "1.0.0",
            "environment": os.getenv("FLASK_ENV", "production")
        }), status_code
    
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


def check_app():
    """Verifica que la aplicación Flask esté corriendo"""
    return {
        "status": "ok",
        "message": "Flask app running"
    }


def check_config():
    """Verifica que las variables de entorno críticas estén configuradas"""
    required_vars = [
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_WHATSAPP_NUMBER"
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        return {
            "status": "error",
            "message": f"Missing environment variables: {', '.join(missing)}"
        }
    
    return {
        "status": "ok",
        "message": "All required environment variables present"
    }


def check_handlers():
    """Verifica que los handlers estén inicializados"""
    try:
        from app.bot.orchestrator import bot_orchestrator
        
        handlers = {
            "menu": bot_orchestrator.menu_handler is not None,
            "booking": bot_orchestrator.booking_handler is not None,
            "cancellation": bot_orchestrator.cancellation_handler is not None,
            "info": bot_orchestrator.info_handler is not None
        }
        
        all_initialized = all(handlers.values())
        
        if not all_initialized:
            missing = [h for h, v in handlers.items() if not v]
            return {
                "status": "error",
                "message": f"Handlers not initialized: {', '.join(missing)}"
            }
        
        return {
            "status": "ok",
            "message": "All handlers initialized",
            "handlers": handlers
        }
    
    except ImportError:
        return {
            "status": "error",
            "message": "Bot orchestrator not available"
        }


def check_services():
    """Verifica que los servicios estén disponibles"""
    services_status = {}
    
    # WhatsApp Service
    try:
        from app.services.whatsapp_service import whatsapp_service
        services_status["whatsapp"] = "ok" if whatsapp_service else "error"
    except ImportError:
        services_status["whatsapp"] = "not_available"
    
    # Calendar Service
    try:
        from app.services.calendar_service import CalendarService
        services_status["calendar"] = "ok"
    except ImportError:
        services_status["calendar"] = "not_available"
    
    # Notification Service
    try:
        from app.services.notification_service import notification_service
        services_status["notifications"] = "ok" if notification_service else "error"
    except ImportError:
        services_status["notifications"] = "not_available"
    
    # Redis (Estado)
    try:
        from app.bot.states.state_manager import redis_client
        redis_client.ping()
        services_status["redis"] = "ok"
    except Exception:
        services_status["redis"] = "error"
    
    # MongoDB (opcional)
    try:
        from app.core.database import MONGODB_DISPONIBLE
        services_status["mongodb"] = "ok" if MONGODB_DISPONIBLE else "not_configured"
    except ImportError:
        services_status["mongodb"] = "not_available"
    
    # Verificar si hay servicios críticos con error
    critical_services = ["whatsapp", "calendar", "redis"]
    critical_errors = [s for s in critical_services if services_status.get(s) == "error"]
    
    if critical_errors:
        return {
            "status": "error",
            "message": f"Critical services with errors: {', '.join(critical_errors)}",
            "services": services_status
        }
    
    return {
        "status": "ok",
        "message": "All critical services available",
        "services": services_status
    }


@health_bp.route('/ping', methods=['GET'])
def ping():
    """Simple ping endpoint"""
    return jsonify({"status": "pong"}), 200