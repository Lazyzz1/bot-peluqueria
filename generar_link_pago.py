"""
Generador de Links de Pago - MercadoPago
Crea links de pago para enviar manualmente por WhatsApp
"""

import mercadopago
import os
from dotenv import load_dotenv

load_dotenv()

# Inicializar SDK de MercadoPago
sdk = mercadopago.SDK(os.getenv("MERCADOPAGO_ACCESS_TOKEN"))

def crear_link_pago_setup_argentina():
    """
    Crea link de pago para Setup Argentina ($200.000 ARS)
    """
    
    preference_data = {
        "items": [
            {
                "title": "TurnosBot - Setup Inicial (Argentina)",
                "description": "Configuración completa del bot de turnos por WhatsApp",
                "quantity": 1,
                "unit_price": 200000,  # $200.000 ARS
                "currency_id": "ARS"
            }
        ],
        "back_urls": {
            "success": "https://wa.me/5492974924147?text=Pago%20realizado%20exitosamente",
            "failure": "https://wa.me/5492974924147?text=Hubo%20un%20problema%20con%20el%20pago",
            "pending": "https://wa.me/5492974924147?text=Pago%20pendiente"
        },
        "auto_return": "approved",
        "notification_url": os.getenv("APP_URL", "https://tu-app.railway.app") + "/api/webhooks/mercadopago",
        "statement_descriptor": "TurnosBot Setup",
        "external_reference": "setup_argentina",
        "payer": {
            "name": "",
            "surname": "",
            "email": "",
            "phone": {
                "area_code": "",
                "number": ""
            }
        }
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return {
            "success": True,
            "init_point": preference_response["response"]["init_point"],  # Link de pago
            "id": preference_response["response"]["id"]
        }
    else:
        return {
            "success": False,
            "error": preference_response
        }

def crear_link_pago_mensual_argentina():
    """
    Crea link de pago para Mensualidad Argentina ($65.000 ARS)
    """
    
    preference_data = {
        "items": [
            {
                "title": "TurnosBot - Mensualidad (Argentina)",
                "description": "Pago mensual del servicio de bot de turnos",
                "quantity": 1,
                "unit_price": 65000,  # $65.000 ARS
                "currency_id": "ARS"
            }
        ],
        "back_urls": {
            "success": "https://wa.me/5492974924147?text=Mensualidad%20pagada%20exitosamente",
            "failure": "https://wa.me/5492974924147?text=Hubo%20un%20problema%20con%20el%20pago",
            "pending": "https://wa.me/5492974924147?text=Pago%20pendiente"
        },
        "auto_return": "approved",
        "notification_url": os.getenv("APP_URL", "https://tu-app.railway.app") + "/api/webhooks/mercadopago",
        "statement_descriptor": "TurnosBot Mensual",
        "external_reference": "mensual_argentina"
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return {
            "success": True,
            "init_point": preference_response["response"]["init_point"],
            "id": preference_response["response"]["id"]
        }
    else:
        return {
            "success": False,
            "error": preference_response
        }

def crear_link_pago_setup_internacional():
    """
    Crea link de pago para Setup Internacional ($199 USD)
    MercadoPago lo convierte automáticamente
    """
    
    preference_data = {
        "items": [
            {
                "title": "TurnosBot - Setup (International)",
                "description": "WhatsApp bot setup - Full configuration",
                "quantity": 1,
                "unit_price": 199,  # $199 USD
                "currency_id": "USD"  # MercadoPago convierte automáticamente
            }
        ],
        "back_urls": {
            "success": "https://wa.me/5492974924147?text=Payment%20successful",
            "failure": "https://wa.me/5492974924147?text=Payment%20failed",
            "pending": "https://wa.me/5492974924147?text=Payment%20pending"
        },
        "auto_return": "approved",
        "notification_url": os.getenv("APP_URL", "https://tu-app.railway.app") + "/api/webhooks/mercadopago",
        "statement_descriptor": "TurnosBot Setup",
        "external_reference": "setup_internacional"
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return {
            "success": True,
            "init_point": preference_response["response"]["init_point"],
            "id": preference_response["response"]["id"]
        }
    else:
        return {
            "success": False,
            "error": preference_response
        }

def crear_link_pago_mensual_internacional():
    """
    Crea link de pago para Mensualidad Internacional ($65 USD)
    """
    
    preference_data = {
        "items": [
            {
                "title": "TurnosBot - Monthly (International)",
                "description": "Monthly payment for WhatsApp bot service",
                "quantity": 1,
                "unit_price": 65,  # $65 USD
                "currency_id": "USD"
            }
        ],
        "back_urls": {
            "success": "https://wa.me/5492974924147?text=Monthly%20payment%20successful",
            "failure": "https://wa.me/5492974924147?text=Payment%20failed",
            "pending": "https://wa.me/5492974924147?text=Payment%20pending"
        },
        "auto_return": "approved",
        "notification_url": os.getenv("APP_URL", "https://tu-app.railway.app") + "/api/webhooks/mercadopago",
        "statement_descriptor": "TurnosBot Monthly",
        "external_reference": "mensual_internacional"
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return {
            "success": True,
            "init_point": preference_response["response"]["init_point"],
            "id": preference_response["response"]["id"]
        }
    else:
        return {
            "success": False,
            "error": preference_response
        }

def crear_link_personalizado(titulo, descripcion, precio, moneda="ARS", referencia="custom"):
    """
    Crea link de pago personalizado
    
    Args:
        titulo (str): Título del producto
        descripcion (str): Descripción
        precio (float): Precio
        moneda (str): ARS o USD
        referencia (str): Referencia externa
    
    Returns:
        dict: {success: bool, init_point: str, id: str}
    """
    
    preference_data = {
        "items": [
            {
                "title": titulo,
                "description": descripcion,
                "quantity": 1,
                "unit_price": precio,
                "currency_id": moneda
            }
        ],
        "back_urls": {
            "success": f"https://wa.me/5492974924147?text=Pago%20exitoso:%20{titulo}",
            "failure": "https://wa.me/5492974924147?text=Problema%20con%20el%20pago",
            "pending": "https://wa.me/5492974924147?text=Pago%20pendiente"
        },
        "auto_return": "approved",
        "notification_url": os.getenv("APP_URL", "https://tu-app.railway.app") + "/api/webhooks/mercadopago",
        "statement_descriptor": titulo[:22],  # Máximo 22 caracteres
        "external_reference": referencia
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return {
            "success": True,
            "init_point": preference_response["response"]["init_point"],
            "id": preference_response["response"]["id"]
        }
    else:
        return {
            "success": False,
            "error": preference_response
        }

# ==================== SCRIPT CLI ====================

if __name__ == "__main__":
    """
    Script para generar links de pago desde la terminal
    Uso: python generar_link_pago.py
    """
    
    import sys
    
    print("\n🔗 Generador de Links de Pago - MercadoPago")
    print("=" * 60)
    print()
    print("Selecciona el tipo de pago:")
    print()
    print("1. Setup Argentina ($200.000 ARS)")
    print("2. Mensualidad Argentina ($65.000 ARS)")
    print("3. Setup Internacional ($199 USD)")
    print("4. Mensualidad Internacional ($65 USD)")
    print("5. Personalizado")
    print()
    
    opcion = input("Opción (1-5): ").strip()
    
    result = None
    
    if opcion == "1":
        print("\n⏳ Generando link para Setup Argentina...")
        result = crear_link_pago_setup_argentina()
        
    elif opcion == "2":
        print("\n⏳ Generando link para Mensualidad Argentina...")
        result = crear_link_pago_mensual_argentina()
        
    elif opcion == "3":
        print("\n⏳ Generando link para Setup Internacional...")
        result = crear_link_pago_setup_internacional()
        
    elif opcion == "4":
        print("\n⏳ Generando link para Mensualidad Internacional...")
        result = crear_link_pago_mensual_internacional()
        
    elif opcion == "5":
        print("\n📝 Pago Personalizado")
        titulo = input("Título del producto: ").strip()
        descripcion = input("Descripción: ").strip()
        precio = float(input("Precio: "))
        moneda = input("Moneda (ARS/USD): ").strip().upper()
        referencia = input("Referencia (opcional): ").strip() or "custom"
        
        print("\n⏳ Generando link personalizado...")
        result = crear_link_personalizado(titulo, descripcion, precio, moneda, referencia)
    
    else:
        print("\n❌ Opción inválida")
        sys.exit(1)
    
    # Mostrar resultado
    print()
    print("=" * 60)
    
    if result and result["success"]:
        print("✅ Link de pago generado exitosamente!")
        print()
        print("🔗 LINK DE PAGO:")
        print(result["init_point"])
        print()
        print("📋 ID de preferencia:", result["id"])
        print()
        print("💡 Envía este link por WhatsApp a tu cliente")
        print("💡 El cliente paga y recibe confirmación automática")
        print("💡 Tu bot recibirá el webhook de confirmación")
        print()
    else:
        print("❌ Error al generar el link")
        print()
        print("Error:", result.get("error", "Desconocido") if result else "Sin respuesta")
        print()
    
    print("=" * 60)