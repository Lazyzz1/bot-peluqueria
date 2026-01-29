"""
Sistema de Traducciones
Soporte para múltiples idiomas
"""

# Traducciones disponibles
TRANSLATIONS = {
    "es": {
        # Menú
        "menu_welcome": "👋 *¡Bienvenido a {nombre}!*",
        "menu_option_1": "1️⃣ Pedir turno",
        "menu_option_2": "2️⃣ Ver mis turnos",
        "menu_option_3": "3️⃣ Cancelar turno",
        "menu_option_4": "4️⃣ Ver servicios",
        "menu_option_5": "5️⃣ Reagendar turno",
        "menu_option_6": "6️⃣ Preguntas frecuentes",
        "menu_option_7": "7️⃣ Ubicación y contacto",
        "menu_option_0": "0️⃣ Salir",
        "menu_prompt": "Escribí el número de la opción que querés",
        
        # Mensajes comunes
        "invalid_option": "❓ No entendí '{texto}'",
        "operation_cancelled": "❌ Operación cancelada",
        "error_occurred": "❌ Ocurrió un error",
        "back_to_menu": "Escribí *menu* para volver",
        
        # Reservas
        "booking_confirmed": "✅ *Turno confirmado*",
        "no_availability": "😕 No hay horarios disponibles",
        "select_barber": "👤 ¿Con qué peluquero querés tu turno?",
        "select_day": "📅 Días disponibles",
        "select_time": "🕒 Horarios disponibles",
        "enter_name": "Perfecto ✂️ ¿A nombre de quién tomo el turno?",
        "select_service": "📋 *¿Qué servicio(s) querés?*",
        
        # Despedida
        "goodbye": "👋 ¡Gracias por contactarnos!",
        "come_back": "Cuando quieras volver, escribí *hola* o *menu*"
    },
    
    "en": {
        # Menu
        "menu_welcome": "👋 *Welcome to {nombre}!*",
        "menu_option_1": "1️⃣ Book appointment",
        "menu_option_2": "2️⃣ View my appointments",
        "menu_option_3": "3️⃣ Cancel appointment",
        "menu_option_4": "4️⃣ View services",
        "menu_option_5": "5️⃣ Reschedule appointment",
        "menu_option_6": "6️⃣ FAQ",
        "menu_option_7": "7️⃣ Location & contact",
        "menu_option_0": "0️⃣ Exit",
        "menu_prompt": "Type the number of the option you want",
        
        # Common messages
        "invalid_option": "❓ I didn't understand '{texto}'",
        "operation_cancelled": "❌ Operation cancelled",
        "error_occurred": "❌ An error occurred",
        "back_to_menu": "Type *menu* to go back",
        
        # Bookings
        "booking_confirmed": "✅ *Appointment confirmed*",
        "no_availability": "😕 No availability",
        "select_barber": "👤 Which barber would you like?",
        "select_day": "📅 Available days",
        "select_time": "🕒 Available times",
        "enter_name": "Perfect ✂️ What name should I book it under?",
        "select_service": "📋 *What service(s) would you like?*",
        
        # Goodbye
        "goodbye": "👋 Thanks for contacting us!",
        "come_back": "Type *hello* or *menu* anytime to come back"
    },
    
    "pt": {
        # Menu
        "menu_welcome": "👋 *Bem-vindo ao {nombre}!*",
        "menu_option_1": "1️⃣ Marcar horário",
        "menu_option_2": "2️⃣ Ver meus horários",
        "menu_option_3": "3️⃣ Cancelar horário",
        "menu_option_4": "4️⃣ Ver serviços",
        "menu_option_5": "5️⃣ Reagendar horário",
        "menu_option_6": "6️⃣ Perguntas frequentes",
        "menu_option_7": "7️⃣ Localização e contato",
        "menu_option_0": "0️⃣ Sair",
        "menu_prompt": "Digite o número da opção desejada",
        
        # Common messages
        "invalid_option": "❓ Não entendi '{texto}'",
        "operation_cancelled": "❌ Operação cancelada",
        "error_occurred": "❌ Ocorreu um erro",
        "back_to_menu": "Digite *menu* para voltar",
        
        # Bookings
        "booking_confirmed": "✅ *Horário confirmado*",
        "no_availability": "😕 Sem disponibilidade",
        "select_barber": "👤 Com qual cabeleireiro você quer?",
        "select_day": "📅 Dias disponíveis",
        "select_time": "🕒 Horários disponíveis",
        "enter_name": "Perfeito ✂️ Em nome de quem?",
        "select_service": "📋 *Qual(is) serviço(s) você quer?*",
        
        # Goodbye
        "goodbye": "👋 Obrigado por entrar em contato!",
        "come_back": "Digite *olá* ou *menu* quando quiser voltar"
    }
}


def t(key, idioma="es", **kwargs):
    """
    Obtiene una traducción
    
    Args:
        key: Clave de la traducción
        idioma: Código del idioma (es, en, pt)
        **kwargs: Variables para formatear el texto
    
    Returns:
        str: Texto traducido
    """
    # Obtener traducciones del idioma (fallback a español)
    translations = TRANSLATIONS.get(idioma, TRANSLATIONS["es"])
    
    # Obtener texto (fallback a la clave si no existe)
    texto = translations.get(key, key)
    
    # Formatear con variables si hay
    if kwargs:
        try:
            texto = texto.format(**kwargs)
        except KeyError:
            pass
    
    return texto


def get_available_languages():
    """
    Obtiene lista de idiomas disponibles
    
    Returns:
        list: Códigos de idiomas disponibles
    """
    return list(TRANSLATIONS.keys())


def detect_language(texto):
    """
    Intenta detectar el idioma del texto (muy básico)
    
    Args:
        texto: Texto a analizar
    
    Returns:
        str: Código del idioma detectado
    """
    texto_lower = texto.lower()
    
    # Palabras clave en inglés
    en_keywords = ["hello", "hi", "appointment", "booking", "schedule"]
    if any(word in texto_lower for word in en_keywords):
        return "en"
    
    # Palabras clave en portugués
    pt_keywords = ["olá", "oi", "horário", "agendar", "marcar"]
    if any(word in texto_lower for word in pt_keywords):
        return "pt"
    
    # Por defecto español
    return "es"