from flask import Flask, jsonify, request
from google.auth.transport.requests import Request
import json
from datetime import datetime, timedelta
from app.utils.time_utils import ahora_local
import pytz
import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import threading
import time
from dotenv import load_dotenv
from twilio.rest import Client
import base64
from threading import Lock
from health_check import ejecutar_health_check
from zoneinfo import available_timezones
from app.utils.time_utils import crear_datetime_local
from state_manager import get_state, set_state
from app.utils.translations import t
try:
    from app.core.database import (
        guardar_turno,
        guardar_cliente,
        cancelar_turno_db,
        obtener_turnos_por_telefono,
        obtener_turnos_proximos_db,
        marcar_recordatorio_enviado,
        recordatorio_ya_enviado
    )
    MONGODB_DISPONIBLE = True
    print("âœ… MongoDB conectado")
except ImportError as e:
    print(f"âš ï¸ MongoDB no disponible: {e}")
    MONGODB_DISPONIBLE = False
    def guardar_turno(*args, **kwargs): return None
    def guardar_cliente(*args, **kwargs): return None
    def cancelar_turno_db(*args, **kwargs): return False
    def obtener_turnos_por_telefono(*args, **kwargs): return []
    def obtener_turnos_proximos_db(*args, **kwargs): return []
    def marcar_recordatorio_enviado(*args, **kwargs): return False
    def recordatorio_ya_enviado(*args, **kwargs): return False

MODO_DESARROLLO = 'run_local' in sys.argv[0] or os.getenv('FLASK_ENV') == 'development'

if MODO_DESARROLLO:
    print("="*60)
    print("ðŸ§ª MODO DESARROLLO ACTIVADO")
    print("="*60)
    load_dotenv('.env.local')  # Usar configuraciÃ³n local
else:
    print("="*60)
    print("ðŸš€ MODO PRODUCCIÃ“N")
    print("="*60)
    load_dotenv()  # Usar configuraciÃ³n normal
#----------------------------------------------------------------
app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    resultado = ejecutar_health_check(
        twilio_client=twilio_client,
        peluquerias=PELUQUERIAS,
        get_calendar_service=get_calendar_service
    )

    status_code = 200 if resultado["status"] == "ok" else 503
    return jsonify(resultado), status_code


# ==================== CONFIGURACIÃ“N DE PLANTILLAS ====================

# Activar/desactivar uso de plantillas aprobadas
USAR_PLANTILLAS = True  # Cambiar a False para usar mensajes normales

# Content SIDs de plantillas (obtener de Twilio Content Editor)
TEMPLATE_CONFIRMACION = os.getenv("TEMPLATE_CONFIRMACION", "HXxxxxx")
TEMPLATE_RECORDATORIO = os.getenv("TEMPLATE_RECORDATORIO", "HXxxxxx")
TEMPLATE_NUEVO_TURNO = os.getenv("TEMPLATE_NUEVO_TURNO", "HXxxxxx")
TEMPLATE_MODIFICADO = os.getenv("TEMPLATE_MODIFICADO", "HXxxxxx")

# Verificar que los SIDs estÃ©n configurados
if USAR_PLANTILLAS:
    faltantes = [
        nombre for nombre, valor in {
            "TEMPLATE_CONFIRMACION": TEMPLATE_CONFIRMACION,
            "TEMPLATE_RECORDATORIO": TEMPLATE_RECORDATORIO,
            "TEMPLATE_NUEVO_TURNO": TEMPLATE_NUEVO_TURNO,
            "TEMPLATE_MODIFICADO": TEMPLATE_MODIFICADO,
        }.items() if not valor
    ]

    if faltantes:
        print("âŒ ERROR: Faltan Content SIDs de WhatsApp:")
        for f in faltantes:
            print(f"   - {f}")
        raise SystemExit(1)

# ------------------- CONFIGURACIÃ“N DE META ---------------------

load_dotenv()  # Carga variables de .env

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER]):
    raise ValueError("âŒ Faltan variables de entorno de Twilio")

# Inicializar cliente de Twilio
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
# ------------------------------------------------------------------------
SCOPES = ['https://www.googleapis.com/auth/calendar']
# Leer carpeta clientes.json
# Cargar configuraciÃ³n de clientes
try:
    with open("clientes.json", "r", encoding="utf-8") as f:
        PELUQUERIAS = json.load(f)
    
except FileNotFoundError:
    raise FileNotFoundError("âŒ No se encontrÃ³ clientes.json")
except json.JSONDecodeError:
    raise ValueError("âŒ clientes.json estÃ¡ corrupto")

# Crear carpeta tokens
os.makedirs('tokens', exist_ok=True)
# -------------------------------------------------------------
for cliente_id, config in PELUQUERIAS.items():
    tz = config.get("timezone")
    if not tz:
        raise ValueError(f"âŒ Cliente {cliente_id} no tiene timezone configurado")
    if tz not in available_timezones():
        raise ValueError(f"âŒ Timezone invÃ¡lido para {cliente_id}: {tz}")

# ==================== ARCHIVOS Y CACHE ====================

ARCHIVO_RECORDATORIOS = "recordatorios_enviados.json"
ARCHIVO_ESTADOS = "user_states.json"

# Thread-safe structures

recordatorios_enviados = set()
recordatorios_lock = Lock()
services_cache = {}

# ==================== AUTO-GUARDADO DE ESTADOS ====================


# ==================== FUNCIONES DE FORMATEO ====================
def formatear_telefono(telefono):
    """
    Formatea telÃ©fono segÃºn cÃ³digo de paÃ­s
    
    Args:
        telefono: +5492974210130, +12624767007, etc.
    
    Returns:
        str: TelÃ©fono formateado legible
    """
    if not telefono:
        return "No disponible"
    
    # Limpiar el telÃ©fono
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
    
    # MÃ©xico: +52 55 1234-5678
    elif tel_limpio.startswith("+52"):
        if len(tel_limpio) > 12:  # Celular
            area = tel_limpio[3:6]
            resto = tel_limpio[6:]
        else:  # Fijo
            area = tel_limpio[3:5]
            resto = tel_limpio[5:]
        return f"+52 {area} {resto}"
    
    # EspaÃ±a: +34 612 345 678
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
    
    # Otros paÃ­ses: devolver limpio
    return tel_limpio

def formatear_fecha_espanol(fecha):
    """Formatea fecha en espaÃ±ol"""
    dias = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'MiÃ©rcoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'SÃ¡bado',
        'Sunday': 'Domingo'
    }
    
    dia_semana = fecha.strftime('%A')
    dia_semana_es = dias.get(dia_semana, dia_semana)
    fecha_str = fecha.strftime('%d/%m/%Y')
    
    return f"{dia_semana_es} {fecha_str}"

def formatear_fecha_completa(fecha):
    """Formato mÃ¡s completo: "Lunes 16 de Diciembre, 15:00" """
    dias = ['Lunes', 'Martes', 'MiÃ©rcoles', 'Jueves', 'Viernes', 'SÃ¡bado', 'Domingo']
    meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
             'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    dia_semana = dias[fecha.weekday()]
    mes = meses[fecha.month - 1]
    
    return f"{dia_semana} {fecha.day} de {mes}, {fecha.strftime('%H:%M')}"

def formatear_item_lista(indice, texto):
    """
    Formatea items de lista con emojis (1-9) o negritas (10+)
    
    Args:
        indice: Ãndice en la lista (0-based)
        texto: Texto del item
    
    Returns:
        String formateado
    """
    numero = indice + 1
    
    # Emojis numÃ©ricos del 1 al 9
    emojis = {
        1: "1ï¸âƒ£", 2: "2ï¸âƒ£", 3: "3ï¸âƒ£", 4: "4ï¸âƒ£", 5: "5ï¸âƒ£",
        6: "6ï¸âƒ£", 7: "7ï¸âƒ£", 8: "8ï¸âƒ£", 9: "9ï¸âƒ£"
    }
    
    if numero in emojis:
        return f"{emojis[numero]} {texto}"
    else:
        return f"*{numero}.* {texto}"

def obtener_peluqueros_disponibles(peluqueria_key, dia_seleccionado, servicio=None):
    """
    Obtiene los peluqueros que trabajan en un dÃ­a especÃ­fico
    y opcionalmente que hagan un servicio especÃ­fico
    """
    config = PELUQUERIAS.get(peluqueria_key, {})
    peluqueros = config.get("peluqueros", [])
    
    if not peluqueros:
        return []
    
    dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
    dia_nombre = dias_semana[dia_seleccionado.weekday()]
    
    peluqueros_disponibles = []
    
    for peluquero in peluqueros:
        # Verificar si trabaja ese dÃ­a
        if dia_nombre not in peluquero.get("dias_trabajo", []):
            continue
        
        # Si se especificÃ³ un servicio, verificar especialidad
        if servicio:
            especialidades = peluquero.get("especialidades", [])
            if servicio not in especialidades:
                continue
        
        peluqueros_disponibles.append(peluquero)
    
    return peluqueros_disponibles




