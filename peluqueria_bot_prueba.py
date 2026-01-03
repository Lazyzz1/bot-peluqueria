from flask import Flask, request
import requests 
from google.auth.transport.requests import Request
import json
from datetime import datetime, timedelta
import pytz
import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
import threading
import time
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import base64
from threading import Lock


MODO_DESARROLLO = 'run_local' in sys.argv[0] or os.getenv('FLASK_ENV') == 'development'

if MODO_DESARROLLO:
    print("="*60)
    print("🧪 MODO DESARROLLO ACTIVADO")
    print("="*60)
    load_dotenv('.env.local')  # Usar configuración local
else:
    print("="*60)
    print("🚀 MODO PRODUCCIÓN")
    print("="*60)
    load_dotenv()  # Usar configuración normal
#----------------------------------------------------------------
app = Flask(__name__)


# ==================== CONFIGURACIÓN DE PLANTILLAS ====================

# Activar/desactivar uso de plantillas aprobadas
USAR_PLANTILLAS = True  # Cambiar a False para usar mensajes normales

# Content SIDs de plantillas (obtener de Twilio Content Editor)
TEMPLATE_CONFIRMACION = os.getenv("TEMPLATE_CONFIRMACION", "HXxxxxx")
TEMPLATE_RECORDATORIO = os.getenv("TEMPLATE_RECORDATORIO", "HXxxxxx")
TEMPLATE_NUEVO_TURNO = os.getenv("TEMPLATE_NUEVO_TURNO", "HXxxxxx")
TEMPLATE_MODIFICADO = os.getenv("TEMPLATE_MODIFICADO", "HXxxxxx")

# Verificar que los SIDs estén configurados
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
        print("❌ ERROR: Faltan Content SIDs de WhatsApp:")
        for f in faltantes:
            print(f"   - {f}")
        raise SystemExit(1)

# ------------------- CONFIGURACIÓN DE META ---------------------

load_dotenv()  # Carga variables de .env

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER]):
    raise ValueError("❌ Faltan variables de entorno de Twilio")

# Inicializar cliente de Twilio
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
# ------------------------------------------------------------------------
SCOPES = ['https://www.googleapis.com/auth/calendar']
# Leer carpeta clientes.json
# Cargar configuración de clientes
try:
    with open("clientes.json", "r", encoding="utf-8") as f:
        PELUQUERIAS = json.load(f)
    
except FileNotFoundError:
    raise FileNotFoundError("❌ No se encontró clientes.json")
except json.JSONDecodeError:
    raise ValueError("❌ clientes.json está corrupto")

# Crear carpeta tokens
os.makedirs('tokens', exist_ok=True)
# ==================== ARCHIVOS Y CACHE ====================

ARCHIVO_RECORDATORIOS = "recordatorios_enviados.json"
ARCHIVO_ESTADOS = "user_states.json"

# Thread-safe structures
user_states = {}
user_states_lock = Lock()
recordatorios_enviados = set()
recordatorios_lock = Lock()
services_cache = {}
# ==================== FUNCIONES DE FORMATEO ====================

def formatear_fecha_espanol(fecha):
    """Formatea fecha en español"""
    dias = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado',
        'Sunday': 'Domingo'
    }
    
    dia_semana = fecha.strftime('%A')
    dia_semana_es = dias.get(dia_semana, dia_semana)
    fecha_str = fecha.strftime('%d/%m/%Y')
    
    return f"{dia_semana_es} {fecha_str}"

def formatear_fecha_completa(fecha):
    """Formato más completo: "Lunes 16 de Diciembre, 15:00" """
    dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
             'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    dia_semana = dias[fecha.weekday()]
    mes = meses[fecha.month - 1]
    
    return f"{dia_semana} {fecha.day} de {mes}, {fecha.strftime('%H:%M')}"

def formatear_item_lista(indice, texto):
    """
    Formatea items de lista con emojis (1-9) o negritas (10+)
    
    Args:
        indice: Índice en la lista (0-based)
        texto: Texto del item
    
    Returns:
        String formateado
    """
    numero = indice + 1
    
    # Emojis numéricos del 1 al 9
    emojis = {
        1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣",
        6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣"
    }
    
    if numero in emojis:
        return f"{emojis[numero]} {texto}"
    else:
        return f"*{numero}.* {texto}"

def obtener_peluqueros_disponibles(peluqueria_key, dia_seleccionado, servicio=None):
    """
    Obtiene los peluqueros que trabajan en un día específico
    y opcionalmente que hagan un servicio específico
    """
    config = PELUQUERIAS.get(peluqueria_key, {})
    peluqueros = config.get("peluqueros", [])
    
    if not peluqueros:
        return []
    
    dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
    dia_nombre = dias_semana[dia_seleccionado.weekday()]
    
    peluqueros_disponibles = []
    
    for peluquero in peluqueros:
        # Verificar si trabaja ese día
        if dia_nombre not in peluquero.get("dias_trabajo", []):
            continue
        
        # Si se especificó un servicio, verificar especialidad
        if servicio:
            especialidades = peluquero.get("especialidades", [])
            if servicio not in especialidades:
                continue
        
        peluqueros_disponibles.append(peluquero)
    
    return peluqueros_disponibles




