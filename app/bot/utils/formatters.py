"""
Funciones de formateo para mensajes y datos
"""
from datetime import datetime


def formatear_telefono(telefono):
    """
    Formatea teléfono según código de país
    
    Args:
        telefono: +5492974210130, +12624767007, etc.
    
    Returns:
        str: Teléfono formateado legible
    """
    if not telefono:
        return "No disponible"
    
    # Limpiar el teléfono
    tel_limpio = str(telefono).replace("whatsapp:", "").strip()
    
    # Argentina con 9 (celular): +54 9 297 4210-130
    if tel_limpio.startswith("+549"):
        codigo_area = tel_limpio[4:7]  # 297
        primera = tel_limpio[7:11]      # 4210
        segunda = tel_limpio[11:]       # 130
        return f"+54 9 {codigo_area} {primera}-{segunda}"
    
    # Argentina sin 9 (fijo): +54 297 4210-130
    elif tel_limpio.startswith("+54"):
        codigo_area = tel_limpio[3:6]
        primera = tel_limpio[6:10]
        segunda = tel_limpio[10:]
        return f"+54 {codigo_area} {primera}-{segunda}"
    
    # USA: +1 (262) 476-7007
    elif tel_limpio.startswith("+1"):
        area = tel_limpio[2:5]
        primera = tel_limpio[5:8]
        segunda = tel_limpio[8:]
        return f"+1 ({area}) {primera}-{segunda}"
    
    # México: +52 55 1234-5678
    elif tel_limpio.startswith("+52"):
        if len(tel_limpio) > 12:  # Celular
            area = tel_limpio[3:6]
            resto = tel_limpio[6:]
        else:  # Fijo
            area = tel_limpio[3:5]
            resto = tel_limpio[5:]
        return f"+52 {area} {resto}"
    
    # España: +34 612 345 678
    elif tel_limpio.startswith("+34"):
        parte1 = tel_limpio[3:6]
        parte2 = tel_limpio[6:9]
        parte3 = tel_limpio[9:]
        return f"+34 {parte1} {parte2} {parte3}"
    
    # Chile: +56 9 1234 5678
    elif tel_limpio.startswith("+56"):
        if tel_limpio[3] == "9":  # Celular
            parte1 = tel_limpio[3:5]
            parte2 = tel_limpio[5:9]
            parte3 = tel_limpio[9:]
            return f"+56 {parte1} {parte2} {parte3}"
        else:  # Fijo
            return tel_limpio
    
    # Otros países: devolver limpio
    return tel_limpio


def formatear_fecha_espanol(fecha):
    """
    Formatea fecha en español
    
    Args:
        fecha (datetime): Fecha a formatear
        
    Returns:
        str: Fecha formateada (ej: "Lunes 15 de Enero")
    """
    dias = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado',
        'Sunday': 'Domingo'
    }
    
    meses = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    
    dia_semana = dias[fecha.strftime('%A')]
    dia_numero = fecha.day
    mes = meses[fecha.month]
    
    return f"{dia_semana} {dia_numero} de {mes}"


def formatear_hora(hora):
    """
    Formatea hora en formato 24h
    
    Args:
        hora (datetime): Hora a formatear
        
    Returns:
        str: Hora formateada (ej: "14:30")
    """
    return hora.strftime("%H:%M")


def formatear_item_lista(indice, texto):
    """
    Formatea un item de lista numerada
    
    Args:
        indice (int): Número del item (0-based)
        texto (str): Texto del item
        
    Returns:
        str: Item formateado con emoji
    """
    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    if indice < len(emojis):
        return f"{emojis[indice]} {texto}"
    else:
        return f"{indice + 1}. {texto}"


def formatear_duracion(minutos):
    """
    Formatea duración en texto legible
    
    Args:
        minutos (int): Duración en minutos
        
    Returns:
        str: Duración formateada (ej: "1 hora", "30 min")
    """
    if minutos >= 60:
        horas = minutos // 60
        mins_restantes = minutos % 60
        
        if mins_restantes == 0:
            return f"{horas} {'hora' if horas == 1 else 'horas'}"
        else:
            return f"{horas}h {mins_restantes}min"
    else:
        return f"{minutos} min"


def formatear_precio(precio):
    """
    Formatea precio con símbolo de moneda
    
    Args:
        precio (float): Precio a formatear
        
    Returns:
        str: Precio formateado (ej: "$1,500")
    """
    return f"${precio:,.0f}".replace(",", ".")


def limpiar_numero_telefono(telefono):
    """
    Limpia y normaliza número de teléfono
    
    Args:
        telefono (str): Número a limpiar
        
    Returns:
        str: Número limpio sin whatsapp: prefix
    """
    return telefono.replace("whatsapp:", "").strip()