def obtener_horarios_peluquero(cliente_id, peluqueria_key, dia_seleccionado, peluquero_id):
    """
    Obtiene horarios disponibles de un peluquero especÃ­fico
    SOPORTA HORARIOS PARTIDOS (maÃ±ana y tarde)
    MANEJA FORMATO MIXTO CORRECTAMENTE
    """
    try:
        config = PELUQUERIAS.get(peluqueria_key, {})
 

        ahora = ahora_local(cliente_id, PELUQUERIAS)
 
        peluqueros = config.get("peluqueros", [])
        
        # Buscar el peluquero
        peluquero = None
        for p in peluqueros:
            if p["id"] == peluquero_id:
                peluquero = p
                break
        
        if not peluquero:
            print(f"âŒ Peluquero {peluquero_id} no encontrado")
            return []
        
        # Obtener horarios del peluquero para ese dÃ­a
        dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        dia_nombre = dias_semana[dia_seleccionado.weekday()]
        
        horarios_dia = peluquero.get("horarios", {}).get(dia_nombre)
        
        if not horarios_dia:
            print(f"âŒ {peluquero['nombre']} no trabaja los {dia_nombre}")
            return []
        
        
        ahora = ahora_local(cliente_id, PELUQUERIAS)
        
        # Normalizar formato ANTES de procesar
        # Detectar si primer elemento es string (formato viejo) o list (formato nuevo)
        if horarios_dia and isinstance(horarios_dia[0], str):
            # Formato viejo: ["09:00", "18:00"] â†’ [["09:00", "18:00"]]
            horarios_dia = [horarios_dia]
            print(f"ðŸ“… {peluquero['nombre']} - {dia_nombre}: formato viejo convertido")
        else:
            print(f"ðŸ“… {peluquero['nombre']} - {dia_nombre}: formato nuevo (partidos)")
        
        # Obtener servicio de Calendar
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)
        
        if not service:
            print("âŒ No se pudo obtener servicio de Calendar")
            return []
        
        # Procesar cada rango horario
        horarios_libres = []
        
        for idx, rango in enumerate(horarios_dia):
            # ValidaciÃ³n estricta
            if not isinstance(rango, list) or len(rango) != 2:
                print(f"âŒ Rango invÃ¡lido en posiciÃ³n {idx}: {rango}")
                continue
            
            hora_inicio_str, hora_fin_str = rango
            
            # Validar que sean strings
            if not isinstance(hora_inicio_str, str) or not isinstance(hora_fin_str, str):
                print(f"âŒ Formato de hora invÃ¡lido: {hora_inicio_str}, {hora_fin_str}")
                continue
            
            try:
                
                # Parsear horas
                hora_inicio = crear_datetime_local(
                    cliente_id, 
                    PELUQUERIAS, 
                    dia_seleccionado, 
                    hora_inicio_str
                )
                
                
                hora_fin = crear_datetime_local(
                    cliente_id, 
                    PELUQUERIAS, 
                    dia_seleccionado, 
                    hora_fin_str
                )
                
            except (ValueError, IndexError) as e:
                print(f"âŒ Error parseando {hora_inicio_str}-{hora_fin_str}: {e}")
                continue
            
            # Si es hoy, ajustar hora_inicio
            if dia_seleccionado == ahora.date():
                if ahora > hora_inicio:
                    minutos = (ahora.minute // 30 + 1) * 30
                    if minutos >= 60:
                        hora_inicio = ahora.replace(hour=ahora.hour + 1, minute=0, second=0, microsecond=0)
                    else:
                        hora_inicio = ahora.replace(minute=minutos, second=0, microsecond=0)
                
                # Si ya pasÃ³ este rango, continuar
                if ahora >= hora_fin:
                    print(f"â­ï¸ Rango {hora_inicio_str}-{hora_fin_str} ya pasÃ³")
                    continue
            
            # Obtener eventos ocupados
            try:
                eventos = service.events().list(
                    calendarId=calendar_id,
                    timeMin=hora_inicio.isoformat(),  # convierte a UTC automÃ¡ticamente
                    timeMax=hora_fin.isoformat(),
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
            except Exception as e:
                print(f"âŒ Error obteniendo eventos: {e}")
                continue
            
            # Filtrar eventos de este peluquero
            ocupados = []
            if "items" in eventos:
                for event in eventos["items"]:
                    try:
                        descripcion = event.get("description", "")
                        if f"Peluquero: {peluquero['nombre']}" in descripcion:
                            start = datetime.fromisoformat(event["start"]["dateTime"].replace("Z", "+00:00"))
                            ocupados.append(start)
                    except Exception:
                        continue
            
            # Generar slots libres
            horario = hora_inicio
            while horario < hora_fin:
                if not esta_ocupado(horario, ocupados):
                    horarios_libres.append(horario)
                horario += timedelta(minutes=30)
        
        print(f"âœ… {peluquero['nombre']} - {dia_nombre}: {len(horarios_libres)} slots disponibles")
        return horarios_libres
        
    except Exception as e:
        print(f"âŒ Error obteniendo horarios: {e}")
        import traceback
        traceback.print_exc()
        return []


# ==================== GOOGLE TOKEN ====================

def restaurar_token_google_master():
    """Restaura el token de Google desde variable de entorno"""
    token_b64 = os.getenv("GOOGLE_TOKEN_MASTER")
    if not token_b64:
        print("âš ï¸ GOOGLE_TOKEN_MASTER no configurado")
        return

    token_path = "tokens/master_token.json"
    
    # âŒ NUNCA imprimir tokens en producciÃ³n
    # print("GOOGLE_TOKEN_MASTER =", os.getenv("GOOGLE_TOKEN_MASTER"))  # ELIMINADO

    if not os.path.exists(token_path):
        try:
            with open(token_path, "wb") as f:
                f.write(base64.b64decode(token_b64))
            print("âœ… Token Google master restaurado")
        except Exception as e:
            print(f"âŒ Error restaurando token: {e}")

restaurar_token_google_master()


# ------------------- CONFIGURACIÃ“N GOOGLE CALENDAR ---------------------


def get_calendar_service(peluqueria_key):
    """Conecta con Google Calendar para una peluquerÃ­a especÃ­fica"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            print(f"âŒ PeluquerÃ­a no encontrada: {peluqueria_key}")
            return None
            
        config = PELUQUERIAS[peluqueria_key]
        token_file = config["token_file"]

        if not os.path.exists(token_file):
            print(f"âŒ ERROR: No existe {token_file}")
            return None

        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
                print(f"âœ… Token Google refrescado ({peluqueria_key})")
            except Exception as e:
                print(f"âŒ Error refrescando token ({peluqueria_key}): {e}")
                return None

        return build("calendar", "v3", credentials=creds)

    except Exception as e:
        print(f"âŒ Error conectando Google Calendar para {peluqueria_key}: {e}")
        return None

def get_calendar_config(peluqueria_key):
    """Obtiene el calendar_id de una peluquerÃ­a"""
    if peluqueria_key not in PELUQUERIAS:
        raise ValueError(f"PeluquerÃ­a no encontrada: {peluqueria_key}")
    return PELUQUERIAS[peluqueria_key]["calendar_id"]

def esta_ocupado(horario, ocupados):
    """Verifica si un horario estÃ¡ ocupado con 1 minuto de tolerancia"""
    for ocupado in ocupados:
        if abs((horario - ocupado).total_seconds()) < 60:
            return True
    return False

def obtener_horarios_disponibles(cliente_id, peluqueria_key, dia_seleccionado=None):
    """Genera turnos y revisa eventos ocupados en Google Calendar"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            print(f"âŒ PeluquerÃ­a invÃ¡lida: {peluqueria_key}")
            return []
            
        config = PELUQUERIAS.get(peluqueria_key, {})
        
        tz_name = config.get("timezone", "America/Argentina/Buenos_Aires")
        tz = pytz.timezone(tz_name)

        service = get_calendar_service(peluqueria_key)
        
        if not service:
            print("âŒ Service es None, retornando []")
            return []

        calendar_id = get_calendar_config(peluqueria_key)
        
        
        ahora = ahora_local(cliente_id, PELUQUERIAS)
        
        if dia_seleccionado is None:
            dia_seleccionado = ahora.date()

        # Si el dÃ­a es domingo, retornar vacÃ­o
        if dia_seleccionado.weekday() == 6:
            return []

        # Obtener horarios de la configuraciÃ³n
        config = PELUQUERIAS[peluqueria_key]
        dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        dia_nombre = dias_semana[dia_seleccionado.weekday()]
        
        # Si la peluquerÃ­a tiene horarios configurados, usarlos
        if "horarios" in config and dia_nombre in config["horarios"]:
            horario_config = config["horarios"][dia_nombre]
            hora_apertura = int(horario_config[0].split(':')[0])
            hora_cierre = int(horario_config[1].split(':')[0])
        else:
            # Horarios por defecto
            hora_apertura = 8
            hora_cierre = 21

        hora_inicio = tz.localize(
            datetime.combine(dia_seleccionado, datetime.min.time()).replace(hour=hora_apertura)
        )

        hora_fin = tz.localize(
            datetime.combine(dia_seleccionado, datetime.min.time()).replace(hour=hora_cierre)
        )

        # Si es hoy, ajustar hora_inicio
        if dia_seleccionado == ahora.date():
            if ahora > hora_inicio:
                minutos = (ahora.minute // 30 + 1) * 30
                if minutos >= 60:
                    hora_inicio = ahora.replace(hour=ahora.hour + 1, minute=0, second=0, microsecond=0)
                else:
                    hora_inicio = ahora.replace(minute=minutos, second=0, microsecond=0)

        # Obtener eventos
        eventos = service.events().list(
            calendarId=calendar_id,
            timeMin=hora_inicio.isoformat(),
            timeMax=hora_fin.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        ocupados = []
        if "items" in eventos:
            for event in eventos["items"]:
                try:
                    start = datetime.fromisoformat(event["start"]["dateTime"].replace("Z", "+00:00"))
                    ocupados.append(start)
                except Exception:
                    continue

        horarios_libres = []
        horario = hora_inicio
        while horario < hora_fin:
            if not esta_ocupado(horario, ocupados):
                horarios_libres.append(horario)
            horario += timedelta(minutes=30)

        return horarios_libres
            
    except Exception as e:
        print(f"âŒ Error obteniendo horarios: {e}")
        return []

def obtener_hora_cierre(peluqueria_key, dia_seleccionado, peluquero=None):
    """
    Obtiene la hora de cierre para un dÃ­a especÃ­fico
    Considera horarios del peluquero si estÃ¡ especificado
    
    Args:
        peluqueria_key: ID del cliente
        dia_seleccionado: Objeto date
        peluquero: Dict del peluquero (opcional)
    
    Returns:
        datetime con la hora de cierre en timezone Argentina
    """
    try:
        config = PELUQUERIAS.get(peluqueria_key, {})

        tz_name = config.get("timezone", "America/Argentina/Buenos_Aires")
        tz = pytz.timezone(tz_name)

        dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        dia_nombre = dias_semana[dia_seleccionado.weekday()]
        
        
        
        # Si hay peluquero, usar sus horarios
        if peluquero:
            horarios_dia = peluquero.get("horarios", {}).get(dia_nombre)
            if horarios_dia:
                hora_cierre_str = horarios_dia[1]  # [inicio, cierre]
                hora_cierre = tz.localize(
                    datetime.combine(dia_seleccionado, datetime.min.time()).replace(
                        hour=int(hora_cierre_str.split(':')[0]),
                        minute=int(hora_cierre_str.split(':')[1])
                    )
                )
                return hora_cierre
        
        # Si no hay peluquero o no tiene horarios, usar horarios generales del local
        if "horarios" in config and dia_nombre in config["horarios"]:
            horario_config = config["horarios"][dia_nombre]
            hora_cierre_str = horario_config[1]  # [apertura, cierre]
        else:
            # Horario por defecto
            hora_cierre_str = "21:00" if dia_nombre != "sabado" else "14:00"
        
        hora_cierre = tz.localize(
            datetime.combine(dia_seleccionado, datetime.min.time()).replace(
                hour=int(hora_cierre_str.split(':')[0]),
                minute=int(hora_cierre_str.split(':')[1])
            )
        )
        
        return hora_cierre
        
    except Exception as e:
        print(f"âŒ Error obteniendo hora de cierre: {e}")
        # Retornar hora por defecto en caso de error
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        return tz.localize(
            datetime.combine(dia_seleccionado, datetime.min.time()).replace(hour=21, minute=0)
        )

def obtener_turnos_cliente(peluqueria_key, telefono):
    """Obtiene todos los turnos futuros de un cliente"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            print(f"âŒ PeluquerÃ­a invÃ¡lida: {peluqueria_key}")
            return []
            
        config = PELUQUERIAS.get(peluqueria_key, {})

        tz_name = config.get("timezone", "America/Argentina/Buenos_Aires")
        tz = pytz.timezone(tz_name)

        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)

        if not service:
            print("âŒ No se pudo obtener el servicio de Calendar")
            return []

        
        ahora = ahora_local(peluqueria_key, PELUQUERIAS)
        
        try:
            eventos = service.events().list(
                calendarId=calendar_id,
                timeMin=ahora.isoformat(),
                timeMax=(ahora + timedelta(days=30)).isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
        except Exception as e:
            print(f"âŒ Error obteniendo eventos: {e}")
            return []
        
        turnos_cliente = []
        
        # Limpiar el telÃ©fono de bÃºsqueda
        telefono_busqueda = telefono.replace('whatsapp:', '').replace('+', '').replace(' ', '').replace('-', '')
        
        if "items" in eventos:
            for event in eventos["items"]:
                try:
                    descripcion = event.get("description", "")
                    summary = event.get("summary", "Sin tÃ­tulo")
                    
                    # Limpiar la descripciÃ³n
                    descripcion_limpia = descripcion.replace('+', '').replace(' ', '').replace('-', '').replace('Tel:', '').replace('\n', '').replace('\r', '')
                    
                    # BÃºsqueda flexible
                    if telefono_busqueda in descripcion_limpia:
                        inicio_str = event["start"].get("dateTime", event["start"].get("date"))
                        
                        if not inicio_str:
                            continue
                        
                        # Parsear fecha con timezone ( convierte UTC de Google a local del cliente)
                        if inicio_str.endswith('Z'):
                            inicio_utc = datetime.fromisoformat(inicio_str.replace("Z", "+00:00"))
                            inicio_arg = inicio_utc.astimezone(tz)
                        else:
                            inicio_arg = datetime.fromisoformat(inicio_str)
                            if inicio_arg.tzinfo is None:
                                inicio_arg = tz.localize(inicio_arg)
                            else:
                                inicio_arg = inicio_arg.astimezone(tz)
                        
                        turno_info = {
                            "id": event["id"],
                            "resumen": summary,
                            "inicio": inicio_arg
                        }
                        turnos_cliente.append(turno_info)
                except Exception as e:
                    print(f"âŒ Error procesando evento individual: {e}")
                    continue
        
        return turnos_cliente
        
    except Exception as e:
        print(f"âŒ Error general en obtener_turnos_cliente: {e}")
        import traceback
        traceback.print_exc()
        return []

def cancelar_turno(peluqueria_key, event_id):
    """Cancela un turno en Google Calendar"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            return False
            
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)

        if not service:
            return False

        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()
        return True
    except Exception as e:
        print(f"âŒ Error cancelando turno: {e}")
        return False

def crear_reserva_en_calendar(peluqueria_key, fecha_hora, cliente, servicio, telefono, peluquero=None):
    """Crea un evento en Google Calendar al confirmar turno"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            return False
            
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)

        if not service:
            return False

        # DescripciÃ³n con o sin peluquero
        descripcion = f"Cliente: {cliente}\nTel: {telefono}"
        if peluquero:
            descripcion += f"\nPeluquero: {peluquero['nombre']}"
        
        summary = f"Turno - {servicio} - {cliente}"
        if peluquero:
            summary = f"{peluquero['nombre']} - {servicio} - {cliente}"

        evento = {
            'summary': summary,
            'start': {
                'dateTime': fecha_hora.isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            },
            'end': {
                'dateTime': (fecha_hora + timedelta(minutes=30)).isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            },
            'description': descripcion
        }

        event_result = service.events().insert(
            calendarId=calendar_id,
            body=evento
        ).execute()
        
        # ðŸ†• GUARDAR EN MONGODB
        if MONGODB_DISPONIBLE:
            try:
                event_id = event_result.get('id')
                
                # ðŸ”§ BUSCAR PRECIO DEL SERVICIO
                config = PELUQUERIAS.get(peluqueria_key, {})
                servicios = config.get("servicios", [])
                precio = 0
                duracion = 30  # Por defecto
                
                # Buscar el servicio en la configuraciÃ³n
                for s in servicios:
                    if s["nombre"].lower() == servicio.lower():
                        precio = s.get("precio", 0)
                        duracion = s.get("duracion", 30)
                        break
                
                turno_id = guardar_turno(
                    peluqueria_key=peluqueria_key,
                    telefono=telefono,
                    cliente_nombre=cliente,
                    servicio=servicio,
                    fecha_hora=fecha_hora,
                    peluquero=peluquero,
                    precio=precio,  
                    duracion=duracion,  
                    google_event_id=event_id
                )
                
                if turno_id:
                    guardar_cliente(telefono, cliente, peluqueria_key)
                    print(f"âœ… Turno guardado en MongoDB: {turno_id}")
                else:
                    print("âš ï¸ No se pudo guardar en MongoDB")
                    
            except Exception as e:
                print(f"âš ï¸ Error MongoDB: {e}")
                import traceback
                traceback.print_exc()
        
        return True

    except Exception as e:
        print(f"âŒ Error creando reserva: {e}")
        import traceback
        traceback.print_exc()
        return False

def crear_reserva_multiple(peluqueria_key, fecha_hora, cliente, servicios, duracion_total, telefono, peluquero=None):
    """
    Crea un evento en Google Calendar con mÃºltiples servicios
    y guarda en MONGODB 
    """
    try:
        if peluqueria_key not in PELUQUERIAS:
            return False
            
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)

        if not service:
            return False

        # Crear resumen
        if len(servicios) == 1:
            nombre_servicios = servicios[0]['nombre']
        else:
            nombre_servicios = " + ".join(s['nombre'] for s in servicios)
        
        precio_total = sum(s['precio'] for s in servicios)
        
        # DescripciÃ³n detallada
        lista_servicios = "\n".join(
            f"â€¢ {s['nombre']} (${s['precio']:,}, {s['duracion']}min)".replace(',', '.')
            for s in servicios
        )
        
        descripcion = (
            f"Cliente: {cliente}\n"
            f"Tel: {telefono}\n"
            f"\nServicios:\n{lista_servicios}\n"
            f"\nTotal: ${precio_total:,}".replace(',', '.') + "\n"
            f"DuraciÃ³n total: {duracion_total} min"
        )
        
        if peluquero:
            descripcion += f"\nPeluquero: {peluquero['nombre']}"
        
        summary = f"{peluquero['nombre'] if peluquero else 'Turno'} - {nombre_servicios} - {cliente}"
        
        evento = {
            'summary': summary,
            'start': {
                'dateTime': fecha_hora.isoformat(),
                'timeZone': PELUQUERIAS[peluqueria_key]['timezone']
            },
            'end': {
                'dateTime': (fecha_hora + timedelta(minutes=duracion_total)).isoformat(),
                'timeZone': PELUQUERIAS[peluqueria_key]['timezone']
            },
            'description': descripcion,
            'colorId': '9' if len(servicios) > 1 else None
        }


        # CREAR EN GOOGLE CALENDAR

        event_result = service.events().insert(
            calendarId=calendar_id,
            body=evento
        ).execute()
        
        event_id = event_result.get('id')  # ID del evento de Google
        print(f"âœ… Reserva creada en Calendar: {nombre_servicios} ({duracion_total}min)")

        # GUARDAR EN MONGODB
  
        try:
            from app.core.database import guardar_turno, guardar_cliente
            
            # Guardar turno en MongoDB
            turno_id = guardar_turno(
                peluqueria_key=peluqueria_key,
                telefono=telefono,
                cliente_nombre=cliente,
                servicio=nombre_servicios,
                fecha_hora=fecha_hora,
                peluquero=peluquero,
                precio=precio_total,
                duracion=duracion_total,
                google_event_id=event_id  # Relacionar con Calendar
            )
            
            if turno_id:
                print(f"âœ… Turno guardado en MongoDB: {turno_id}")
            else:
                print("âš ï¸ No se pudo guardar en MongoDB (Calendar OK)")
            
            # Guardar informaciÃ³n del cliente
            guardar_cliente(
                telefono=telefono,
                nombre=cliente,
                peluqueria_key=peluqueria_key
            )
            
        except ImportError:
            print("âš ï¸ database.py no encontrado - Solo guardado en Calendar")
        except Exception as db_error:
            print(f"âš ï¸ Error guardando en MongoDB: {db_error}")
            # NO FALLAR si MongoDB falla, Calendar ya estÃ¡ OK

        return True

    except Exception as e:
        print(f"âŒ Error creando reserva: {e}")
        import traceback
        traceback.print_exc()
        return False
# ------------------- RECORDATORIOS ---------------------

def cargar_recordatorios_enviados():
    """Carga los recordatorios enviados desde el archivo JSON"""
    global recordatorios_enviados
    
    if os.path.exists(ARCHIVO_RECORDATORIOS):
        try:
            with open(ARCHIVO_RECORDATORIOS, "r", encoding="utf-8") as f:
                datos = json.load(f)
                with recordatorios_lock:
                    recordatorios_enviados = set(datos)
                return recordatorios_enviados
        except json.JSONDecodeError:
            print("âš ï¸ Archivo corrupto, creando backup...")
            os.rename(ARCHIVO_RECORDATORIOS, f"{ARCHIVO_RECORDATORIOS}.backup")
            return set()
        except Exception as e:
            print(f"âš ï¸ Error cargando recordatorios: {e}")
            return set()
    
    return set()

def guardar_recordatorios_enviados(recordatorios):
    """Guarda los recordatorios enviados en el archivo JSON"""
    try:
        with open(ARCHIVO_RECORDATORIOS, "w", encoding="utf-8") as f:
            json.dump(list(recordatorios), f, indent=2)
    except PermissionError:
        print("âŒ No hay permisos para escribir el archivo")
    except Exception as e:
        print(f"âŒ Error guardando recordatorios: {e}")

def obtener_turnos_proximos(cliente_id, peluqueria_key, horas_anticipacion=24):
    """Obtiene turnos que ocurrirÃ¡n en X horas"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            return []
            
        config = PELUQUERIAS.get(peluqueria_key, {})

        tz_name = config.get("timezone", "America/Argentina/Buenos_Aires")
        tz = pytz.timezone(tz_name)

        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)
        
        if not service:
            return []
        
        
        ahora = ahora_local(cliente_id, PELUQUERIAS)
        
        tiempo_inicio = ahora + timedelta(hours=horas_anticipacion - 1)
        tiempo_fin = ahora + timedelta(hours=horas_anticipacion + 1)
        
        eventos = service.events().list(
            calendarId=calendar_id,
            timeMin=tiempo_inicio.isoformat(),
            timeMax=tiempo_fin.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        turnos_recordar = []
        
        if "items" in eventos:
            for event in eventos["items"]:
                try:
                    inicio_str = event["start"]["dateTime"]

                    if inicio_str.endswith('Z'):
                        inicio_utc = datetime.fromisoformat(inicio_str.replace("Z", "+00:00"))
                        inicio = inicio_utc.astimezone(tz)
                    else:
                        inicio = datetime.fromisoformat(inicio_str)
                        if inicio.tzinfo is None:
                            inicio = tz.localize(inicio)
                        else:
                            inicio = inicio.astimezone(tz)
                    
                    descripcion = event.get("description", "")
                    
                    telefono = None
                    for linea in descripcion.split("\n"):
                        if "Tel:" in linea:
                            telefono = linea.replace("Tel:", "").strip()
                            break
                    
                    if telefono:
                        turno_info = {
                            "telefono": telefono,
                            "inicio": inicio,
                            "resumen": event.get("summary", "Turno"),
                            "id": event["id"],
                            "peluqueria": peluqueria_key
                        }
                        turnos_recordar.append(turno_info)
                        
                except Exception as e:
                    print(f"âŒ Error procesando evento para recordatorio: {e}")
                    continue
        
        return turnos_recordar
    
    except Exception as e:
        print(f"âŒ Error obteniendo turnos prÃ³ximos: {e}")
        return []

def enviar_recordatorio(cliente_id, turno):
    """EnvÃ­a un recordatorio de turno al cliente usando plantilla aprobada"""
    try:
        # Verificar recordatorios activos desde Redis
        telefono = turno["telefono"]
        estado_usuario = get_state(telefono)
        
        # Verificar si ya se enviÃ³ (usando MongoDB)
        if MONGODB_DISPONIBLE:
            turno_id = turno.get("_id") or turno.get("id")
            if recordatorio_ya_enviado(turno_id, "24h"):
                print(f"â­ï¸ Recordatorio ya enviado para {turno_id}")
                return


        if estado_usuario:
            if not estado_usuario.get("recordatorios_activos", True):
                print(f"â­ï¸ Usuario {telefono} tiene recordatorios desactivados")
                return
        
        # Formatear datos
        fecha = formatear_fecha_espanol(turno["inicio"])
        hora = turno["inicio"].strftime("%H:%M")
        
        # Extraer nombre del cliente y servicio del resumen
        resumen = turno.get("resumen", "Turno")
        partes = resumen.split(" - ")
        
        # Intentar extraer servicio
        if len(partes) >= 2:
            servicio = partes[-2] if len(partes) >= 3 else partes[0]
        else:
            servicio = "Tu servicio"
        
        # Intentar extraer nombre del cliente
        if len(partes) >= 3:
            nombre_cliente = partes[-1]
        else:
            nombre_cliente = "Cliente"
        
        ahora = ahora_local(cliente_id, PELUQUERIAS)
        diferencia = turno["inicio"] - ahora
        horas_faltantes = int(diferencia.total_seconds() / 3600)
        
        print(f"ðŸ“¤ Enviando recordatorio a {telefono} ({horas_faltantes}h antes)")
        
        # Usar plantilla de recordatorio
        if horas_faltantes >= 20:  # Recordatorio de 24 horas
            resultado = enviar_con_plantilla(
                telefono=telefono,
                content_sid=TEMPLATE_RECORDATORIO,
                variables={
                    "1": nombre_cliente,
                    "2": fecha,
                    "3": hora,
                    "4": servicio
                }
            )
            
            if resultado:
                print("âœ… Recordatorio 24h enviado con plantilla")
            
        elif 1 <= horas_faltantes < 3:  # Recordatorio de 2 horas
            mensaje = (
                f"â° *Recordatorio urgente*\n\n"
                f"Tu turno es en {horas_faltantes} horas:\n\n"
                f"ðŸ• Hora: {hora}\n"
                f"âœ‚ï¸ {servicio}\n\n"
                f"Â¡Nos vemos pronto! ðŸ’ˆ"
            )
            enviar_mensaje(mensaje, telefono)
            print("âœ… Recordatorio 2h enviado")

            if resultado and MONGODB_DISPONIBLE:
                marcar_recordatorio_enviado(turno_id, "24h")
                print("âœ… Recordatorio marcado en MongoDB")
                
        elif 1 <= horas_faltantes < 3:  # Recordatorio de 2 horas
            enviar_mensaje(mensaje, telefono)
            
            if MONGODB_DISPONIBLE:
                marcar_recordatorio_enviado(turno_id, "2h")
                print("âœ… Recordatorio marcado en MongoDB")            
        
    except Exception as e:
        print(f"âŒ Error enviando recordatorio: {e}")
        import traceback
        traceback.print_exc()

def sistema_recordatorios():
    """Sistema de recordatorios en segundo plano"""
    global recordatorios_enviados
    
    # Cargar recordatorios previos
    recordatorios_enviados = cargar_recordatorios_enviados()
    print(f"ðŸ“‚ Cargados {len(recordatorios_enviados)} recordatorios previos")
    print("ðŸ”” Sistema de recordatorios iniciado")
    
    while True:
        try:
            ahora = ahora_local(cliente_id, PELUQUERIAS).strftime('%H:%M')
            print(f"\nâ° [{ahora}] Verificando turnos prÃ³ximos...")
            
            # Verificar TODAS las peluquerÃ­as
            for peluqueria_key in PELUQUERIAS.keys():
                try:
                    print(f"   Verificando {PELUQUERIAS[peluqueria_key]['nombre']}...")
                    
                    # Recordatorios de 24 horas
                    turnos_24h = obtener_turnos_proximos(peluqueria_key, horas_anticipacion=24)
                    for turno in turnos_24h:
                        recordatorio_id = f"{turno['id']}_24h"
                        
                        with recordatorios_lock:
                            if recordatorio_id not in recordatorios_enviados:
                                enviar_recordatorio(turno)
                                recordatorios_enviados.add(recordatorio_id)
                                guardar_recordatorios_enviados(recordatorios_enviados)
                                print(f"   ðŸ“¤ Recordatorio 24h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")
                    
                    # Recordatorios de 2 horas
                    turnos_2h = obtener_turnos_proximos(peluqueria_key, horas_anticipacion=2)
                    for turno in turnos_2h:
                        recordatorio_id = f"{turno['id']}_2h"
                        
                        with recordatorios_lock:
                            if recordatorio_id not in recordatorios_enviados:
                                enviar_recordatorio(turno)
                                recordatorios_enviados.add(recordatorio_id)
                                guardar_recordatorios_enviados(recordatorios_enviados)
                                print(f"   ðŸ“¤ Recordatorio 2h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")
                
                except Exception as e:
                    print(f"   âŒ Error procesando {peluqueria_key}: {e}")
                    continue
            
            print("   âœ… VerificaciÃ³n completada. PrÃ³xima en 1 hora.")
            
            # Limpiar recordatorios antiguos
            with recordatorios_lock:
                if len(recordatorios_enviados) > 1000:
                    recordatorios_enviados.clear()
                    guardar_recordatorios_enviados(recordatorios_enviados)
                    print("   âœ… Limpieza completada")
            
        except Exception as e:
            print(f"   âŒ Error en sistema de recordatorios: {e}")
        
        time.sleep(3600)  # 1 hora
# ------------------- MENSAJERÃA WHATSAPP ---------------------

def enviar_mensaje(texto, numero):
    """EnvÃ­a mensaje por WhatsApp usando Twilio"""
    try:
        if not numero.startswith('whatsapp:'):
            numero = f'whatsapp:{numero}'
        
        message = twilio_client.messages.create(
            from_=f'whatsapp:{TWILIO_WHATSAPP_NUMBER}',
            body=texto,
            to=numero
        )
        
        print(f"âœ… Mensaje enviado - SID: {message.sid}")
        return True
        
    except Exception as e:
        print(f"âŒ Error enviando mensaje: {e}")
        return False

def enviar_con_plantilla(telefono, content_sid, variables):
    """
    EnvÃ­a mensaje usando plantilla aprobada de Twilio
    
    Args:
        telefono: NÃºmero destino (con o sin 'whatsapp:')
        content_sid: Content SID de la plantilla (ej: HXxxxx...)
        variables: Dict con las variables de la plantilla
        
    Returns:
        bool: True si se enviÃ³ correctamente
    """
    try:
        # Limpiar nÃºmero
        numero_limpio = telefono.replace('whatsapp:', '').strip()
        numero_formateado = f'whatsapp:{numero_limpio}'
        
        print("\nðŸ“¤ Enviando con plantilla:")
        print(f"   Para: {numero_formateado}")
        print(f"   Template SID: {content_sid}")
        print(f"   Variables: {variables}")
        
        # Convertir variables a formato JSON string
        import json
        content_variables = json.dumps(variables)
        
        message = twilio_client.messages.create(
            from_=f'whatsapp:{TWILIO_WHATSAPP_NUMBER}',
            to=numero_formateado,
            content_sid=content_sid,
            content_variables=content_variables
        )
        
        print(f"âœ… Mensaje con plantilla enviado - SID: {message.sid}")
        print(f"   Status: {message.status}")
        return True
        
    except Exception as e:
        print(f"âŒ Error enviando con plantilla: {e}")
        import traceback
        traceback.print_exc()
        return False


def notificar_peluquero(peluquero, cliente, servicio, fecha_hora, config, telefono_cliente=None):
    """
    EnvÃ­a notificaciÃ³n al peluquero cuando se reserva un turno
    Incluye telÃ©fono del cliente
    """
    try:
        telefono_peluquero = peluquero.get("telefono")
        
        if not telefono_peluquero:
            print(f"âš ï¸ Peluquero {peluquero['nombre']} no tiene telÃ©fono configurado")
            return False
        
        # Formatear fecha y hora
        fecha_formateada = formatear_fecha_espanol(fecha_hora)
        hora = fecha_hora.strftime("%H:%M")
        
        # DEBUG: Verificar quÃ© llega
        print(f"\n{'='*60}")
        print("ðŸ“ž DEBUG NOTIFICACIÃ“N:")
        print(f"   Peluquero: {peluquero['nombre']}")
        print(f"   Tel peluquero: {telefono_peluquero}")
        print(f"   Cliente: {cliente}")
        print(f"   Tel cliente recibido: {telefono_cliente}")
        print(f"   Tipo: {type(telefono_cliente)}")
        print(f"{'='*60}\n")
        
        # Formatear telÃ©fono del cliente usando la funciÃ³n
        print(f"   Tel cliente recibido: {telefono_cliente}")
        telefono_mostrar = formatear_telefono(telefono_cliente)
        print(f"   Tel formateado: {telefono_mostrar}")
        
        # Crear mensaje
        mensaje_peluquero = (
            f"ðŸ”” *Nuevo turno reservado*\n\n"
            f"ðŸ‘¤ Cliente: {cliente}\n"
            f"ðŸ“ž TelÃ©fono: {telefono_mostrar}\n"
            f"ðŸ“… Fecha: {fecha_formateada}\n"
            f"ðŸ• Hora: {hora}\n"
            f"âœ‚ï¸ Servicio: {servicio}\n\n"
            f"ðŸ“ {config['nombre']}"
        )
        
        print(f"\nðŸ“± Enviando notificaciÃ³n a {telefono_peluquero}")
        print(f"ðŸ“„ Mensaje:\n{mensaje_peluquero}\n")
        
        resultado = enviar_mensaje(mensaje_peluquero, telefono_peluquero)
        
        if resultado:
            print("âœ… NotificaciÃ³n enviada correctamente")
        else:
            print("âŒ Error enviando notificaciÃ³n")
        
        return resultado
        
    except Exception as e:
        print(f"âŒ Error en notificar_peluquero: {e}")
        import traceback
        traceback.print_exc()
        return False



def detectar_peluqueria(to_number):
    """
    Detecta quÃ© peluquerÃ­a segÃºn el nÃºmero de Twilio que recibiÃ³ el mensaje.
    Sistema multi-tenant para SaaS.
    """
    # Limpiar el nÃºmero (quitar whatsapp: y espacios)
    numero_twilio = to_number.replace("whatsapp:", "").strip()
    
    print(f"ðŸ” Detectando cliente para nÃºmero Twilio: {numero_twilio}")
    
    # Buscar quÃ© cliente tiene este nÃºmero de Twilio asignado
    for cliente_key, config in PELUQUERIAS.items():
        numero_cliente = config.get("numero_twilio", "").strip()
        
        if numero_cliente and numero_cliente == numero_twilio:
            print(f"âœ… Cliente encontrado: {cliente_key} ({config['nombre']})")
            return cliente_key
    
    # Si no se encuentra, registrar el error
    print(f"âŒ No se encontrÃ³ cliente para el nÃºmero: {numero_twilio}")
    print("ðŸ“‹ NÃºmeros Twilio registrados:")
    for key, cfg in PELUQUERIAS.items():
        print(f"   â€¢ {key}: {cfg.get('numero_twilio', 'NO CONFIGURADO')}")
    
    # Retornar None para manejar el error apropiadamente
    return None
def obtener_menu_principal(peluqueria_key, idioma="es"):
    """Genera el menÃº principal traducido"""
    config = PELUQUERIAS.get(peluqueria_key, {})
    nombre = config.get("nombre", "PeluquerÃ­a")
    
    # Detectar idioma del cliente
    idioma = config.get("idioma", "es")
    
    return (
        t("menu_bienvenida", idioma, nombre=nombre) + "\n"
        f"1ï¸âƒ£ {t('opcion_pedir_turno', idioma)}\n"
        f"2ï¸âƒ£ {t('opcion_ver_turnos', idioma)}\n"
        f"3ï¸âƒ£ {t('opcion_cancelar', idioma)}\n"
        f"4ï¸âƒ£ {t('opcion_servicios', idioma)}\n"
        f"5ï¸âƒ£ {t('opcion_reagendar', idioma)}\n"
        f"6ï¸âƒ£ {t('opcion_faq', idioma)}\n"
        f"7ï¸âƒ£ {t('opcion_ubicacion', idioma)}\n"
        f"0ï¸âƒ£ {t('opcion_salir', idioma)}\n\n"
        f"{t('escribe_numero', idioma)}"
    )


# ==================== WEBHOOK Y PROCESAMIENTO ====================

@app.route("/webhook", methods=["POST"])
def webhook():

    """
    Webhook para recibir mensajes de Twilio WhatsApp
    Sistema multi-tenant: detecta automÃ¡ticamente el cliente por el nÃºmero Twilio
    """
    try:
        # Obtener datos del mensaje
        incoming_msg = request.values.get('Body', '').strip().lower()
        numero = request.values.get('From', '')  # NÃºmero del usuario
        to_number = request.values.get('To', '')  # NÃºmero de Twilio (identifica al cliente)
        
        print("\n" + "="*60)
        print("ðŸ“¨ MENSAJE RECIBIDO")
        print("="*60)
        print(f"ðŸ‘¤ De (cliente final): {numero}")
        print(f"ðŸ“ž Para (nÃºmero Twilio): {to_number}")
        print(f"ðŸ’¬ Mensaje: {incoming_msg}")
        print("="*60)
        # Detectar a quÃ© cliente pertenece este nÃºmero de Twilio
        peluqueria_key = detectar_peluqueria(to_number)
        
        # VALIDACIÃ“N CRÃTICA: Si no se encuentra el cliente, no continuar
        if not peluqueria_key or peluqueria_key not in PELUQUERIAS:
            print("âŒ CLIENTE NO ENCONTRADO")
            print("ðŸ”§ SOLUCIÃ“N: Agrega este nÃºmero en clientes.json:")
            print(f'   "numero_twilio": "{to_number.replace("whatsapp:", "")}"')
            
            enviar_mensaje(
                "âŒ *Servicio no configurado*\n\n"
                "Este nÃºmero de WhatsApp Business no estÃ¡ registrado en el sistema.\n\n"
                "Por favor contacta al administrador del servicio.",
                numero
            )
            return "", 200
        
        print(f"âœ… CLIENTE IDENTIFICADO: {peluqueria_key}")
        print(f"ðŸª Negocio: {PELUQUERIAS[peluqueria_key]['nombre']}")
        print("="*60 + "\n")
        
        # Limpiar nÃºmero del usuario
        numero_limpio = numero.replace('whatsapp:', '')
        texto = incoming_msg
        
        estado_usuario = get_state(numero_limpio)
        
        if not estado_usuario:
            # Usuario nuevo
            print(f"ðŸ†• Nuevo usuario detectado: {numero_limpio}")
            estado_usuario = {
                "paso": "menu",
                "peluqueria": peluqueria_key
            }
            set_state(numero_limpio, estado_usuario)
        else:
            # Usuario existente
            paso_actual = estado_usuario.get("paso", "menu")
            if paso_actual == "finalizado":
                print(f"ðŸ”„ Reactivando usuario: {numero_limpio}")
                estado_usuario["paso"] = "menu"
            
            # Actualizar peluquerÃ­a por si cambiÃ³
            estado_usuario["peluqueria"] = peluqueria_key
            set_state(numero_limpio, estado_usuario)
        
        # Comandos globales para volver al menÃº (mÃ¡s flexibles)

        
        if texto in ["menu", "menÃº", "inicio", "hola", "hi", "hey", "buenas", "buenos dias", "buenas tardes", "buen dia", "hola, quiero probar el bot", "quiero probar el bot", "probar el bot"]:
            print(f"ðŸ“‹ Comando de menÃº detectado: '{texto}'")
            estado_usuario["paso"] = "menu"
            set_state(numero_limpio, estado_usuario)
            enviar_mensaje(obtener_menu_principal(peluqueria_key), numero)
            return "", 200
        
        # Obtener estado actual
        estado_usuario = get_state(numero_limpio) or {"paso": "menu"}
        estado = estado_usuario.get("paso", "menu")
        
        print(f"ðŸ“ Estado actual del usuario: {estado}")
        
        #  Si el usuario estÃ¡ en "menu" y escribe CUALQUIER COSA, mostrar menÃº
        if estado == "menu":
            # Verificar si es una opciÃ³n vÃ¡lida del menÃº (1-7, 0)
            if texto in ["1", "2", "3", "4", "5", "6", "7", "0"]:
                # Es una opciÃ³n vÃ¡lida, procesarla normalmente
                print(f"âœ… OpciÃ³n de menÃº vÃ¡lida: {texto}")
                procesar_mensaje(numero_limpio, texto, estado, peluqueria_key, numero)
            else:
                #  NO es una opciÃ³n vÃ¡lida, mostrar el menÃº
                print(f"â“ Mensaje no reconocido en menÃº: '{texto}' -> Mostrando menÃº")
                enviar_mensaje(
                    "No entendÃ­ tu mensaje. Pero te dejo el menÃº\n\n" + 
                    obtener_menu_principal(peluqueria_key),
                    numero
                )
            return "", 200
        
        # Comando para cancelar operaciÃ³n actual
        if texto in ["cancelar", "salir", "abortar", "stop", "volver"]:
            if estado != "menu":
                estado_usuario["paso"] = "menu"
                set_state(numero_limpio, estado_usuario)
                enviar_mensaje("âŒ OperaciÃ³n cancelada...", numero)
                return "", 200
        
        # Procesar segÃºn estado
        procesar_mensaje(numero_limpio, texto, estado, peluqueria_key, numero)
        
    except Exception as e:
        print("\nâŒ ERROR CRÃTICO EN WEBHOOK:")
        print(f"   {str(e)}")
        import traceback
        print("\nðŸ“‹ STACK TRACE:")
        traceback.print_exc()
        print("="*60 + "\n")
        
        # Intentar enviar mensaje de error al usuario
        try:
            enviar_mensaje(
                "âŒ OcurriÃ³ un error temporal.\n\n"
                "Por favor escribÃ­ *menu* para reintentar.",
                numero
            )
        except Exception as e:
            print(f"âš ï¸ Error ignorado en bloque X: {e}")
    
    return "", 200

def procesar_mensaje(numero_limpio, texto, estado, peluqueria_key, numero):
    """Procesa el mensaje segÃºn el estado del usuario"""
    config = PELUQUERIAS[peluqueria_key]
    
    # MENÃš PRINCIPAL
    if estado == "menu":
        if texto == "1":  # Pedir turno
            procesar_pedir_turno_inicio(numero_limpio, peluqueria_key, numero)
        elif texto == "2":  # Ver turnos
            procesar_ver_turnos(numero_limpio, peluqueria_key, numero)
        elif texto == "3":  # Cancelar turno
            procesar_cancelar_turno_inicio(numero_limpio, peluqueria_key, numero)
        elif texto == "4":  # Servicios
            procesar_servicios(config, numero)
        elif texto == "5":  # Reagendar
            procesar_reagendar_inicio(numero_limpio, peluqueria_key, numero)
        elif texto == "6":  # FAQ
            procesar_faq(numero)
        elif texto == "7":  # UbicaciÃ³n
            procesar_ubicacion(config, numero)    
        elif texto == "0":  # Salir
            procesar_salir(config, numero_limpio, numero)
        else:
            #  Mensaje mÃ¡s amigable para opciones no vÃ¡lidas
            enviar_mensaje(
                f"â“ No entendÃ­ '{texto}'\n\n" + 
                obtener_menu_principal(peluqueria_key),
                numero
            )
    
    elif estado == "seleccionar_peluquero":
        procesar_seleccion_peluquero(numero_limpio, texto, peluqueria_key, numero)    

    # FLUJO PEDIR TURNO
    elif estado == "seleccionar_dia":
        procesar_seleccion_dia(numero_limpio, texto, peluqueria_key, numero)
    elif estado == "seleccionar_horario":
        procesar_seleccion_horario(numero_limpio, texto, numero)
    elif estado == "nombre":
        procesar_nombre_cliente(numero_limpio, texto, peluqueria_key, numero)
    elif estado == "servicio":
        procesar_seleccion_servicio(numero_limpio, texto, peluqueria_key, numero)
    # elif estado == "confirmar_servicios":
     #   procesar_confirmacion_servicios(numero_limpio, texto, peluqueria_key, numero)
    
    # FLUJO CANCELAR TURNO
    elif estado == "seleccionar_turno_cancelar":
        procesar_seleccion_turno_cancelar(numero_limpio, texto, peluqueria_key, numero)
    elif estado == "confirmar_cancelacion":
        procesar_confirmacion_cancelacion(numero_limpio, texto, peluqueria_key, numero)
    
    # FLUJO REAGENDAR
    elif estado == "seleccionar_turno_reagendar":
        procesar_seleccion_turno_reagendar(numero_limpio, texto, numero)
    
    else:
        #  Si el estado es desconocido, resetear a menÃº
        print(f"âš ï¸ Estado desconocido: {estado} - Reseteando a menÃº")
        estado_usuario = get_state(numero_limpio) or {"paso": "menu"}
        estado = estado_usuario.get("paso", "menu")
        enviar_mensaje(
            "â“ Hubo un error. Volvamos al inicio.\n\n" + 
            obtener_menu_principal(peluqueria_key),
            numero
        )

# ==================== OPCIÃ“N 1: PEDIR TURNO ====================

def procesar_pedir_turno_inicio(numero_limpio, peluqueria_key, numero):
    """Inicia el flujo de pedir turno - filtra peluqueros activos"""
    config = PELUQUERIAS.get(peluqueria_key, {})
    peluqueros = config.get("peluqueros", [])
    
    # Filtrar solo peluqueros activos
    peluqueros_activos = [p for p in peluqueros if p.get("activo", True)]
    
    # Si NO hay peluqueros O ninguno activo, flujo normal
    if not peluqueros or not peluqueros_activos:
        # Flujo sin peluqueros...
        return
    
    # Si HAY peluqueros activos, preguntar primero
    estado_usuario = get_state(numero_limpio) or {}
    estado_usuario["paso"] = "seleccionar_peluquero"
    set_state(numero_limpio, estado_usuario)
    
    # Mostrar lista de peluqueros ACTIVOS con sus especialidades
    lista_peluqueros = []
    for i, peluquero in enumerate(peluqueros_activos):
        especialidades = ", ".join(peluquero.get("especialidades", []))
        dias = ", ".join([d.capitalize()[:3] for d in peluquero.get("dias_trabajo", [])])
        
        contenido = (
            f"*{peluquero['nombre']}*\n"
            f"   âœ‚ï¸ {especialidades}\n"
            f"   ðŸ“… {dias}"
        )
        lista_peluqueros.append(formatear_item_lista(i, contenido))
    # Verificar si hay peluqueros no disponibles
    peluqueros_inactivos = [p for p in peluqueros if not p.get("activo", True)]
    nota_inactivos = ""
    
    if peluqueros_inactivos:
        nombres_inactivos = ", ".join([p['nombre'] for p in peluqueros_inactivos])
        nota_inactivos = f"\n\n_âš ï¸ No disponibles: {nombres_inactivos}_"
        
        # Mostrar mensajes personalizados
        for p in peluqueros_inactivos:
            mensaje_custom = p.get("mensaje_no_disponible")
            if mensaje_custom:
                nota_inactivos += f"\n_{p['nombre']}: {mensaje_custom}_"
    
    mensaje = (
        "ðŸ‘¤ *Â¿Con quÃ© peluquero querÃ©s tu turno?*\n\n" +
        "\n\n".join(lista_peluqueros) +
        nota_inactivos +
        "\n\nElegÃ­ un nÃºmero:"
    )
    
    
    # Guardar peluqueros disponibles
    estado_usuario["peluqueros_disponibles"] = peluqueros_activos
    set_state(numero_limpio, estado_usuario)
    
    enviar_mensaje(mensaje, numero)

def procesar_seleccion_dia(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selecciÃ³n del dÃ­a"""
    try:
        index = int(texto) - 1
        # Obtener de Redis
        estado_usuario = get_state(numero_limpio) or {}
        dias_iso = estado_usuario.get("dias", [])
        dias = [datetime.fromisoformat(d).date() for d in dias_iso]
        peluquero = estado_usuario.get("peluquero")

        if 0 <= index < len(dias):
            dia_elegido = dias[index]
            
            # Si hay peluquero seleccionado, usar sus horarios
            if peluquero:
                horarios = obtener_horarios_peluquero(peluqueria_key, peluqueria_key, dia_elegido, peluquero["id"])
            else:
                # Flujo normal sin peluquero
                horarios = obtener_horarios_disponibles(peluqueria_key, peluqueria_key, dia_elegido)

            if not horarios:
                enviar_mensaje(
                    "Ese dÃ­a no tiene horarios disponibles ðŸ˜•\n\n"
                    "EscribÃ­ *menu* para volver.",
                    numero
                )
                return
            # Guardar en Redis
            estado_usuario["dia"] = dia_elegido.isoformat()  # âš ï¸ Convertir a string
            estado_usuario["horarios"] = [h.isoformat() for h in horarios]  # âš ï¸ ISO format
            estado_usuario["paso"] = "seleccionar_horario"
            set_state(numero_limpio, estado_usuario)

            lista = "\n".join(
                formatear_item_lista(i, h.strftime('%H:%M'))
                for i, h in enumerate(horarios)

            )

            mensaje_extra = ""
            if peluquero:
                mensaje_extra = f"\nðŸ‘¤ Con: *{peluquero['nombre']}*\n"

            enviar_mensaje(
                f"ðŸ•’ Horarios disponibles:{mensaje_extra}\n{lista}\n\nElegÃ­ un nÃºmero, o escribÃ­ *menu* para volver al MenÃº",
                numero
            )
        else:
            enviar_mensaje("âŒ NÃºmero fuera de rango. ElegÃ­ uno de la lista.", numero)

    except ValueError:
        enviar_mensaje("âŒ Debe ser un nÃºmero.", numero)


def procesar_seleccion_horario(numero_limpio, texto, numero):
    """Procesa la selecciÃ³n del horario"""
    try:
        index = int(texto) - 1
        
        # Obtener de Redis
        estado_usuario = get_state(numero_limpio) or {}
        # Convertir de ISO string a datetime
        horarios_iso = estado_usuario.get("horarios", [])
        horarios = [datetime.fromisoformat(h) for h in horarios_iso]
        
        if 0 <= index < len(horarios):
            fecha_hora = horarios[index]
            
            # Guardar en Redis (como ISO string)
            estado_usuario["fecha_hora"] = fecha_hora.isoformat()
            estado_usuario["paso"] = "nombre"
            set_state(numero_limpio, estado_usuario)
        
        enviar_mensaje("Perfecto âœ‚ï¸ Â¿A nombre de quiÃ©n tomo el turno?", numero)
        
    except (ValueError, IndexError):
        enviar_mensaje("âŒ NÃºmero invÃ¡lido. ElegÃ­ uno de la lista.", numero)


def procesar_nombre_cliente(numero_limpio, texto, peluqueria_key, numero):
    """Procesa el nombre del cliente y muestra servicios"""
    estado_usuario = get_state(numero_limpio) or {}
    estado_usuario["cliente"] = texto.title()
    estado_usuario["paso"] = "servicio"
    
    peluquero = estado_usuario.get("peluquero")

    config = PELUQUERIAS[peluqueria_key]
    servicios = config.get("servicios", [])
    
    # Filtrar servicios segÃºn especialidades del peluquero
    if peluquero:
        especialidades = peluquero.get("especialidades", [])
        servicios_filtrados = [s for s in servicios if s["nombre"] in especialidades]
        servicios_a_mostrar = servicios_filtrados if servicios_filtrados else servicios
    else:
        servicios_a_mostrar = servicios
    
    if servicios_a_mostrar:
        lista = []
        for i, servicio in enumerate(servicios_a_mostrar):
            precio_formateado = f"${servicio['precio']:,}".replace(',', '.')
            lista.append(formatear_item_lista(i, f"{servicio['nombre']} - {precio_formateado}"))
        
        # Guardar servicios disponibles
        estado_usuario["servicios_disponibles"] = servicios_a_mostrar
        set_state(numero_limpio, estado_usuario)
        
        mensaje_peluquero = ""
        if peluquero:
            mensaje_peluquero = f"Con *{peluquero['nombre']}*\n\n"
        
        # Instrucciones para selecciÃ³n mÃºltiple
        mensaje = (
            "ðŸ“‹ *Â¿QuÃ© servicio(s) querÃ©s?*\n\n"
            f"{mensaje_peluquero}" +
            "\n".join(lista) +
            "\n\nðŸ’¡ *PodÃ©s elegir varios servicios*\n"
            "Ejemplos:\n"
            "â€¢ Un servicio: 1\n"
            "â€¢ Varios: 1,2 o 1,3\n"
            
        )
        enviar_mensaje(mensaje, numero)
    else:
        enviar_mensaje("ðŸ“‹ Â¿QuÃ© servicio querÃ©s?\nEj: Corte, Tintura, Barba", numero)

def procesar_seleccion_servicio(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selecciÃ³n del servicio (uno o mÃºltiples) y crea la reserva"""
    config = PELUQUERIAS[peluqueria_key]
    
    #  Obtener estado de Redis
    estado_usuario = get_state(numero_limpio) or {}
    
    servicios_disponibles = estado_usuario.get("servicios_disponibles", config.get("servicios", []))
    
    # Convertir fecha_hora de ISO string a datetime
    fecha_hora_iso = estado_usuario.get("fecha_hora")
    if not fecha_hora_iso:
        enviar_mensaje("âŒ Error: No se encontrÃ³ la fecha seleccionada. EscribÃ­ *menu*", numero)
        return
    
    
    fecha_hora = datetime.datetime.fromisoformat(fecha_hora_iso)
    
    cliente = estado_usuario.get("cliente")
    peluquero = estado_usuario.get("peluquero")
    
    # ... cÃ³digo de parseo de servicios ...
    
    servicios_seleccionados = []
    duracion_total = 0
    
    try:
        if ',' in texto:
            indices = [int(num.strip()) - 1 for num in texto.split(',')]
            for index in indices:
                if 0 <= index < len(servicios_disponibles):
                    servicio = servicios_disponibles[index]
                    servicios_seleccionados.append(servicio)
                    duracion_total += servicio.get("duracion", 30)
        else:
            index = int(texto) - 1
            if 0 <= index < len(servicios_disponibles):
                servicio = servicios_disponibles[index]
                servicios_seleccionados.append(servicio)
                duracion_total = servicio.get("duracion", 30)
    except ValueError:
        for serv in servicios_disponibles:
            if serv["nombre"].lower() == texto.lower():
                servicios_seleccionados.append(serv)
                duracion_total = serv.get("duracion", 30)
                break
    
    if not servicios_seleccionados:
        enviar_mensaje("âŒ Servicio no vÃ¡lido.\n\nEscribÃ­ *menu* para volver.", numero)
        return
    
    # Crear nombres legibles
    if len(servicios_seleccionados) == 1:
        nombre_servicios = servicios_seleccionados[0]["nombre"]
    else:
        nombre_servicios = " + ".join(s["nombre"] for s in servicios_seleccionados)
    
    precio_total = sum(s["precio"] for s in servicios_seleccionados)
    
        # âš ï¸ Convertir dia de ISO string a date
    dia_iso = estado_usuario.get("dia")
    if dia_iso:

        dia_seleccionado = datetime.fromisoformat(dia_iso).date()
    else:
        dia_seleccionado = fecha_hora.date()

    # Validar disponibilidad de tiempo
    hora_cierre = obtener_hora_cierre(peluqueria_key, dia_seleccionado, peluquero)
    hora_fin_turno = fecha_hora + timedelta(minutes=duracion_total)
    
    if hora_fin_turno > hora_cierre:
        minutos_faltantes = int((hora_fin_turno - hora_cierre).total_seconds() / 60)
        enviar_mensaje(
             "â° *No hay suficiente tiempo*\n\n"
            f"Los servicios duran *{duracion_total} minutos*\n\n"
            f"ðŸ“… Inicio: {fecha_hora.strftime('%H:%M')}\n"
            f"â±ï¸ Fin: {hora_fin_turno.strftime('%H:%M')}\n"
            f"ðŸ”’ Cierre: {hora_cierre.strftime('%H:%M')}\n\n"
            f"âŒ Faltan {minutos_faltantes} minutos.\n\n"
             "EscribÃ­ *menu* para elegir otro horario.",
            numero
        )
        return
    
    # Usar numero_limpio (sin whatsapp:)
    telefono_cliente = numero_limpio  # +5492974210130
    
    # DEBUG: Verificar el telÃ©fono
    print(f"\n{'='*60}")
    print( "ðŸ“ž DEBUG TELÃ‰FONO CLIENTE:")
    print(f"   numero (con whatsapp:): {numero}")
    print(f"   numero_limpio: {numero_limpio}")
    print(f"   telefono_cliente: {telefono_cliente}")
    print(f"{'='*60}\n")
    
    # Crear reserva
    print(f"ðŸ“… Creando reserva para {cliente} - {nombre_servicios}")
    
    if crear_reserva_multiple(
        peluqueria_key, 
        fecha_hora, 
        cliente, 
        servicios_seleccionados,
        duracion_total,
        telefono_cliente,  # âœ… Pasar sin whatsapp:
        peluquero
    ):
        fecha_formateada = formatear_fecha_espanol(fecha_hora)
        hora = fecha_hora.strftime("%H:%M")
        
        print("âœ… Reserva creada, enviando confirmaciÃ³n...")
        
        # Enviar confirmaciÃ³n
        resultado = enviar_con_plantilla(
            telefono=numero,  # AcÃ¡ sÃ­ va con whatsapp para Twilio
            content_sid=TEMPLATE_CONFIRMACION,
            variables={
                "1": cliente,
                "2": fecha_formateada,
                "3": hora,
                "4": nombre_servicios,
                "5": config['nombre']
            }
        )
        
        if not resultado or MODO_DESARROLLO:
            enviar_mensaje(
                 "âœ… *Turno confirmado*\n\n"
                f"ðŸ‘¤ Cliente: {cliente}\n"
                f"ðŸ“… Fecha: {fecha_formateada}\n"
                f"ðŸ• Hora: {hora}\n"
                f"âœ‚ï¸ Servicio(s): {nombre_servicios}\n"
                f"ðŸ’° Total: ${precio_total:,}\n\n"
                 "Â¡Te esperamos! ðŸ’ˆ".replace(',', '.'),
                numero
            )
        
        # âœ… Notificar al peluquero CON telÃ©fono
        if peluquero:
            print(f"ðŸ“± Notificando a peluquero: {peluquero['nombre']}")
            print(f"   TelÃ©fono cliente a enviar: {telefono_cliente}")
            
            notificar_peluquero(
                peluquero, 
                cliente, 
                nombre_servicios, 
                fecha_hora, 
                config, 
                telefono_cliente  # âœ… SIN whatsapp:
            )
    else:
        enviar_mensaje("âŒ Error al crear la reserva.\n\nEscribÃ­ *menu*", numero)

    estado_usuario["paso"] = "menu"
    set_state(numero_limpio, estado_usuario)

# ==================== OPCIÃ“N 2: VER TURNOS ====================

def procesar_ver_turnos(numero_limpio, peluqueria_key, numero):
    """Muestra los turnos del cliente"""
    turnos = obtener_turnos_cliente(peluqueria_key, peluqueria_key, numero_limpio)
    
    if not turnos:
        enviar_mensaje(
            "ðŸ”­ No tenÃ©s turnos reservados.\n\n"
            "EscribÃ­ *menu* para volver.",
            numero
        )
    else:
        lista = []
        for i, turno in enumerate(turnos):
            fecha_formateada = formatear_fecha_espanol(turno["inicio"])
            hora = turno["inicio"].strftime("%H:%M")
            lista.append(f"{i+1}. {fecha_formateada} a las {hora}\n   {turno['resumen']}")
        
        mensaje = "ðŸ“… *Tus turnos:*\n\n" + "\n\n".join(lista) + "\n\nEscribÃ­ *menu* para volver"
        enviar_mensaje(mensaje, numero)


# ==================== OPCIÃ“N 3: CANCELAR TURNO ====================

def procesar_cancelar_turno_inicio(numero_limpio, peluqueria_key, numero):
    """Inicia el flujo de cancelar turno"""
    try:
        turnos = obtener_turnos_cliente(peluqueria_key, peluqueria_key, numero_limpio)
        
        if not turnos:
            enviar_mensaje(
                "ðŸ”­ No tenÃ©s turnos para cancelar.\n\n"
                "EscribÃ­ *menu* para volver.",
                numero
            )
            return
        # Guardar turnos en Redis
        estado_usuario = get_state(numero_limpio) or {}
        
         # Convertir turnos a formato serializable
        turnos_serializables = []
        for turno in turnos:
            turnos_serializables.append({
                "id": turno["id"],
                "resumen": turno["resumen"],
                "inicio": turno["inicio"].isoformat()  # datetime â†’ ISO string
            })
        
        estado_usuario["turnos"] = turnos_serializables
        estado_usuario["paso"] = "seleccionar_turno_cancelar"
        set_state(numero_limpio, estado_usuario)
        
        lista = []
        for i, turno in enumerate(turnos):
            fecha = turno["inicio"].strftime("%d/%m/%Y")
            hora = turno["inicio"].strftime("%H:%M")
            lista.append(formatear_item_lista(i, f"{fecha} a las {hora}\n   {turno['resumen']}"))
        
        mensaje = (
            "âŒ *Selecciona el turno a cancelar:*\n\n" + 
            "\n\n".join(lista) + 
            "\n\n0ï¸âƒ£ Volver al menÃº"
        )
        enviar_mensaje(mensaje, numero)
        
    except Exception as e:
        print(f"âŒ Error en procesar_cancelar_turno_inicio: {e}")
        import traceback
        traceback.print_exc()
        enviar_mensaje(
            "âŒ Hubo un error al buscar tus turnos.\n\n"
            "Por favor intentÃ¡ de nuevo escribiendo *menu*",
            numero
        )

def procesar_seleccion_turno_cancelar(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selecciÃ³n del turno a cancelar"""
    try:
        config = PELUQUERIAS.get(peluqueria_key, {})
        print(f"ðŸ” [{config.get('nombre', peluqueria_key)}] Usuario {numero_limpio} cancelando turno")
        
        if texto == "0":
            print("   â†³ CancelaciÃ³n abortada")
            
            # Actualizar estado en Redis
            estado_usuario = get_state(numero_limpio) or {}
            estado_usuario["paso"] = "menu"
            set_state(numero_limpio, estado_usuario)
            
            enviar_mensaje("âœ… CancelaciÃ³n abortada. EscribÃ­ *menu* para volver.", numero)
            return
        
        try:
            index = int(texto) - 1
            print(f"   â†³ SeleccionÃ³ turno #{index + 1}")
        except ValueError:
            print(f"   â†³ Entrada invÃ¡lida: '{texto}'")
            enviar_mensaje("âŒ Debe ser un nÃºmero. ElegÃ­ uno de la lista o 0 para volver.", numero)
            return
        
        # Obtener turnos de Redis
        estado_usuario = get_state(numero_limpio) or {}
        turnos_serializados = estado_usuario.get("turnos", [])
        
        if index < 0 or index >= len(turnos_serializados):
            print(f"   â†³ Ãndice fuera de rango: {index}")
            enviar_mensaje("âŒ NÃºmero invÃ¡lido. ElegÃ­ uno de la lista.", numero)
            return
        
        turno_seleccionado = turnos_serializados[index]
        
        # Guardar turno a cancelar en Redis
        estado_usuario["turno_a_cancelar"] = turno_seleccionado
        estado_usuario["paso"] = "confirmar_cancelacion"
        set_state(numero_limpio, estado_usuario)
        
        try:
            # âš ï¸ Convertir fecha de ISO string a datetime para formatear
            inicio = datetime.fromisoformat(turno_seleccionado["inicio"])
            
            fecha = inicio.strftime("%d/%m/%Y")
            hora = inicio.strftime("%H:%M")
            resumen = turno_seleccionado.get("resumen", "Turno")
            
            print(f"   â†³ Pidiendo confirmaciÃ³n para: {fecha} {hora}")
        except Exception as e:
            print(f"âŒ Error formateando fecha del turno: {e}")
            enviar_mensaje(
                "âŒ Error al procesar el turno.\n\n"
                "EscribÃ­ *menu* para volver.",
                numero
            )
            return
        
        enviar_mensaje(
             "âš ï¸ Â¿EstÃ¡s seguro de cancelar el turno?\n\n"
            f"ðŸ“… {fecha} a las {hora}\n"
            f"âœ‚ï¸ {resumen}\n\n"
             "EscribÃ­ *SI* para confirmar o *NO* para cancelar",
            numero
        )
        
    except Exception as e:
        print(f"âŒ ERROR en procesar_seleccion_turno_cancelar [{peluqueria_key}]: {e}")
        import traceback
        traceback.print_exc()
        
        enviar_mensaje(
            "âŒ OcurriÃ³ un error al procesar tu solicitud.\n\n"
            "Por favor escribÃ­ *menu* para reintentar.",
            numero
        )
        
        # Resetear estado en Redis
        estado_usuario = get_state(numero_limpio) or {}
        estado_usuario["paso"] = "menu"
        set_state(numero_limpio, estado_usuario)

def procesar_confirmacion_cancelacion(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la confirmaciÃ³n de cancelaciÃ³n"""
    try:
        if texto in ["si", "sÃ­", "s"]:
            # Obtener turno de Redis
            estado_usuario = get_state(numero_limpio) or {}
            turno = estado_usuario.get("turno_a_cancelar")
            
            if not turno:
                enviar_mensaje(
                    "âŒ No se encontrÃ³ el turno a cancelar.\n\n"
                    "EscribÃ­ *menu* para volver.",
                    numero
                )
                estado_usuario["paso"] = "menu"
                set_state(numero_limpio, estado_usuario)
                return
            
            print(f"ðŸ—‘ï¸ Cancelando turno ID: {turno['id']}")
            
            # Cancelar en Google Calendar
            if cancelar_turno(peluqueria_key, turno["id"]):
                print("âœ… Turno cancelado exitosamente en Calendar")
                # AGREGAR: TambiÃ©n cancelar en MongoDB
                if MONGODB_DISPONIBLE:
                    try:
                        # Buscar turno por google_event_id
                        from app.core.database import turnos_collection
                        from bson.objectid import ObjectId
                        
                        # Actualizar estado en MongoDB
                        turnos_collection.update_one(
                            {"google_event_id": turno["id"]},
                            {"$set": {
                                "estado": "cancelado",
                                "cancelado_en": datetime.utcnow()
                            }}
                        )
                        print("âœ… Turno cancelado en MongoDB")
                    except Exception as e:
                        print(f"âš ï¸ Error MongoDB: {e}")
                 

                try:
                    # Convertir ISO string a datetime para formatear
                    inicio = datetime.fromisoformat(turno["inicio"])
                    
                    fecha = inicio.strftime("%d/%m/%Y")
                    hora = inicio.strftime("%H:%M")
                    resumen = turno.get("resumen", "")
                    
                    # Extraer info del resumen
                    partes = resumen.split(" - ")
                    nombre_cliente = partes[-1] if len(partes) >= 3 else "Cliente"
                    servicio = partes[-2] if len(partes) >= 3 else partes[0] if partes else "Servicio"
                    
                    # Confirmar al cliente
                    enviar_mensaje(
                         "âœ… Turno cancelado exitosamente\n\n"
                        f"ðŸ“… {fecha} a las {hora}\n\n"
                         "Â¡Esperamos verte pronto! ðŸ’ˆ",
                        numero
                    )
                    
                    # Notificar al peluquero
                    config = PELUQUERIAS.get(peluqueria_key, {})
                    
                    # Buscar peluquero en el resumen
                    telefono_peluquero = None
                    nombre_peluquero = None
                    
                    for peluquero in config.get("peluqueros", []):
                        if peluquero["nombre"] in resumen:
                            nombre_peluquero = peluquero["nombre"]
                            telefono_peluquero = peluquero.get("telefono")
                            break
                    
                    if telefono_peluquero:
                        print(f"ðŸ“± Notificando cancelaciÃ³n a {nombre_peluquero}")
                        
                        mensaje_cancelacion = (
                             "âŒ *Turno cancelado*\n\n"
                            f"ðŸ‘¤ Cliente: {nombre_cliente}\n"
                            f"ðŸ“† Fecha: {fecha}\n"
                            f"â° Hora: {hora}\n"
                            f"âœ‚ï¸ Servicio: {servicio}\n\n"
                            f"ðŸ“ {config['nombre']}"
                        )
                        
                        if enviar_mensaje(mensaje_cancelacion, telefono_peluquero):
                            print(f"âœ… NotificaciÃ³n de cancelaciÃ³n enviada a {nombre_peluquero}")
                        else:
                            print(f"âš ï¸ No se pudo notificar a {nombre_peluquero}")
                    
                except Exception as e:
                    print(f"âš ï¸ Error en notificaciones: {e}")
                    # AÃºn asÃ­ confirmar al cliente
                    enviar_mensaje(
                        "âœ… Turno cancelado exitosamente\n\n"
                        "Â¡Esperamos verte pronto! ðŸ’ˆ",
                        numero
                    )
            else:
                # âŒ Error al cancelar
                print("âŒ Error cancelando turno en Google Calendar")
                enviar_mensaje(
                    "âŒ Hubo un error al cancelar el turno.\n\n"
                    "Por favor intentÃ¡ mÃ¡s tarde o contacta al negocio.",
                    numero
                )
            
            # Resetear estado en Redis
            estado_usuario["paso"] = "menu"
            set_state(numero_limpio, estado_usuario)
            
        elif texto in ["no", "n"]:
            enviar_mensaje(
                "âœ… CancelaciÃ³n abortada. Tu turno sigue reservado.\n\n"
                "EscribÃ­ *menu* para volver.",
                numero
            )
            
            # Actualizar estado en Redis
            estado_usuario = get_state(numero_limpio) or {}
            estado_usuario["paso"] = "menu"
            set_state(numero_limpio, estado_usuario)
        else:
            enviar_mensaje("âš ï¸ RespondÃ© *SI* o *NO*", numero)
            
    except Exception as e:
        print(f"âŒ ERROR en procesar_confirmacion_cancelacion: {e}")
        import traceback
        traceback.print_exc()
        
        enviar_mensaje(
            "âŒ OcurriÃ³ un error.\n\n"
            "EscribÃ­ *menu* para volver.",
            numero
        )
        
        # Resetear estado en Redis
        estado_usuario = get_state(numero_limpio) or {}
        estado_usuario["paso"] = "menu"
        set_state(numero_limpio, estado_usuario)


# ==================== OPCIÃ“N 4: SERVICIOS ====================

def procesar_servicios(config, numero):
    """Muestra los servicios disponibles"""
    servicios = config.get("servicios", [])
    
    if not servicios:
        enviar_mensaje(
            "âœ‚ï¸ *Nuestros servicios:*\n\n"
            "Contactanos para conocer nuestros servicios.\n\n"
            "EscribÃ­ *menu* para volver",
            numero
        )
    else:
        lista_servicios = []
        for servicio in servicios:
            nombre = servicio["nombre"]
            precio = f"${servicio['precio']:,}".replace(',', '.')
            duracion = servicio["duracion"]
            lista_servicios.append(f"â€¢ {nombre} - {precio} ({duracion} min)")
        
        mensaje = (
            f"âœ‚ï¸ *Servicios de {config['nombre']}:*\n\n" +
            "\n".join(lista_servicios) +
            "\n\nEscribÃ­ *menu* para volver"
        )
        enviar_mensaje(mensaje, numero)


# ==================== OPCIÃ“N 5: REAGENDAR ====================

def procesar_reagendar_inicio(numero_limpio, peluqueria_key, numero):
    """Inicia el flujo de reagendar turno"""
    turnos = obtener_turnos_cliente(peluqueria_key, peluqueria_key, numero_limpio)
    
    if not turnos:
        enviar_mensaje("ðŸ”­ No tenÃ©s turnos para reagendar.\n\nEscribÃ­ *menu* para volver.", numero)
    else:
        # Guardar en Redis con serializaciÃ³n
        estado_usuario = get_state(numero_limpio) or {}
        
        # âš ï¸ Serializar turnos (datetime â†’ ISO string)
        turnos_serializables = []
        for turno in turnos:
            turnos_serializables.append({
                "id": turno["id"],
                "resumen": turno["resumen"],
                "inicio": turno["inicio"].isoformat()
            })
        
        estado_usuario["turnos"] = turnos_serializables
        estado_usuario["paso"] = "seleccionar_turno_reagendar"
        set_state(numero_limpio, estado_usuario)
        
        lista = []
        for i, turno in enumerate(turnos):
            fecha = formatear_fecha_espanol(turno["inicio"])
            hora = turno["inicio"].strftime("%H:%M")
            lista.append(f"{i+1}ï¸âƒ£ {fecha} a las {hora}")
        
        mensaje = "ðŸ”„ *Selecciona el turno a reagendar:*\n\n" + "\n".join(lista)
        enviar_mensaje(mensaje, numero)


def procesar_seleccion_turno_reagendar(numero_limpio, texto, numero):
    """Procesa la selecciÃ³n del turno a reagendar"""
    try:
        opcion = int(texto) - 1
        
        # Obtener de Redis
        estado_usuario = get_state(numero_limpio) or {}
        turnos = estado_usuario.get("turnos", [])

        if opcion < 0 or opcion >= len(turnos):
            enviar_mensaje("âŒ OpciÃ³n invÃ¡lida. ElegÃ­ un nÃºmero de la lista.", numero)
            return

        turno_seleccionado = turnos[opcion]
        
        # Guardar en Redis
        estado_usuario["turno_a_reagendar"] = turno_seleccionado
        estado_usuario["paso"] = "menu"
        set_state(numero_limpio, estado_usuario)

        enviar_mensaje(
            "â„¹ï¸ Para reagendar:\n\n"
            "1ï¸âƒ£ Primero cancelÃ¡ tu turno actual (opciÃ³n 3)\n"
            "2ï¸âƒ£ Luego pedÃ­ uno nuevo (opciÃ³n 1)\n\n"
            "EscribÃ­ *menu* para volver",
            numero
        )

    except ValueError:
        enviar_mensaje("âŒ EnviÃ¡ solo el nÃºmero del turno.", numero)


# ==================== OPCIÃ“N 6: FAQ ====================

def procesar_faq(numero):
    """Muestra preguntas frecuentes"""
    mensaje = """ðŸ“– *Preguntas Frecuentes:*

*Â¿Puedo cambiar la hora?*
CancelÃ¡ el turno actual y reservÃ¡ uno nuevo

*Â¿Con cuÃ¡nto tiempo de anticipaciÃ³n debo reservar?*
PodÃ©s reservar hasta con 7 dÃ­as de anticipaciÃ³n

*Â¿QuÃ© pasa si llego tarde?*
IntentÃ¡ llegar 5 min antes. Si llegÃ¡s mÃ¡s de 15 min tarde, tu turno podrÃ­a ser reasignado

*Â¿Formas de pago?*
Efectivo, dÃ©bito y crÃ©dito

EscribÃ­ *menu* para volver"""
    
    enviar_mensaje(mensaje, numero)


# ==================== OPCIÃ“N 7: UBICACIÃ“N ====================

def procesar_ubicacion(config, numero):
    """Muestra ubicaciÃ³n y contacto"""
    mensaje = f"""ðŸ“ *UbicaciÃ³n de {config['nombre']}:*

DirecciÃ³n: Calle Ejemplo 123, Buenos Aires

ðŸ•’ *Horarios:*
Lunes a Viernes: 08:00 - 21:00
SÃ¡bados: 08:00 - 19:00
Domingos: Cerrado

ðŸ“ž *Contacto:*
TelÃ©fono: +54 9 11 1234-5678

EscribÃ­ *menu* para volver"""
    
    enviar_mensaje(mensaje, numero)

# ==================== OPCIÃ“N SELECCIÃ“N DE PELUQUEROS ====================

def procesar_seleccion_peluquero(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selecciÃ³n del peluquero - Valida que estÃ© activo"""
    try:
        # Obtener de Redis
        estado_usuario = get_state(numero_limpio) or {}
        peluqueros = estado_usuario.get("peluqueros_disponibles", [])
        
        # Si no existe la lista filtrada, obtener de config (fallback)
        if not peluqueros:
            config = PELUQUERIAS.get(peluqueria_key, {})
            peluqueros = [p for p in config.get("peluqueros", []) if p.get("activo", True)]
        
        index = int(texto) - 1
        
        if 0 <= index < len(peluqueros):
            peluquero_seleccionado = peluqueros[index]
            
            # Verificar que estÃ© activo
            if not peluquero_seleccionado.get("activo", True):
                enviar_mensaje(
                    f"ðŸ˜• {peluquero_seleccionado['nombre']} no estÃ¡ disponible en este momento.\n\n"
                    "EscribÃ­ *menu* para elegir otro peluquero.",
                    numero
                )
                
                # Actualizar estado en Redis
                estado_usuario["paso"] = "menu"
                set_state(numero_limpio, estado_usuario)
                return
            
            # Guardar peluquero en Redis
            estado_usuario["peluquero"] = peluquero_seleccionado
            
            print(f"âœ… Peluquero guardado: {peluquero_seleccionado['nombre']}")
            
            # Generar dÃ­as disponibles para este peluquero
            hoy = datetime.now().date()
            dias = []
            dias_semana_map = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
            
            for i in range(7):
                dia = hoy + timedelta(days=i)
                dia_nombre = dias_semana_map[dia.weekday()]
                
                if dia_nombre in peluquero_seleccionado.get("dias_trabajo", []):
                    dias.append(dia)
            
            if not dias:
                enviar_mensaje(
                    f"ðŸ˜• {peluquero_seleccionado['nombre']} no tiene dÃ­as disponibles esta semana.\n\n"
                    "EscribÃ­ *menu* para elegir otro peluquero.",
                    numero
                )
                estado_usuario["paso"] = "menu"
                set_state(numero_limpio, estado_usuario)
                return
            # CONVERTIR a ISO strings antes de guardar
            dias_iso = [d.isoformat() for d in dias]
            # dias_iso = ["2026-01-15", "2026-01-16", "2026-01-17", ...]

            estado_usuario = {
                "paso": "seleccionar_dia",
                "dias": dias_iso  # â† Guardamos strings
            }

            set_state(numero_limpio, estado_usuario)   
            # Guardar dÃ­as en Redis (como ISO strings)
            estado_usuario["dias"] = [d.isoformat() for d in dias]
            estado_usuario["paso"] = "seleccionar_dia"
            set_state(numero_limpio, estado_usuario)
            
            print(f"âœ… Estado cambiado a: seleccionar_dia con {len(dias)} dÃ­as disponibles")
            
            # Mostrar dÃ­as
            dias_espanol = {0: 'Lun', 1: 'Mar', 2: 'MiÃ©', 3: 'Jue', 4: 'Vie', 5: 'SÃ¡b', 6: 'Dom'}
            lista = "\n".join(
                formatear_item_lista(i, f"{dias_espanol[d.weekday()]} {d.strftime('%d/%m')}")
                for i, d in enumerate(dias)
            )
            
            enviar_mensaje(
                f"ðŸ“… DÃ­as disponibles de *{peluquero_seleccionado['nombre']}*:\n\n{lista}\n\nElegÃ­ un nÃºmero:",
                numero
            )
        else:
            enviar_mensaje("âŒ NÃºmero invÃ¡lido. ElegÃ­ uno de la lista.", numero)
    
    except ValueError:
        enviar_mensaje("âŒ Debe ser un nÃºmero.", numero)
    except Exception as e:
        print(f"âŒ Error en procesar_seleccion_peluquero: {e}")
        import traceback
        traceback.print_exc()
        enviar_mensaje(
            "âŒ OcurriÃ³ un error. EscribÃ­ *menu* para reintentar.",
            numero
        )
        
        # Resetear estado en Redis
        estado_usuario = get_state(numero_limpio) or {}
        estado_usuario["paso"] = "menu"
        set_state(numero_limpio, estado_usuario)

# ==================== OPCIÃ“N 0: SALIR ====================

def procesar_salir(config, numero_limpio, numero):
    """Procesa la salida del menÃº"""
    enviar_mensaje(
         "ðŸ‘‹ Â¡Gracias por contactarnos!\n\n"
         "Cuando quieras volver, escribÃ­ *hola* o *menu*\n\n"
        f"*{config['nombre']}* ðŸ’ˆ",
        numero
    )
    
    # Actualizar estado en Redis
    estado_usuario = get_state(numero_limpio) or {}
    estado_usuario["paso"] = "finalizado"
    set_state(numero_limpio, estado_usuario)

# ==================== GUARDAR AL CERRAR ====================


# ==================== INICIO DEL SERVIDOR ====================

if __name__ == "__main__":
    print("=" * 50)
    print("ðŸ¤– BOT DE PELUQUERÃA MULTI-CLIENTE")
    print("=" * 50)
    print(f"âœ… Clientes cargados: {len(PELUQUERIAS)}")
    for key, config in PELUQUERIAS.items():
        print(f"   â€¢ {config['nombre']} ({key})")
    print("=" * 50)
    
    # Iniciar recordatorios solo en producciÃ³n
    if not MODO_DESARROLLO:
        hilo_recordatorios = threading.Thread(target=sistema_recordatorios, daemon=True)
        hilo_recordatorios.start()
        print("âœ… Sistema de recordatorios activado")
    else:
        print("ðŸ§ª Recordatorios desactivados en desarrollo")
    print("âœ… Sistema de recordatorios activado")
    
    # Puerto dinÃ¡mico para deployment
    port = int(os.environ.get("PORT", 3000))
    print(f"ðŸš€ Servidor iniciando en puerto {port}")
    print("=" * 50)
    
    # Debug segÃºn modo
    app.run(host="0.0.0.0", port=port, debug=MODO_DESARROLLO)