def obtener_horarios_peluquero(peluqueria_key, dia_seleccionado, peluquero_id):
    """
    Obtiene horarios disponibles de un peluquero específico
    ✅ SOPORTA HORARIOS PARTIDOS (mañana y tarde)
    ✅ MANEJA FORMATO MIXTO CORRECTAMENTE
    """
    try:
        config = PELUQUERIAS.get(peluqueria_key, {})
        peluqueros = config.get("peluqueros", [])
        
        # Buscar el peluquero
        peluquero = None
        for p in peluqueros:
            if p["id"] == peluquero_id:
                peluquero = p
                break
        
        if not peluquero:
            print(f"❌ Peluquero {peluquero_id} no encontrado")
            return []
        
        # Obtener horarios del peluquero para ese día
        dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        dia_nombre = dias_semana[dia_seleccionado.weekday()]
        
        horarios_dia = peluquero.get("horarios", {}).get(dia_nombre)
        
        if not horarios_dia:
            print(f"❌ {peluquero['nombre']} no trabaja los {dia_nombre}")
            return []
        
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        
        # ✅ CRÍTICO: Normalizar formato ANTES de procesar
        # Detectar si primer elemento es string (formato viejo) o list (formato nuevo)
        if horarios_dia and isinstance(horarios_dia[0], str):
            # Formato viejo: ["09:00", "18:00"] → [["09:00", "18:00"]]
            horarios_dia = [horarios_dia]
            print(f"📅 {peluquero['nombre']} - {dia_nombre}: formato viejo convertido")
        else:
            print(f"📅 {peluquero['nombre']} - {dia_nombre}: formato nuevo (partidos)")
        
        # Obtener servicio de Calendar
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)
        
        if not service:
            print(f"❌ No se pudo obtener servicio de Calendar")
            return []
        
        # ✅ Procesar cada rango horario
        horarios_libres = []
        
        for idx, rango in enumerate(horarios_dia):
            # ✅ Validación estricta
            if not isinstance(rango, list) or len(rango) != 2:
                print(f"❌ Rango inválido en posición {idx}: {rango}")
                continue
            
            hora_inicio_str, hora_fin_str = rango
            
            # ✅ Validar que sean strings
            if not isinstance(hora_inicio_str, str) or not isinstance(hora_fin_str, str):
                print(f"❌ Formato de hora inválido: {hora_inicio_str}, {hora_fin_str}")
                continue
            
            try:
                # Parsear horas
                hora_inicio = tz.localize(
                    datetime.combine(dia_seleccionado, datetime.min.time()).replace(
                        hour=int(hora_inicio_str.split(':')[0]),
                        minute=int(hora_inicio_str.split(':')[1])
                    )
                )
                
                hora_fin = tz.localize(
                    datetime.combine(dia_seleccionado, datetime.min.time()).replace(
                        hour=int(hora_fin_str.split(':')[0]),
                        minute=int(hora_fin_str.split(':')[1])
                    )
                )
                
            except (ValueError, IndexError) as e:
                print(f"❌ Error parseando {hora_inicio_str}-{hora_fin_str}: {e}")
                continue
            
            # Si es hoy, ajustar hora_inicio
            if dia_seleccionado == ahora.date():
                if ahora > hora_inicio:
                    minutos = (ahora.minute // 30 + 1) * 30
                    if minutos >= 60:
                        hora_inicio = ahora.replace(hour=ahora.hour + 1, minute=0, second=0, microsecond=0)
                    else:
                        hora_inicio = ahora.replace(minute=minutos, second=0, microsecond=0)
                
                # Si ya pasó este rango, continuar
                if ahora >= hora_fin:
                    print(f"⏭️ Rango {hora_inicio_str}-{hora_fin_str} ya pasó")
                    continue
            
            # Obtener eventos ocupados
            try:
                eventos = service.events().list(
                    calendarId=calendar_id,
                    timeMin=hora_inicio.isoformat(),
                    timeMax=hora_fin.isoformat(),
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
            except Exception as e:
                print(f"❌ Error obteniendo eventos: {e}")
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
        
        print(f"✅ {peluquero['nombre']} - {dia_nombre}: {len(horarios_libres)} slots disponibles")
        return horarios_libres
        
    except Exception as e:
        print(f"❌ Error obteniendo horarios: {e}")
        import traceback
        traceback.print_exc()
        return []


# ==================== GOOGLE TOKEN ====================

def restaurar_token_google_master():
    """Restaura el token de Google desde variable de entorno"""
    token_b64 = os.getenv("GOOGLE_TOKEN_MASTER")
    if not token_b64:
        print("⚠️ GOOGLE_TOKEN_MASTER no configurado")
        return

    token_path = "tokens/master_token.json"
    
    # ❌ NUNCA imprimir tokens en producción
    # print("GOOGLE_TOKEN_MASTER =", os.getenv("GOOGLE_TOKEN_MASTER"))  # ELIMINADO

    if not os.path.exists(token_path):
        try:
            with open(token_path, "wb") as f:
                f.write(base64.b64decode(token_b64))
            print("✅ Token Google master restaurado")
        except Exception as e:
            print(f"❌ Error restaurando token: {e}")

restaurar_token_google_master()


# ------------------- CONFIGURACIÓN GOOGLE CALENDAR ---------------------


def get_calendar_service(peluqueria_key):
    """Conecta con Google Calendar para una peluquería específica"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            print(f"❌ Peluquería no encontrada: {peluqueria_key}")
            return None
            
        config = PELUQUERIAS[peluqueria_key]
        token_file = config["token_file"]

        if not os.path.exists(token_file):
            print(f"❌ ERROR: No existe {token_file}")
            return None

        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
                print(f"✅ Token Google refrescado ({peluqueria_key})")
            except Exception as e:
                print(f"❌ Error refrescando token ({peluqueria_key}): {e}")
                return None

        return build("calendar", "v3", credentials=creds)

    except Exception as e:
        print(f"❌ Error conectando Google Calendar para {peluqueria_key}: {e}")
        return None

def get_calendar_config(peluqueria_key):
    """Obtiene el calendar_id de una peluquería"""
    if peluqueria_key not in PELUQUERIAS:
        raise ValueError(f"Peluquería no encontrada: {peluqueria_key}")
    return PELUQUERIAS[peluqueria_key]["calendar_id"]

def esta_ocupado(horario, ocupados):
    """Verifica si un horario está ocupado con 1 minuto de tolerancia"""
    for ocupado in ocupados:
        if abs((horario - ocupado).total_seconds()) < 60:
            return True
    return False

def obtener_horarios_disponibles(peluqueria_key, dia_seleccionado=None):
    """Genera turnos y revisa eventos ocupados en Google Calendar"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            print(f"❌ Peluquería inválida: {peluqueria_key}")
            return []
            
        service = get_calendar_service(peluqueria_key)
        
        if not service:
            print("❌ Service es None, retornando []")
            return []

        calendar_id = get_calendar_config(peluqueria_key)
        
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        
        if dia_seleccionado is None:
            dia_seleccionado = ahora.date()

        # Si el día es domingo, retornar vacío
        if dia_seleccionado.weekday() == 6:
            return []

        # Obtener horarios de la configuración
        config = PELUQUERIAS[peluqueria_key]
        dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        dia_nombre = dias_semana[dia_seleccionado.weekday()]
        
        # Si la peluquería tiene horarios configurados, usarlos
        if "horarios" in config and dia_nombre in config["horarios"]:
            horario_config = config["horarios"][dia_nombre]
            hora_apertura = int(horario_config[0].split(':')[0])
            hora_cierre = int(horario_config[1].split(':')[0])
        else:
            # Horarios por defecto
            hora_apertura = 8
            hora_cierre = 19

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
        print(f"❌ Error obteniendo horarios: {e}")
        return []

def obtener_hora_cierre(peluqueria_key, dia_seleccionado, peluquero=None):
    """
    Obtiene la hora de cierre para un día específico
    Considera horarios del peluquero si está especificado
    
    Args:
        peluqueria_key: ID del cliente
        dia_seleccionado: Objeto date
        peluquero: Dict del peluquero (opcional)
    
    Returns:
        datetime con la hora de cierre en timezone Argentina
    """
    try:
        config = PELUQUERIAS.get(peluqueria_key, {})
        dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        dia_nombre = dias_semana[dia_seleccionado.weekday()]
        
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        
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
            hora_cierre_str = "19:00" if dia_nombre != "sabado" else "14:00"
        
        hora_cierre = tz.localize(
            datetime.combine(dia_seleccionado, datetime.min.time()).replace(
                hour=int(hora_cierre_str.split(':')[0]),
                minute=int(hora_cierre_str.split(':')[1])
            )
        )
        
        return hora_cierre
        
    except Exception as e:
        print(f"❌ Error obteniendo hora de cierre: {e}")
        # Retornar hora por defecto en caso de error
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        return tz.localize(
            datetime.combine(dia_seleccionado, datetime.min.time()).replace(hour=19, minute=0)
        )

def obtener_turnos_cliente(peluqueria_key, telefono):
    """Obtiene todos los turnos futuros de un cliente"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            print(f"❌ Peluquería inválida: {peluqueria_key}")
            return []
            
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)

        if not service:
            print("❌ No se pudo obtener el servicio de Calendar")
            return []

        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        
        try:
            eventos = service.events().list(
                calendarId=calendar_id,
                timeMin=ahora.isoformat(),
                timeMax=(ahora + timedelta(days=30)).isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
        except Exception as e:
            print(f"❌ Error obteniendo eventos: {e}")
            return []
        
        turnos_cliente = []
        
        # Limpiar el teléfono de búsqueda
        telefono_busqueda = telefono.replace('whatsapp:', '').replace('+', '').replace(' ', '').replace('-', '')
        
        if "items" in eventos:
            for event in eventos["items"]:
                try:
                    descripcion = event.get("description", "")
                    summary = event.get("summary", "Sin título")
                    
                    # Limpiar la descripción
                    descripcion_limpia = descripcion.replace('+', '').replace(' ', '').replace('-', '').replace('Tel:', '').replace('\n', '').replace('\r', '')
                    
                    # Búsqueda flexible
                    if telefono_busqueda in descripcion_limpia:
                        inicio_str = event["start"].get("dateTime", event["start"].get("date"))
                        
                        if not inicio_str:
                            continue
                        
                        # Parsear fecha con timezone
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
                    print(f"❌ Error procesando evento individual: {e}")
                    continue
        
        return turnos_cliente
        
    except Exception as e:
        print(f"❌ Error general en obtener_turnos_cliente: {e}")
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
        print(f"❌ Error cancelando turno: {e}")
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

        # Descripción con o sin peluquero
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

        service.events().insert(
            calendarId=calendar_id,
            body=evento
        ).execute()

        return True

    except Exception as e:
        print(f"❌ Error creando reserva: {e}")
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
            print("⚠️ Archivo corrupto, creando backup...")
            os.rename(ARCHIVO_RECORDATORIOS, f"{ARCHIVO_RECORDATORIOS}.backup")
            return set()
        except Exception as e:
            print(f"⚠️ Error cargando recordatorios: {e}")
            return set()
    
    return set()

def guardar_recordatorios_enviados(recordatorios):
    """Guarda los recordatorios enviados en el archivo JSON"""
    try:
        with open(ARCHIVO_RECORDATORIOS, "w", encoding="utf-8") as f:
            json.dump(list(recordatorios), f, indent=2)
    except PermissionError:
        print("❌ No hay permisos para escribir el archivo")
    except Exception as e:
        print(f"❌ Error guardando recordatorios: {e}")

def obtener_turnos_proximos(peluqueria_key, horas_anticipacion=24):
    """Obtiene turnos que ocurrirán en X horas"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            return []
            
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)
        
        if not service:
            return []
        
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        
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
                    print(f"❌ Error procesando evento para recordatorio: {e}")
                    continue
        
        return turnos_recordar
    
    except Exception as e:
        print(f"❌ Error obteniendo turnos próximos: {e}")
        return []

def enviar_recordatorio(turno):
    """Envía un recordatorio de turno al cliente usando plantilla aprobada"""
    try:
        # Verificar si el usuario tiene recordatorios activos
        with user_states_lock:
            if turno["telefono"] in user_states:
                if not user_states[turno["telefono"]].get("recordatorios_activos", True):
                    print(f"⏭️ Usuario {turno['telefono']} tiene recordatorios desactivados")
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
        
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        diferencia = turno["inicio"] - ahora
        horas_faltantes = int(diferencia.total_seconds() / 3600)
        
        print(f"📤 Enviando recordatorio a {turno['telefono']} ({horas_faltantes}h antes)")
        
        # Usar plantilla de recordatorio
        if horas_faltantes >= 20:  # Recordatorio de 24 horas
            resultado = enviar_con_plantilla(
                telefono=turno["telefono"],
                content_sid=TEMPLATE_RECORDATORIO,
                variables={
                    "1": nombre_cliente,  # {{1}} = Nombre
                    "2": fecha,           # {{2}} = Fecha
                    "3": hora,            # {{3}} = Hora
                    "4": servicio         # {{4}} = Servicio
                }
            )
            
            if resultado:
                print(f"✅ Recordatorio 24h enviado con plantilla")
            
        elif 1 <= horas_faltantes < 3:  # Recordatorio de 2 horas
            # Para 2h podemos usar mensaje normal o crear otra plantilla
            mensaje = (
                f"⏰ *Recordatorio urgente*\n\n"
                f"Tu turno es en {horas_faltantes} horas:\n\n"
                f"🕒 Hora: {hora}\n"
                f"✂️ {servicio}\n\n"
                f"¡Nos vemos pronto! 💈"
            )
            enviar_mensaje(mensaje, turno["telefono"])
            print(f"✅ Recordatorio 2h enviado")
        
    except Exception as e:
        print(f"❌ Error enviando recordatorio: {e}")
        import traceback
        traceback.print_exc()

def sistema_recordatorios():
    """Sistema de recordatorios en segundo plano"""
    global recordatorios_enviados
    
    # Cargar recordatorios previos
    recordatorios_enviados = cargar_recordatorios_enviados()
    print(f"📂 Cargados {len(recordatorios_enviados)} recordatorios previos")
    print("🔔 Sistema de recordatorios iniciado")
    
    while True:
        try:
            ahora = datetime.now().strftime('%H:%M')
            print(f"\n⏰ [{ahora}] Verificando turnos próximos...")
            
            # Verificar TODAS las peluquerías
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
                                print(f"   📤 Recordatorio 24h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")
                    
                    # Recordatorios de 2 horas
                    turnos_2h = obtener_turnos_proximos(peluqueria_key, horas_anticipacion=2)
                    for turno in turnos_2h:
                        recordatorio_id = f"{turno['id']}_2h"
                        
                        with recordatorios_lock:
                            if recordatorio_id not in recordatorios_enviados:
                                enviar_recordatorio(turno)
                                recordatorios_enviados.add(recordatorio_id)
                                guardar_recordatorios_enviados(recordatorios_enviados)
                                print(f"   📤 Recordatorio 2h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")
                
                except Exception as e:
                    print(f"   ❌ Error procesando {peluqueria_key}: {e}")
                    continue
            
            print("   ✅ Verificación completada. Próxima en 1 hora.")
            
            # Limpiar recordatorios antiguos
            with recordatorios_lock:
                if len(recordatorios_enviados) > 1000:
                    recordatorios_enviados.clear()
                    guardar_recordatorios_enviados(recordatorios_enviados)
                    print("   ✅ Limpieza completada")
            
        except Exception as e:
            print(f"   ❌ Error en sistema de recordatorios: {e}")
        
        time.sleep(3600)  # 1 hora
# ------------------- MENSAJERÍA WHATSAPP ---------------------

def enviar_mensaje(texto, numero):
    """Envía mensaje por WhatsApp usando Twilio"""
    try:
        if not numero.startswith('whatsapp:'):
            numero = f'whatsapp:{numero}'
        
        message = twilio_client.messages.create(
            from_=f'whatsapp:{TWILIO_WHATSAPP_NUMBER}',
            body=texto,
            to=numero
        )
        
        print(f"✅ Mensaje enviado - SID: {message.sid}")
        return True
        
    except Exception as e:
        print(f"❌ Error enviando mensaje: {e}")
        return False

def enviar_con_plantilla(telefono, content_sid, variables):
    """
    Envía mensaje usando plantilla aprobada de Twilio
    
    Args:
        telefono: Número destino (con o sin 'whatsapp:')
        content_sid: Content SID de la plantilla (ej: HXxxxx...)
        variables: Dict con las variables de la plantilla
        
    Returns:
        bool: True si se envió correctamente
    """
    try:
        # Limpiar número
        numero_limpio = telefono.replace('whatsapp:', '').strip()
        numero_formateado = f'whatsapp:{numero_limpio}'
        
        print(f"\n📤 Enviando con plantilla:")
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
        
        print(f"✅ Mensaje con plantilla enviado - SID: {message.sid}")
        print(f"   Status: {message.status}")
        return True
        
    except Exception as e:
        print(f"❌ Error enviando con plantilla: {e}")
        import traceback
        traceback.print_exc()
        return False


def notificar_peluquero(peluquero, cliente, servicio, fecha_hora, config, telefono_cliente=None):
    """
    Envía notificación al peluquero cuando se reserva un turno
    ✅ Incluye teléfono del cliente
    """
    try:
        telefono_peluquero = peluquero.get("telefono")
        
        if not telefono_peluquero:
            print(f"⚠️ Peluquero {peluquero['nombre']} no tiene teléfono configurado")
            return False
        
        # Formatear fecha y hora
        fecha_formateada = formatear_fecha_espanol(fecha_hora)
        hora = fecha_hora.strftime("%H:%M")
        
        # ✅ DEBUG: Verificar qué llega
        print(f"\n{'='*60}")
        print(f"📞 DEBUG NOTIFICACIÓN:")
        print(f"   Peluquero: {peluquero['nombre']}")
        print(f"   Tel peluquero: {telefono_peluquero}")
        print(f"   Cliente: {cliente}")
        print(f"   Tel cliente recibido: {telefono_cliente}")
        print(f"   Tipo: {type(telefono_cliente)}")
        print(f"{'='*60}\n")
        
        # ✅ Formatear teléfono del cliente
        telefono_mostrar = "No disponible"
        
        if telefono_cliente:
            # Limpiar cualquier cosa rara
            tel_limpio = str(telefono_cliente).replace("whatsapp:", "").strip()
            
            print(f"   Tel limpio: {tel_limpio}")
            
            # Formatear según país
            if tel_limpio.startswith("+549"):
                # Argentina con 9: +54 9 297 4210-130
                codigo_area = tel_limpio[4:7]  # 297
                primera_parte = tel_limpio[7:11]  # 4210
                segunda_parte = tel_limpio[11:]  # 130
                telefono_mostrar = f"+54 9 {codigo_area} {primera_parte}-{segunda_parte}"
                
            elif tel_limpio.startswith("+54"):
                # Argentina sin 9
                codigo_area = tel_limpio[3:6]
                primera_parte = tel_limpio[6:10]
                segunda_parte = tel_limpio[10:]
                telefono_mostrar = f"+54 {codigo_area} {primera_parte}-{segunda_parte}"
                
            elif tel_limpio.startswith("+1"):
                # USA: +1 (262) 476-7007
                area = tel_limpio[2:5]
                primera = tel_limpio[5:8]
                segunda = tel_limpio[8:]
                telefono_mostrar = f"+1 ({area}) {primera}-{segunda}"
            else:
                # Otro formato
                telefono_mostrar = tel_limpio
            
            print(f"   Tel formateado: {telefono_mostrar}")
        else:
            print(f"   ⚠️ telefono_cliente es None o vacío")
        
        # Crear mensaje
        mensaje_peluquero = (
            f"🔔 *Nuevo turno reservado*\n\n"
            f"👤 Cliente: {cliente}\n"
            f"📞 Teléfono: {telefono_mostrar}\n"
            f"📅 Fecha: {fecha_formateada}\n"
            f"🕐 Hora: {hora}\n"
            f"✂️ Servicio: {servicio}\n\n"
            f"📍 {config['nombre']}"
        )
        
        print(f"\n📱 Enviando notificación a {telefono_peluquero}")
        print(f"📄 Mensaje:\n{mensaje_peluquero}\n")
        
        resultado = enviar_mensaje(mensaje_peluquero, telefono_peluquero)
        
        if resultado:
            print(f"✅ Notificación enviada correctamente")
        else:
            print(f"❌ Error enviando notificación")
        
        return resultado
        
    except Exception as e:
        print(f"❌ Error en notificar_peluquero: {e}")
        import traceback
        traceback.print_exc()
        return False



def detectar_peluqueria(to_number):
    """
    Detecta qué peluquería según el número de Twilio que recibió el mensaje.
    Sistema multi-tenant para SaaS.
    """
    # Limpiar el número (quitar whatsapp: y espacios)
    numero_twilio = to_number.replace("whatsapp:", "").strip()
    
    print(f"🔍 Detectando cliente para número Twilio: {numero_twilio}")
    
    # Buscar qué cliente tiene este número de Twilio asignado
    for cliente_key, config in PELUQUERIAS.items():
        numero_cliente = config.get("numero_twilio", "").strip()
        
        if numero_cliente and numero_cliente == numero_twilio:
            print(f"✅ Cliente encontrado: {cliente_key} ({config['nombre']})")
            return cliente_key
    
    # Si no se encuentra, registrar el error
    print(f"❌ No se encontró cliente para el número: {numero_twilio}")
    print(f"📋 Números Twilio registrados:")
    for key, cfg in PELUQUERIAS.items():
        print(f"   • {key}: {cfg.get('numero_twilio', 'NO CONFIGURADO')}")
    
    # Retornar None para manejar el error apropiadamente
    return None
def obtener_menu_principal(peluqueria_key):
    """Genera el menú principal personalizado"""
    config = PELUQUERIAS.get(peluqueria_key, {})
    nombre = config.get("nombre", "Peluquería")
    
    return (
        f"👋 ¡Hola! Bienvenido a *{nombre}* 💈\n\n"
        "Elige una opción:\n"
        "1️⃣ Pedir turno\n"
        "2️⃣ Ver mis turnos\n"
        "3️⃣ Cancelar turno\n"
        "4️⃣ Servicios y precios\n"
        "5️⃣ Reagendar turno\n"
        "6️⃣ Preguntas frecuentes\n"
        "7️⃣ Ubicación y contacto\n"
        "0️⃣ Salir\n\n"
        "Escribí el número de la opción"
    )


# ==================== WEBHOOK Y PROCESAMIENTO ====================

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Webhook para recibir mensajes de Twilio WhatsApp
    Sistema multi-tenant: detecta automáticamente el cliente por el número Twilio
    """
    try:
        # Obtener datos del mensaje
        incoming_msg = request.values.get('Body', '').strip().lower()
        numero = request.values.get('From', '')  # Número del usuario
        to_number = request.values.get('To', '')  # Número de Twilio (identifica al cliente)
        
        print("\n" + "="*60)
        print("📨 MENSAJE RECIBIDO")
        print("="*60)
        print(f"👤 De (cliente final): {numero}")
        print(f"📞 Para (número Twilio): {to_number}")
        print(f"💬 Mensaje: {incoming_msg}")
        print("="*60)
        
        # Detectar a qué cliente pertenece este número de Twilio
        peluqueria_key = detectar_peluqueria(to_number)
        
        # VALIDACIÓN CRÍTICA: Si no se encuentra el cliente, no continuar
        if not peluqueria_key or peluqueria_key not in PELUQUERIAS:
            print(f"❌ CLIENTE NO ENCONTRADO")
            print(f"🔧 SOLUCIÓN: Agrega este número en clientes.json:")
            print(f'   "numero_twilio": "{to_number.replace("whatsapp:", "")}"')
            
            enviar_mensaje(
                "❌ *Servicio no configurado*\n\n"
                "Este número de WhatsApp Business no está registrado en el sistema.\n\n"
                "Por favor contacta al administrador del servicio.",
                numero
            )
            return "", 200
        
        print(f"✅ CLIENTE IDENTIFICADO: {peluqueria_key}")
        print(f"🏪 Negocio: {PELUQUERIAS[peluqueria_key]['nombre']}")
        print("="*60 + "\n")
        
        # Limpiar número del usuario
        numero_limpio = numero.replace('whatsapp:', '')
        texto = incoming_msg
        
        # ✅ NUEVO: Inicializar estado si es nuevo usuario O si está en paso "finalizado"
        with user_states_lock:
            if numero_limpio not in user_states:
                print(f"🆕 Nuevo usuario detectado: {numero_limpio}")
                user_states[numero_limpio] = {
                    "paso": "menu",
                    "peluqueria": peluqueria_key
                }
            else:
                # ✅ Si el usuario está en paso "finalizado", reactivarlo
                paso_actual = user_states[numero_limpio].get("paso", "menu")
                if paso_actual == "finalizado":
                    print(f"🔄 Reactivando usuario: {numero_limpio}")
                    user_states[numero_limpio]["paso"] = "menu"
                
                # Actualizar la peluquería por si cambió
                user_states[numero_limpio]["peluqueria"] = peluqueria_key
        
        # ✅ NUEVO: Comandos globales para volver al menú (más flexibles)
        comandos_menu = ["menu", "menú", "inicio", "hola", "hi", "hey", "buenas", "buenos dias", "buenas tardes", "buen dia", "hola, quiero probar el bot", "quiero probar el bot", "probar el bot"]
        
        if texto in comandos_menu:
            print(f"📋 Comando de menú detectado: '{texto}'")
            with user_states_lock:
                user_states[numero_limpio]["paso"] = "menu"
            enviar_mensaje(obtener_menu_principal(peluqueria_key), numero)
            return "", 200
        
        # Obtener estado actual
        with user_states_lock:
            estado = user_states[numero_limpio].get("paso", "menu")
        
        print(f"📍 Estado actual del usuario: {estado}")
        
        # ✅ NUEVO: Si el usuario está en "menu" y escribe CUALQUIER COSA, mostrar menú
        if estado == "menu":
            # Verificar si es una opción válida del menú (1-7, 0)
            if texto in ["1", "2", "3", "4", "5", "6", "7", "0"]:
                # Es una opción válida, procesarla normalmente
                print(f"✅ Opción de menú válida: {texto}")
                procesar_mensaje(numero_limpio, texto, estado, peluqueria_key, numero)
            else:
                # ✅ NO es una opción válida, mostrar el menú
                print(f"❓ Mensaje no reconocido en menú: '{texto}' -> Mostrando menú")
                enviar_mensaje(
                    f"No entendí tu mensaje. Pero te dejo el menú\n\n" + 
                    obtener_menu_principal(peluqueria_key),
                    numero
                )
            return "", 200
        
        # Comando para cancelar operación actual
        if texto in ["cancelar", "salir", "abortar", "stop", "volver"]:
            if estado != "menu":
                print(f"❌ Usuario canceló operación desde estado: {estado}")
                with user_states_lock:
                    user_states[numero_limpio]["paso"] = "menu"
                enviar_mensaje(
                    "❌ Operación cancelada.\n\n"
                    "Volviste al menú principal.\n"
                    "Escribí *menu* para ver las opciones.",
                    numero
                )
                return "", 200
        
        # Procesar según estado
        procesar_mensaje(numero_limpio, texto, estado, peluqueria_key, numero)
        
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO EN WEBHOOK:")
        print(f"   {str(e)}")
        import traceback
        print("\n📋 STACK TRACE:")
        traceback.print_exc()
        print("="*60 + "\n")
        
        # Intentar enviar mensaje de error al usuario
        try:
            enviar_mensaje(
                "❌ Ocurrió un error temporal.\n\n"
                "Por favor escribí *menu* para reintentar.",
                numero
            )
        except:
            pass
    
    return "", 200


def obtener_menu_principal(peluqueria_key):
    """Genera el menú principal personalizado"""
    config = PELUQUERIAS.get(peluqueria_key, {})
    nombre = config.get("nombre", "Peluquería")
    
    return (
        f"👋 ¡Hola! Bienvenido a *{nombre}* 💈\n\n"
        "Elige una opción:\n"
        "1️⃣ Pedir turno\n"
        "2️⃣ Ver mis turnos\n"
        "3️⃣ Cancelar turno\n"
        "4️⃣ Servicios y precios\n"
        "5️⃣ Reagendar turno\n"
        "6️⃣ Preguntas frecuentes\n"
        "7️⃣ Ubicación y contacto\n"
        "0️⃣ Salir\n\n"
        "Escribí el número de la opción"
    )


def procesar_mensaje(numero_limpio, texto, estado, peluqueria_key, numero):
    """Procesa el mensaje según el estado del usuario"""
    config = PELUQUERIAS[peluqueria_key]
    
    # MENÚ PRINCIPAL
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
        elif texto == "7":  # Ubicación
            procesar_ubicacion(config, numero)    
        elif texto == "0":  # Salir
            procesar_salir(config, numero_limpio, numero)
        else:
            # ✅ NUEVO: Mensaje más amigable para opciones no válidas
            enviar_mensaje(
                f"❓ No entendí '{texto}'\n\n" + 
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
        # ✅ NUEVO: Si el estado es desconocido, resetear a menú
        print(f"⚠️ Estado desconocido: {estado} - Reseteando a menú")
        with user_states_lock:
            user_states[numero_limpio]["paso"] = "menu"
        enviar_mensaje(
            "❓ Hubo un error. Volvamos al inicio.\n\n" + 
            obtener_menu_principal(peluqueria_key),
            numero
        )

# ==================== OPCIÓN 1: PEDIR TURNO ====================

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
    with user_states_lock:
        user_states[numero_limpio]["paso"] = "seleccionar_peluquero"
    
    # Mostrar lista de peluqueros ACTIVOS con sus especialidades
    lista_peluqueros = []
    for i, peluquero in enumerate(peluqueros_activos):
        especialidades = ", ".join(peluquero.get("especialidades", []))
        dias = ", ".join([d.capitalize()[:3] for d in peluquero.get("dias_trabajo", [])])
        
        contenido = (
            f"*{peluquero['nombre']}*\n"
            f"   ✂️ {especialidades}\n"
            f"   📅 {dias}"
        )
        lista_peluqueros.append(formatear_item_lista(i, contenido))
    # Verificar si hay peluqueros no disponibles
    peluqueros_inactivos = [p for p in peluqueros if not p.get("activo", True)]
    nota_inactivos = ""
    
    if peluqueros_inactivos:
        nombres_inactivos = ", ".join([p['nombre'] for p in peluqueros_inactivos])
        nota_inactivos = f"\n\n_⚠️ No disponibles: {nombres_inactivos}_"
        
        # Mostrar mensajes personalizados
        for p in peluqueros_inactivos:
            mensaje_custom = p.get("mensaje_no_disponible")
            if mensaje_custom:
                nota_inactivos += f"\n_{p['nombre']}: {mensaje_custom}_"
    
    mensaje = (
        "👤 *¿Con qué peluquero querés tu turno?*\n\n" +
        "\n\n".join(lista_peluqueros) +
        nota_inactivos +
        "\n\nElegí un número:"
    )
    
    # Guardar solo los activos para validación
    with user_states_lock:
        user_states[numero_limpio]["peluqueros_disponibles"] = peluqueros_activos
    
    enviar_mensaje(mensaje, numero)

def procesar_seleccion_dia(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selección del día"""
    try:
        index = int(texto) - 1
        
        with user_states_lock:
            dias = user_states[numero_limpio].get("dias", [])
            peluquero = user_states[numero_limpio].get("peluquero")

        if 0 <= index < len(dias):
            dia_elegido = dias[index]
            
            # Si hay peluquero seleccionado, usar sus horarios
            if peluquero:
                horarios = obtener_horarios_peluquero(peluqueria_key, dia_elegido, peluquero["id"])
            else:
                # Flujo normal sin peluquero
                horarios = obtener_horarios_disponibles(peluqueria_key, dia_elegido)

            if not horarios:
                enviar_mensaje(
                    "Ese día no tiene horarios disponibles 😕\n\n"
                    "Escribí *menu* para volver.",
                    numero
                )
                return

            with user_states_lock:
                user_states[numero_limpio]["dia"] = dia_elegido
                user_states[numero_limpio]["horarios"] = horarios
                user_states[numero_limpio]["paso"] = "seleccionar_horario"

            lista = "\n".join(
                formatear_item_lista(i, h.strftime('%H:%M'))
                for i, h in enumerate(horarios)

            )

            mensaje_extra = ""
            if peluquero:
                mensaje_extra = f"\n👤 Con: *{peluquero['nombre']}*\n"

            enviar_mensaje(
                f"🕒 Horarios disponibles:{mensaje_extra}\n{lista}\n\nElegí un número, o escribí *menu* para volver al Menú",
                numero
            )
        else:
            enviar_mensaje("❌ Número fuera de rango. Elegí uno de la lista.", numero)

    except ValueError:
        enviar_mensaje("❌ Debe ser un número.", numero)


def procesar_seleccion_horario(numero_limpio, texto, numero):
    """Procesa la selección del horario"""
    try:
        index = int(texto) - 1
        
        with user_states_lock:
            horarios = user_states[numero_limpio].get("horarios", [])
            
            if 0 <= index < len(horarios):
                fecha_hora = horarios[index]
                user_states[numero_limpio]["fecha_hora"] = fecha_hora
                user_states[numero_limpio]["paso"] = "nombre"
        
        enviar_mensaje("Perfecto ✂️ ¿A nombre de quién tomo el turno?", numero)
    except (ValueError, IndexError):
        enviar_mensaje("❌ Número inválido. Elegí uno de la lista.", numero)


def procesar_nombre_cliente(numero_limpio, texto, peluqueria_key, numero):
    """Procesa el nombre del cliente y muestra servicios"""
    with user_states_lock:
        user_states[numero_limpio]["cliente"] = texto.title()
        user_states[numero_limpio]["paso"] = "servicio"
        peluquero = user_states[numero_limpio].get("peluquero")
    
    config = PELUQUERIAS[peluqueria_key]
    servicios = config.get("servicios", [])
    
    # Filtrar servicios según especialidades del peluquero
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
        with user_states_lock:
            user_states[numero_limpio]["servicios_disponibles"] = servicios_a_mostrar
        
        mensaje_peluquero = ""
        if peluquero:
            mensaje_peluquero = f"Con *{peluquero['nombre']}*\n\n"
        
        # Instrucciones para selección múltiple
        mensaje = (
            f"📋 *¿Qué servicio(s) querés?*\n\n"
            f"{mensaje_peluquero}" +
            "\n".join(lista) +
            "\n\n💡 *Podés elegir varios servicios*\n"
            "Ejemplos:\n"
            "• Un servicio: 1\n"
            "• Varios: 1,2 o 1,3\n"
            
        )
        enviar_mensaje(mensaje, numero)
    else:
        enviar_mensaje("📋 ¿Qué servicio querés?\nEj: Corte, Tintura, Barba", numero)

def procesar_seleccion_servicio(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selección del servicio (uno o múltiples) y crea la reserva"""
    config = PELUQUERIAS[peluqueria_key]
    
    with user_states_lock:
        servicios_disponibles = user_states[numero_limpio].get("servicios_disponibles", config.get("servicios", []))
        fecha_hora = user_states[numero_limpio]["fecha_hora"]
        cliente = user_states[numero_limpio]["cliente"]
        peluquero = user_states[numero_limpio].get("peluquero")
    
    # [... código de parseo de servicios ...]
    
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
        servicio_texto = texto.title()
        for serv in servicios_disponibles:
            if serv["nombre"].lower() == texto.lower():
                servicios_seleccionados.append(serv)
                duracion_total = serv.get("duracion", 30)
                break
    
    if not servicios_seleccionados:
        enviar_mensaje("❌ Servicio no válido.\n\nEscribí *menu* para volver.", numero)
        return
    
    # Crear nombres legibles
    if len(servicios_seleccionados) == 1:
        nombre_servicios = servicios_seleccionados[0]["nombre"]
    else:
        nombre_servicios = " + ".join(s["nombre"] for s in servicios_seleccionados)
    
    precio_total = sum(s["precio"] for s in servicios_seleccionados)
    
    # Validar disponibilidad de tiempo
    dia_seleccionado = user_states[numero_limpio].get("dia")
    hora_cierre = obtener_hora_cierre(peluqueria_key, dia_seleccionado, peluquero)
    hora_fin_turno = fecha_hora + timedelta(minutes=duracion_total)
    
    if hora_fin_turno > hora_cierre:
        minutos_faltantes = int((hora_fin_turno - hora_cierre).total_seconds() / 60)
        enviar_mensaje(
            f"⏰ *No hay suficiente tiempo*\n\n"
            f"Los servicios duran *{duracion_total} minutos*\n\n"
            f"📅 Inicio: {fecha_hora.strftime('%H:%M')}\n"
            f"⏱️ Fin: {hora_fin_turno.strftime('%H:%M')}\n"
            f"🔒 Cierre: {hora_cierre.strftime('%H:%M')}\n\n"
            f"❌ Faltan {minutos_faltantes} minutos.\n\n"
            f"Escribí *menu* para elegir otro horario.",
            numero
        )
        return
    
    # ✅ CRÍTICO: Usar numero_limpio (sin whatsapp:)
    telefono_cliente = numero_limpio  # +5492974210130
    
    # ✅ DEBUG: Verificar el teléfono
    print(f"\n{'='*60}")
    print(f"📞 DEBUG TELÉFONO CLIENTE:")
    print(f"   numero (con whatsapp:): {numero}")
    print(f"   numero_limpio: {numero_limpio}")
    print(f"   telefono_cliente: {telefono_cliente}")
    print(f"{'='*60}\n")
    
    # Crear reserva
    print(f"📅 Creando reserva para {cliente} - {nombre_servicios}")
    
    if crear_reserva_multiple(
        peluqueria_key, 
        fecha_hora, 
        cliente, 
        servicios_seleccionados,
        duracion_total,
        telefono_cliente,  # ✅ Pasar sin whatsapp:
        peluquero
    ):
        fecha_formateada = formatear_fecha_espanol(fecha_hora)
        hora = fecha_hora.strftime("%H:%M")
        
        print(f"✅ Reserva creada, enviando confirmación...")
        
        # Enviar confirmación
        resultado = enviar_con_plantilla(
            telefono=numero,  # ← Aquí SÍ va con whatsapp: para Twilio
            content_sid=TEMPLATE_CONFIRMACION,
            variables={
                "1": cliente,
                "2": fecha_formateada,
                "3": hora,
                "4": nombre_servicios,
                "5": config['nombre']
            }
        )
        
        if not resultado:
            enviar_mensaje(
                f"✅ *Turno confirmado*\n\n"
                f"👤 Cliente: {cliente}\n"
                f"📅 Fecha: {fecha_formateada}\n"
                f"🕐 Hora: {hora}\n"
                f"✂️ Servicio(s): {nombre_servicios}\n"
                f"💰 Total: ${precio_total:,}\n\n"
                f"¡Te esperamos! 💈".replace(',', '.'),
                numero
            )
        
        # ✅ Notificar al peluquero CON teléfono
        if peluquero:
            print(f"📱 Notificando a peluquero: {peluquero['nombre']}")
            print(f"   Teléfono cliente a enviar: {telefono_cliente}")
            
            notificar_peluquero(
                peluquero, 
                cliente, 
                nombre_servicios, 
                fecha_hora, 
                config, 
                telefono_cliente  # ✅ SIN whatsapp:
            )
    else:
        enviar_mensaje("❌ Error al crear la reserva.\n\nEscribí *menu*", numero)

    with user_states_lock:
        user_states[numero_limpio]["paso"] = "menu"



        
"""
def procesar_confirmacion_servicios(numero_limpio, texto, peluqueria_key, numero):
    Procesa la confirmación de servicios seleccionados
    try:
        if texto == "1":
            # Confirmar y validar disponibilidad de tiempo
            with user_states_lock:
                servicios_seleccionados = user_states[numero_limpio].get("servicios_seleccionados", [])
                duracion_total = user_states[numero_limpio].get("duracion_total", 30)
                fecha_hora = user_states[numero_limpio]["fecha_hora"]
                cliente = user_states[numero_limpio]["cliente"]
                peluquero = user_states[numero_limpio].get("peluquero")
                dia_seleccionado = user_states[numero_limpio]["dia"]
            
            # Verificar que hay suficiente tiempo antes del cierre
            hora_cierre = obtener_hora_cierre(peluqueria_key, dia_seleccionado, peluquero)
            hora_fin_turno = fecha_hora + timedelta(minutes=duracion_total)
            
            print(f"🕐 Validando disponibilidad:")
            print(f"   Inicio: {fecha_hora.strftime('%H:%M')}")
            print(f"   Duración: {duracion_total}min")
            print(f"   Fin estimado: {hora_fin_turno.strftime('%H:%M')}")
            print(f"   Hora de cierre: {hora_cierre.strftime('%H:%M')}")
            
            if hora_fin_turno > hora_cierre:
                # No hay suficiente tiempo
                minutos_faltantes = int((hora_fin_turno - hora_cierre).total_seconds() / 60)
                
                enviar_mensaje(
                    f"⏰ *No hay suficiente tiempo*\n\n"
                    f"Los servicios seleccionados duran *{duracion_total} minutos*\n\n"
                    f"📅 Inicio: {fecha_hora.strftime('%H:%M')}\n"
                    f"⏱️ Fin estimado: {hora_fin_turno.strftime('%H:%M')}\n"
                    f"🔒 Cierre: {hora_cierre.strftime('%H:%M')}\n\n"
                    f"❌ Faltan {minutos_faltantes} minutos de tiempo disponible.\n\n"
                    f"*Opciones:*\n"
                    f"1️⃣ Elegir otro horario (escribí *menu*)\n"
                    f"2️⃣ Elegir menos servicios (escribí *2*)",
                    numero
                )
                
                print(f"❌ Turno rechazado: Se extiende {minutos_faltantes}min después del cierre")
                return
            
            # Hay suficiente tiempo, proceder con la reserva
            telefono = numero_limpio
            config = PELUQUERIAS[peluqueria_key]
            
            # Crear resumen de servicios
            if len(servicios_seleccionados) == 1:
                resumen_servicios = servicios_seleccionados[0]['nombre']
            else:
                resumen_servicios = " + ".join(s['nombre'] for s in servicios_seleccionados)
            
            # Calcular precio total
            precio_total = sum(s['precio'] for s in servicios_seleccionados)
            
            # Crear reserva con duración personalizada (parámetros completos)
            if crear_reserva_multiple(
                peluqueria_key, 
                fecha_hora, 
                cliente, 
                servicios_seleccionados, 
                duracion_total,
                telefono, 
                peluquero
            ):
                fecha_formateada = formatear_fecha_espanol(fecha_hora)
                hora = fecha_hora.strftime("%H:%M")
                
                # Enviar confirmación con plantilla (UNA SOLA VEZ)
                enviar_con_plantilla(
                    telefono=numero,
                    content_sid=TEMPLATE_CONFIRMACION,
                    variables={
                        "1": cliente,
                        "2": fecha_formateada,
                        "3": hora,
                        "4": resumen_servicios,
                        "5": config['nombre']
                    }
                )
                
                print(f"✅ Turno confirmado: {fecha_hora.strftime('%H:%M')}-{hora_fin_turno.strftime('%H:%M')}")
                
                # Notificar al peluquero (UNA SOLA VEZ)
                if peluquero:
                    notificar_peluquero(peluquero, cliente, resumen_servicios, fecha_hora, config)
                
            else:
                enviar_mensaje(
                    "❌ Hubo un error al crear la reserva.\n\n"
                    "Escribí *menu* para volver.",
                    numero
                )
            
            with user_states_lock:
                user_states[numero_limpio]["paso"] = "menu"
        
        elif texto == "2":
            # Volver a elegir servicios
            with user_states_lock:
                user_states[numero_limpio]["paso"] = "servicio"
                cliente = user_states[numero_limpio]["cliente"]
            
            # Re-mostrar servicios
            procesar_nombre_cliente(numero_limpio, cliente, peluqueria_key, numero)
        
        else:
            enviar_mensaje("❌ Opción inválida. Escribí 1 o 2", numero)
    
    except Exception as e:
        print(f"❌ Error en procesar_confirmacion_servicios: {e}")
        import traceback
        traceback.print_exc()
        enviar_mensaje("❌ Ocurrió un error. Escribí *menu*", numero)
        with user_states_lock:
            user_states[numero_limpio]["paso"] = "menu"
"""
def crear_reserva_multiple(peluqueria_key, fecha_hora, cliente, servicios, duracion_total, telefono, peluquero=None):
    """
    Crea un evento en Google Calendar con múltiples servicios
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
        
        # Descripción detallada
        lista_servicios = "\n".join(
            f"• {s['nombre']} (${s['precio']:,}, {s['duracion']}min)".replace(',', '.')
            for s in servicios
        )
        
        # ✅ IMPORTANTE: Asegurarse que el teléfono se guarde en descripción
        descripcion = (
            f"Cliente: {cliente}\n"
            f"Tel: {telefono}\n"  # ✅ Debe estar SIN whatsapp:
            f"\nServicios:\n{lista_servicios}\n"
            f"\nTotal: ${precio_total:,}".replace(',', '.') + "\n"
            f"Duración total: {duracion_total} min"
        )
        
        if peluquero:
            descripcion += f"\nPeluquero: {peluquero['nombre']}"
        
        # ✅ DEBUG
        print(f"\n📝 Descripción del evento:")
        print(descripcion)
        print()
        
        summary = f"{peluquero['nombre'] if peluquero else 'Turno'} - {nombre_servicios} - {cliente}"
        
        evento = {
            'summary': summary,
            'start': {
                'dateTime': fecha_hora.isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            },
            'end': {
                'dateTime': (fecha_hora + timedelta(minutes=duracion_total)).isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            },
            'description': descripcion,
            'colorId': '9' if len(servicios) > 1 else None
        }

        service.events().insert(
            calendarId=calendar_id,
            body=evento
        ).execute()

        print(f"✅ Reserva creada: {nombre_servicios} ({duracion_total}min)")
        return True

    except Exception as e:
        print(f"❌ Error creando reserva: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==================== OPCIÓN 2: VER TURNOS ====================

def procesar_ver_turnos(numero_limpio, peluqueria_key, numero):
    """Muestra los turnos del cliente"""
    turnos = obtener_turnos_cliente(peluqueria_key, numero_limpio)
    
    if not turnos:
        enviar_mensaje(
            "🔭 No tenés turnos reservados.\n\n"
            "Escribí *menu* para volver.",
            numero
        )
    else:
        lista = []
        for i, turno in enumerate(turnos):
            fecha_formateada = formatear_fecha_espanol(turno["inicio"])
            hora = turno["inicio"].strftime("%H:%M")
            lista.append(f"{i+1}. {fecha_formateada} a las {hora}\n   {turno['resumen']}")
        
        mensaje = "📅 *Tus turnos:*\n\n" + "\n\n".join(lista) + "\n\nEscribí *menu* para volver"
        enviar_mensaje(mensaje, numero)


# ==================== OPCIÓN 3: CANCELAR TURNO ====================

def procesar_cancelar_turno_inicio(numero_limpio, peluqueria_key, numero):
    """Inicia el flujo de cancelar turno"""
    try:
        turnos = obtener_turnos_cliente(peluqueria_key, numero_limpio)
        
        if not turnos:
            enviar_mensaje(
                "🔭 No tenés turnos para cancelar.\n\n"
                "Escribí *menu* para volver.",
                numero
            )
            return
        
        with user_states_lock:
            user_states[numero_limpio]["turnos"] = turnos
            user_states[numero_limpio]["paso"] = "seleccionar_turno_cancelar"
        
        lista = []
        for i, turno in enumerate(turnos):
            fecha = turno["inicio"].strftime("%d/%m/%Y")
            hora = turno["inicio"].strftime("%H:%M")
            lista.append(formatear_item_lista(i, f"{fecha} a las {hora}\n   {turno['resumen']}"))
        
        mensaje = (
            "❌ *Selecciona el turno a cancelar:*\n\n" + 
            "\n\n".join(lista) + 
            "\n\n0️⃣ Volver al menú"
        )
        enviar_mensaje(mensaje, numero)
        
    except Exception as e:
        print(f"❌ Error en procesar_cancelar_turno_inicio: {e}")
        import traceback
        traceback.print_exc()
        enviar_mensaje(
            "❌ Hubo un error al buscar tus turnos.\n\n"
            "Por favor intentá de nuevo escribiendo *menu*",
            numero
        )

def procesar_seleccion_turno_cancelar(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selección del turno a cancelar"""
    try:
        config = PELUQUERIAS.get(peluqueria_key, {})
        print(f"🔍 [{config.get('nombre', peluqueria_key)}] Usuario {numero_limpio} cancelando turno")
        
        if texto == "0":
            print(f"   ↳ Cancelación abortada")
            with user_states_lock:
                user_states[numero_limpio]["paso"] = "menu"
            enviar_mensaje("✅ Cancelación abortada. Escribí *menu* para volver.", numero)
            return
        
        # Intentar convertir a número
        try:
            index = int(texto) - 1
            print(f"   ↳ Seleccionó turno #{index + 1}")
        except ValueError:
            print(f"   ↳ Entrada inválida: '{texto}'")
            enviar_mensaje("❌ Debe ser un número. Elegí uno de la lista o 0 para volver.", numero)
            return
        
        # Obtener turnos del estado
        with user_states_lock:
            turnos = user_states[numero_limpio].get("turnos", [])
        
        # Verificar que el índice sea válido
        if index < 0 or index >= len(turnos):
            print(f"   ↳ Índice fuera de rango: {index}")
            enviar_mensaje("❌ Número inválido. Elegí uno de la lista.", numero)
            return
        
        turno_seleccionado = turnos[index]
        
        # Guardar el turno a cancelar y cambiar estado
        with user_states_lock:
            user_states[numero_limpio]["turno_a_cancelar"] = turno_seleccionado
            user_states[numero_limpio]["paso"] = "confirmar_cancelacion"
        
        # Formatear la información del turno
        try:
            fecha = turno_seleccionado["inicio"].strftime("%d/%m/%Y")
            hora = turno_seleccionado["inicio"].strftime("%H:%M")
            resumen = turno_seleccionado.get("resumen", "Turno")
            print(f"   ↳ Pidiendo confirmación para: {fecha} {hora}")
        except Exception as e:
            print(f"❌ Error formateando fecha del turno: {e}")
            enviar_mensaje(
                "❌ Error al procesar el turno.\n\n"
                "Escribí *menu* para volver.",
                numero
            )
            return
        
        # Enviar confirmación
        enviar_mensaje(
            f"⚠️ ¿Estás seguro de cancelar el turno?\n\n"
            f"📅 {fecha} a las {hora}\n"
            f"✂️ {resumen}\n\n"
            f"Escribí *SI* para confirmar o *NO* para cancelar",
            numero
        )
        
    except Exception as e:
        print(f"❌ ERROR en procesar_seleccion_turno_cancelar [{peluqueria_key}]: {e}")
        import traceback
        traceback.print_exc()
        
        enviar_mensaje(
            "❌ Ocurrió un error al procesar tu solicitud.\n\n"
            "Por favor escribí *menu* para reintentar.",
            numero
        )
        
        # Resetear estado
        with user_states_lock:
            user_states[numero_limpio]["paso"] = "menu"


def procesar_confirmacion_cancelacion(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la confirmación de cancelación"""
    try:
        if texto in ["si", "sí", "s"]:
            with user_states_lock:
                turno = user_states[numero_limpio].get("turno_a_cancelar")
            
            if not turno:
                enviar_mensaje(
                    "❌ No se encontró el turno a cancelar.\n\n"
                    "Escribí *menu* para volver.",
                    numero
                )
                with user_states_lock:
                    user_states[numero_limpio]["paso"] = "menu"
                return
            
            print(f"🗑️ Cancelando turno ID: {turno['id']}")
            
            # ✅ UNA SOLA VEZ: Intentar cancelar el turno
            if cancelar_turno(peluqueria_key, turno["id"]):
                print(f"✅ Turno cancelado exitosamente en Calendar")
                
                try:
                    fecha = turno["inicio"].strftime("%d/%m/%Y")
                    hora = turno["inicio"].strftime("%H:%M")
                    resumen = turno.get("resumen", "")
                    
                    # Extraer info del resumen
                    partes = resumen.split(" - ")
                    nombre_cliente = partes[-1] if len(partes) >= 3 else "Cliente"
                    servicio = partes[-2] if len(partes) >= 3 else partes[0] if partes else "Servicio"
                    
                    # ✅ Confirmar al cliente
                    enviar_mensaje(
                        f"✅ Turno cancelado exitosamente\n\n"
                        f"📅 {fecha} a las {hora}\n\n"
                        f"¡Esperamos verte pronto! 💈",
                        numero
                    )
                    
                    # ✅ Notificar al peluquero
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
                        print(f"📱 Notificando cancelación a {nombre_peluquero}")
                        
                        # Usar mensaje normal para cancelación
                        mensaje_cancelacion = (
                            f"❌ *Turno cancelado*\n\n"
                            f"👤 Cliente: {nombre_cliente}\n"
                            f"📆 Fecha: {fecha}\n"
                            f"⏰ Hora: {hora}\n"
                            f"✂️ Servicio: {servicio}\n\n"
                            f"📍 {config['nombre']}"
                        )
                        
                        if enviar_mensaje(mensaje_cancelacion, telefono_peluquero):
                            print(f"✅ Notificación de cancelación enviada a {nombre_peluquero}")
                        else:
                            print(f"⚠️ No se pudo notificar a {nombre_peluquero}")
                    
                except Exception as e:
                    print(f"⚠️ Error en notificaciones: {e}")
                    # Aún así confirmar al cliente
                    enviar_mensaje(
                        "✅ Turno cancelado exitosamente\n\n"
                        "¡Esperamos verte pronto! 💈",
                        numero
                    )
            else:
                # ❌ Error al cancelar
                print(f"❌ Error cancelando turno en Google Calendar")
                enviar_mensaje(
                    "❌ Hubo un error al cancelar el turno.\n\n"
                    "Por favor intentá más tarde o contacta al negocio.",
                    numero
                )
            
            # Resetear estado
            with user_states_lock:
                user_states[numero_limpio]["paso"] = "menu"
            
        elif texto in ["no", "n"]:
            enviar_mensaje(
                "✅ Cancelación abortada. Tu turno sigue reservado.\n\n"
                "Escribí *menu* para volver.",
                numero
            )
            with user_states_lock:
                user_states[numero_limpio]["paso"] = "menu"
        else:
            enviar_mensaje("⚠️ Respondé *SI* o *NO*", numero)
            
    except Exception as e:
        print(f"❌ ERROR en procesar_confirmacion_cancelacion: {e}")
        import traceback
        traceback.print_exc()
        
        enviar_mensaje(
            "❌ Ocurrió un error.\n\n"
            "Escribí *menu* para volver.",
            numero
        )
        
        with user_states_lock:
            user_states[numero_limpio]["paso"] = "menu"


# ==================== OPCIÓN 4: SERVICIOS ====================

def procesar_servicios(config, numero):
    """Muestra los servicios disponibles"""
    servicios = config.get("servicios", [])
    
    if not servicios:
        enviar_mensaje(
            "✂️ *Nuestros servicios:*\n\n"
            "Contactanos para conocer nuestros servicios.\n\n"
            "Escribí *menu* para volver",
            numero
        )
    else:
        lista_servicios = []
        for servicio in servicios:
            nombre = servicio["nombre"]
            precio = f"${servicio['precio']:,}".replace(',', '.')
            duracion = servicio["duracion"]
            lista_servicios.append(f"• {nombre} - {precio} ({duracion} min)")
        
        mensaje = (
            f"✂️ *Servicios de {config['nombre']}:*\n\n" +
            "\n".join(lista_servicios) +
            "\n\nEscribí *menu* para volver"
        )
        enviar_mensaje(mensaje, numero)


# ==================== OPCIÓN 5: REAGENDAR ====================

def procesar_reagendar_inicio(numero_limpio, peluqueria_key, numero):
    """Inicia el flujo de reagendar turno"""
    turnos = obtener_turnos_cliente(peluqueria_key, numero_limpio)
    
    if not turnos:
        enviar_mensaje("🔭 No tenés turnos para reagendar.\n\nEscribí *menu* para volver.", numero)
    else:
        with user_states_lock:
            user_states[numero_limpio]["turnos"] = turnos
            user_states[numero_limpio]["paso"] = "seleccionar_turno_reagendar"
        
        lista = []
        for i, turno in enumerate(turnos):
            fecha = formatear_fecha_espanol(turno["inicio"])
            hora = turno["inicio"].strftime("%H:%M")
            lista.append(f"{i+1}️⃣ {fecha} a las {hora}")
        
        mensaje = "🔄 *Selecciona el turno a reagendar:*\n\n" + "\n".join(lista)
        enviar_mensaje(mensaje, numero)


def procesar_seleccion_turno_reagendar(numero_limpio, texto, numero):
    """Procesa la selección del turno a reagendar"""
    try:
        opcion = int(texto) - 1
        
        with user_states_lock:
            turnos = user_states[numero_limpio].get("turnos", [])

            if opcion < 0 or opcion >= len(turnos):
                enviar_mensaje("❌ Opción inválida. Elegí un número de la lista.", numero)
                return

            turno_seleccionado = turnos[opcion]
            user_states[numero_limpio]["turno_a_reagendar"] = turno_seleccionado
            user_states[numero_limpio]["paso"] = "menu"

        enviar_mensaje(
            "ℹ️ Para reagendar:\n\n"
            "1️⃣ Primero cancelá tu turno actual (opción 3)\n"
            "2️⃣ Luego pedí uno nuevo (opción 1)\n\n"
            "Escribí *menu* para volver",
            numero
        )

    except ValueError:
        enviar_mensaje("❌ Enviá solo el número del turno.", numero)


# ==================== OPCIÓN 6: FAQ ====================

def procesar_faq(numero):
    """Muestra preguntas frecuentes"""
    mensaje = """📖 *Preguntas Frecuentes:*

*¿Puedo cambiar la hora?*
Cancelá el turno actual y reservá uno nuevo

*¿Con cuánto tiempo de anticipación debo reservar?*
Podés reservar hasta con 7 días de anticipación

*¿Qué pasa si llego tarde?*
Intentá llegar 5 min antes. Si llegás más de 15 min tarde, tu turno podría ser reasignado

*¿Formas de pago?*
Efectivo, débito y crédito

Escribí *menu* para volver"""
    
    enviar_mensaje(mensaje, numero)


# ==================== OPCIÓN 7: UBICACIÓN ====================

def procesar_ubicacion(config, numero):
    """Muestra ubicación y contacto"""
    mensaje = f"""📍 *Ubicación de {config['nombre']}:*

Dirección: Calle Ejemplo 123, Buenos Aires

🕒 *Horarios:*
Lunes a Viernes: 08:00 - 20:00
Sábados: 08:00 - 19:00
Domingos: Cerrado

📞 *Contacto:*
Teléfono: +54 9 11 1234-5678

Escribí *menu* para volver"""
    
    enviar_mensaje(mensaje, numero)

# ==================== OPCIÓN SELECCIÓN DE PELUQUEROS ====================

def procesar_seleccion_peluquero(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selección del peluquero - Valida que esté activo"""
    try:
        # Obtener lista de peluqueros activos del estado del usuario
        with user_states_lock:
            peluqueros = user_states[numero_limpio].get("peluqueros_disponibles", [])
        
        # Si no existe la lista filtrada, obtener de config (fallback)
        if not peluqueros:
            config = PELUQUERIAS.get(peluqueria_key, {})
            peluqueros = [p for p in config.get("peluqueros", []) if p.get("activo", True)]
        
        index = int(texto) - 1
        
        if 0 <= index < len(peluqueros):
            peluquero_seleccionado = peluqueros[index]
            
            # Verificar que esté activo
            if not peluquero_seleccionado.get("activo", True):
                enviar_mensaje(
                    f"😕 {peluquero_seleccionado['nombre']} no está disponible en este momento.\n\n"
                    "Escribí *menu* para elegir otro peluquero.",
                    numero
                )
                with user_states_lock:
                    user_states[numero_limpio]["paso"] = "menu"
                return
            
            # ✅ CRÍTICO: Guardar peluquero ANTES de generar los días
            with user_states_lock:
                user_states[numero_limpio]["peluquero"] = peluquero_seleccionado
            
            print(f"✅ Peluquero guardado: {peluquero_seleccionado['nombre']}")
            
            # Ahora generar días disponibles para este peluquero
            hoy = datetime.now().date()
            dias = []
            dias_semana_map = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
            
            for i in range(7):
                dia = hoy + timedelta(days=i)
                dia_nombre = dias_semana_map[dia.weekday()]
                
                # Verificar si el peluquero trabaja ese día
                if dia_nombre in peluquero_seleccionado.get("dias_trabajo", []):
                    dias.append(dia)
            
            if not dias:
                enviar_mensaje(
                    f"😕 {peluquero_seleccionado['nombre']} no tiene días disponibles esta semana.\n\n"
                    "Escribí *menu* para elegir otro peluquero.",
                    numero
                )
                with user_states_lock:
                    user_states[numero_limpio]["paso"] = "menu"
                return
            
            # ✅ Guardar días Y cambiar paso JUNTOS
            with user_states_lock:
                user_states[numero_limpio]["dias"] = dias
                user_states[numero_limpio]["paso"] = "seleccionar_dia"
            
            print(f"✅ Estado cambiado a: seleccionar_dia con {len(dias)} días disponibles")
            
            # Mostrar días
            dias_espanol = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
            lista = "\n".join(
                formatear_item_lista(i, f"{dias_espanol[d.weekday()]} {d.strftime('%d/%m')}")
                for i, d in enumerate(dias)
            )
            
            enviar_mensaje(
                f"📅 Días disponibles de *{peluquero_seleccionado['nombre']}*:\n\n{lista}\n\nElegí un número:",
                numero
            )
        else:
            enviar_mensaje("❌ Número inválido. Elegí uno de la lista.", numero)
    
    except ValueError:
        enviar_mensaje("❌ Debe ser un número.", numero)
    except Exception as e:
        print(f"❌ Error en procesar_seleccion_peluquero: {e}")
        import traceback
        traceback.print_exc()
        enviar_mensaje(
            "❌ Ocurrió un error. Escribí *menu* para reintentar.",
            numero
        )
        with user_states_lock:
            user_states[numero_limpio]["paso"] = "menu"


# ==================== OPCIÓN 0: SALIR ====================

def procesar_salir(config, numero_limpio, numero):
    """Procesa la salida del menú"""
    enviar_mensaje(
        f"👋 ¡Gracias por contactarnos!\n\n"
        f"Cuando quieras volver, escribí *hola* o *menu*\n\n"
        f"*{config['nombre']}* 💈",
        numero
    )
    
    with user_states_lock:
        user_states[numero_limpio]["paso"] = "finalizado"


# ==================== INICIO DEL SERVIDOR ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 BOT DE PELUQUERÍA MULTI-CLIENTE")
    print("=" * 50)
    print(f"✅ Clientes cargados: {len(PELUQUERIAS)}")
    for key, config in PELUQUERIAS.items():
        print(f"   • {config['nombre']} ({key})")
    print("=" * 50)
    
    # Iniciar recordatorios solo en producción
    if not MODO_DESARROLLO:
        hilo_recordatorios = threading.Thread(target=sistema_recordatorios, daemon=True)
        hilo_recordatorios.start()
        print("✅ Sistema de recordatorios activado")
    else:
        print("🧪 Recordatorios desactivados en desarrollo")
    print("✅ Sistema de recordatorios activado")
    
    # Puerto dinámico para deployment
    port = int(os.environ.get("PORT", 3000))
    print(f"🚀 Servidor iniciando en puerto {port}")
    print("=" * 50)
    
    # Debug según modo
    app.run(host="0.0.0.0", port=port, debug=MODO_DESARROLLO)

