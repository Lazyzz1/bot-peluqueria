TRANSLATIONS = {
    "es": {
        # Menú principal
        "menu_bienvenida": "👋 ¡Hola! Bienvenido a *{nombre}* 💈\n\nElige una opción:",
        "opcion_pedir_turno": "Pedir turno",
        "opcion_ver_turnos": "Ver mis turnos",
        "opcion_cancelar": "Cancelar turno",
        "opcion_servicios": "Servicios y precios",
        "opcion_reagendar": "Reagendar turno",
        "opcion_faq": "Preguntas frecuentes",
        "opcion_ubicacion": "Ubicación y contacto",
        "opcion_salir": "Salir",
        "escribe_numero": "Escribí el número de la opción",
        
        # Flujo de reserva
        "seleccionar_peluquero": "💁 *¿Con qué peluquero querés tu turno?*",
        "seleccionar_dia": "📅 *¿Qué día preferís?*",
        "seleccionar_horario": "🕐 Horarios disponibles:",
        "nombre_turno": "Perfecto ✂️ ¿A nombre de quién tomo el turno?",
        "seleccionar_servicio": "📋 *¿Qué servicio(s) querés?*",
        
        # Confirmaciones
        "turno_confirmado": "✅ *Turno confirmado*\n\n👤 Cliente: {cliente}\n📅 Fecha: {fecha}\n🕐 Hora: {hora}\n✂️ Servicio(s): {servicio}\n💰 Total: {precio}\n\n¡Te esperamos! 💈",
        "turno_cancelado": "✅ Turno cancelado exitosamente\n\n📅 {fecha} a las {hora}\n\n¡Esperamos verte pronto! 💈",
        
        # Errores
        "error_generico": "❌ Ocurrió un error.\n\nEscribí *menu* para volver.",
        "opcion_invalida": "❌ Opción inválida. Elegí uno de la lista.",
        "no_hay_turnos": "🔭 No tenés turnos reservados.",
        
        # Días de la semana
        "lunes": "Lunes",
        "martes": "Martes",
        "miercoles": "Miércoles",
        "jueves": "Jueves",
        "viernes": "Viernes",
        "sabado": "Sábado",
        "domingo": "Domingo",
    },
    
    "en": {
        # Main menu
        "menu_bienvenida": "👋 Hello! Welcome to *{nombre}* 💈\n\nChoose an option:",
        "opcion_pedir_turno": "Book appointment",
        "opcion_ver_turnos": "View my appointments",
        "opcion_cancelar": "Cancel appointment",
        "opcion_servicios": "Services & pricing",
        "opcion_reagendar": "Reschedule",
        "opcion_faq": "FAQ",
        "opcion_ubicacion": "Location & contact",
        "opcion_salir": "Exit",
        "escribe_numero": "Type the option number",
        
        # Booking flow
        "seleccionar_peluquero": "💁 *Who would you like your appointment with?*",
        "seleccionar_dia": "📅 *What day works for you?*",
        "seleccionar_horario": "🕐 Available times:",
        "nombre_turno": "Perfect ✂️ What name should I book it under?",
        "seleccionar_servicio": "📋 *What service(s) would you like?*",
        
        # Confirmations
        "turno_confirmado": "✅ *Appointment confirmed*\n\n👤 Client: {cliente}\n📅 Date: {fecha}\n🕐 Time: {hora}\n✂️ Service(s): {servicio}\n💰 Total: {precio}\n\nSee you soon! 💈",
        "turno_cancelado": "✅ Appointment cancelled\n\n📅 {fecha} at {hora}\n\nHope to see you again! 💈",
        
        # Errors
        "error_generico": "❌ An error occurred.\n\nType *menu* to go back.",
        "opcion_invalida": "❌ Invalid option. Choose from the list.",
        "no_hay_turnos": "🔭 You have no appointments.",
        
        # Days of the week
        "lunes": "Monday",
        "martes": "Tuesday",
        "miercoles": "Wednesday",
        "jueves": "Thursday",
        "viernes": "Friday",
        "sabado": "Saturday",
        "domingo": "Sunday",
    },
    
    "pt": {
        # Menu principal
        "menu_bienvenida": "👋 Olá! Bem-vindo ao *{nome}* 💈\n\nEscolha uma opção:",
        "opcion_pedir_turno": "Marcar horário",
        "opcion_ver_turnos": "Ver meus horários",
        "opcion_cancelar": "Cancelar horário",
        "opcion_servicios": "Serviços e preços",
        "opcion_reagendar": "Reagendar",
        "opcion_faq": "Perguntas frequentes",
        "opcion_ubicacion": "Localização e contato",
        "opcion_salir": "Sair",
        "escribe_numero": "Digite o número da opção",
        # ... resto de traducciones
    }
}

def t(key, idioma="es", **kwargs):
    """
    Traduce una key al idioma especificado
    
    Args:
        key: Clave de traducción
        idioma: Código de idioma (es, en, pt)
        **kwargs: Variables para formatear (ej: nombre="Peluquería")
    
    Returns:
        str: Texto traducido y formateado
    """
    texto = TRANSLATIONS.get(idioma, TRANSLATIONS["es"]).get(key, key)
    
    if kwargs:
        try:
            return texto.format(**kwargs)
        except KeyError:
            return texto
    
    return texto

def detectar_idioma_por_pais(telefono):
    """
    Detecta idioma según el código de país del teléfono
    
    Args:
        telefono: +5492974210130, +12624767007, etc.
    
    Returns:
        str: Código de idioma (es, en, pt)
    """
    tel_limpio = telefono.replace("whatsapp:", "").replace("+", "").strip()
    
    # Español
    if tel_limpio.startswith("54"):   # Argentina
        return "es"
    if tel_limpio.startswith("52"):   # México
        return "es"
    if tel_limpio.startswith("34"):   # España
        return "es"
    if tel_limpio.startswith("56"):   # Chile
        return "es"
    if tel_limpio.startswith("57"):   # Colombia
        return "es"
    
    # Inglés
    if tel_limpio.startswith("1"):    # USA/Canadá
        return "en"
    if tel_limpio.startswith("44"):   # UK
        return "en"
    
    # Portugués
    if tel_limpio.startswith("55"):   # Brasil
        return "pt"
    if tel_limpio.startswith("351"):  # Portugal
        return "pt"
    
    # Default
    return "es"

FORMATOS_FECHA = {
    "es": "%d/%m/%Y",  # 13/01/2026
    "en": "%m/%d/%Y",  # 01/13/2026
    "pt": "%d/%m/%Y",  # 13/01/2026
}

def formatear_fecha_internacional(fecha, idioma="es"):
    """Formatea fecha según el idioma"""
    dias = {
        "es": ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'],
        "en": ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        "pt": ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'],
    }
    
    dia_semana = dias[idioma][fecha.weekday()]
    formato = FORMATOS_FECHA[idioma]
    fecha_str = fecha.strftime(formato)
    
    return f"{dia_semana} {fecha_str}"