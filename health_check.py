import json
import os
from datetime import datetime


def ejecutar_health_check(twilio_client, peluquerias, get_calendar_service):
    """
    Ejecuta todos los chequeos críticos del sistema
    Retorna dict con estado y detalles
    """
    checks = {}
    estado_general = "ok"

    # ---------------- CLIENTES.JSON ----------------
    try:
        with open("clientes.json", "r", encoding="utf-8") as f:
            json.load(f)
        checks["clientes_json"] = "ok"
    except Exception as e:
        checks["clientes_json"] = f"error: {str(e)}"
        estado_general = "error"

    # ---------------- TWILIO ----------------
    try:
        twilio_client.api.accounts(twilio_client.username).fetch()
        checks["twilio"] = "ok"
    except Exception as e:
        checks["twilio"] = f"error: {str(e)}"
        estado_general = "error"

    # ---------------- GOOGLE CALENDAR ----------------
    try:
        if not peluquerias:
            raise Exception("No hay peluquerías configuradas")

        any_client = next(iter(peluquerias.keys()))
        service = get_calendar_service(any_client)

        if not service:
            raise Exception("Calendar service es None")

        service.calendarList().list(maxResults=1).execute()
        checks["google_calendar"] = "ok"

    except Exception as e:
        checks["google_calendar"] = f"error: {str(e)}"
        estado_general = "error"

    return {
        "status": estado_general,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    from twilio.rest import Client
    from peluqueria_bot_prueba import get_calendar_service, PELUQUERIAS

    load_dotenv()

    twilio_client = Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )

    resultado = ejecutar_health_check(
        twilio_client=twilio_client,
        peluquerias=PELUQUERIAS,
        get_calendar_service=get_calendar_service
    )

    print(json.dumps(resultado, indent=2, ensure_ascii=False))
