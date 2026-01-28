"""
Health check endpoint
"""
from flask import Blueprint, jsonify
from app.services.whatsapp_service import whatsapp_service
from app.core.config import PELUQUERIAS

health_bp = Blueprint('health', __name__)


@health_bp.route("/health", methods=["GET"])
def health():
    """
    Endpoint de health check
    
    Verifica:
    - Conexión a Twilio
    - Configuración de peluquerías
    - Google Calendar (si aplica)
    
    Returns:
        JSON con estado del sistema
    """
    resultado = {
        "status": "ok",
        "checks": {}
    }
    
    # Check 1: Twilio
    try:
        # Verificar que el cliente esté inicializado
        if whatsapp_service.client:
            resultado["checks"]["twilio"] = "ok"
        else:
            resultado["checks"]["twilio"] = "error"
            resultado["status"] = "degraded"
    except Exception as e:
        resultado["checks"]["twilio"] = f"error: {str(e)}"
        resultado["status"] = "degraded"
    
    # Check 2: Peluquerías configuradas
    try:
        if PELUQUERIAS and len(PELUQUERIAS) > 0:
            resultado["checks"]["clientes"] = f"ok ({len(PELUQUERIAS)} clientes)"
        else:
            resultado["checks"]["clientes"] = "error: sin clientes"
            resultado["status"] = "error"
    except Exception as e:
        resultado["checks"]["clientes"] = f"error: {str(e)}"
        resultado["status"] = "error"
    
    # Check 3: Google Calendar (opcional)
    try:
        from app.services.calendar_service import calendar_service
        
        # Intentar obtener servicio de la primera peluquería
        primera_peluqueria = list(PELUQUERIAS.keys())[0]
        service = calendar_service.get_service(primera_peluqueria)
        
        if service:
            resultado["checks"]["google_calendar"] = "ok"
        else:
            resultado["checks"]["google_calendar"] = "no configurado"
    except ImportError:
        resultado["checks"]["google_calendar"] = "módulo no disponible"
    except Exception as e:
        resultado["checks"]["google_calendar"] = f"error: {str(e)}"
        resultado["status"] = "degraded"
    
    # Check 4: MongoDB (opcional)
    try:
        from app.core.database import test_connection
        
        if test_connection():
            resultado["checks"]["mongodb"] = "ok"
        else:
            resultado["checks"]["mongodb"] = "desconectado"
    except ImportError:
        resultado["checks"]["mongodb"] = "no configurado"
    except Exception as e:
        resultado["checks"]["mongodb"] = f"error: {str(e)}"
    
    # Determinar código de respuesta
    status_code = 200
    if resultado["status"] == "degraded":
        status_code = 207  # Multi-Status
    elif resultado["status"] == "error":
        status_code = 503  # Service Unavailable
    
    return jsonify(resultado), status_code