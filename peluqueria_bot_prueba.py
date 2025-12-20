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

#----------------------------------------------------------------
app = Flask(__name__)


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
            descripcion = event.get("description", "")
            summary = event.get("summary", "Sin título")
            
            # Limpiar la descripción
            descripcion_limpia = descripcion.replace('+', '').replace(' ', '').replace('-', '').replace('Tel:', '').replace('\n', '').replace('\r', '')
            
            # Búsqueda flexible
            if telefono_busqueda in descripcion_limpia:
                try:
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
                    print(f"❌ Error procesando evento: {e}")
                    continue
    
    return turnos_cliente

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

def crear_reserva_en_calendar(peluqueria_key, fecha_hora, cliente, servicio, telefono):
    """Crea un evento en Google Calendar al confirmar turno"""
    try:
        if peluqueria_key not in PELUQUERIAS:
            return False
            
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)

        if not service:
            return False

        evento = {
            'summary': f"Turno - {servicio} - {cliente}",
            'start': {
                'dateTime': fecha_hora.isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            },
            'end': {
                'dateTime': (fecha_hora + timedelta(minutes=30)).isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            },
            'description': f"Cliente: {cliente}\nTel: {telefono}"
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
    """Envía un recordatorio de turno al cliente"""
    try:
        # Verificar si el usuario tiene recordatorios activos
        with user_states_lock:
            if turno["telefono"] in user_states:
                if not user_states[turno["telefono"]].get("recordatorios_activos", True):
                    print(f"⏭️ Usuario {turno['telefono']} tiene recordatorios desactivados")
                    return
        
        # Obtener nombre de la peluquería
        peluqueria_nombre = PELUQUERIAS.get(turno.get("peluqueria", "cliente_001"), {}).get("nombre", "Peluquería")
        
        fecha = turno["inicio"].strftime("%d/%m/%Y")
        hora = turno["inicio"].strftime("%H:%M")
        
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        diferencia = turno["inicio"] - ahora
        horas_faltantes = int(diferencia.total_seconds() / 3600)
        
        if horas_faltantes >= 20:  # Recordatorio de 24 horas
            mensaje = (
                f"🔔 *Recordatorio de turno*\n\n"
                f"¡Hola! Te recordamos que tenés turno mañana:\n\n"
                f"📅 Fecha: {fecha}\n"
                f"🕒 Hora: {hora}\n"
                f"✂️ {turno['resumen']}\n"
                f"📍 {peluqueria_nombre}\n\n"
                f"¡Te esperamos! 💈\n\n"
                f"_Si necesitás cancelar, escribí *menu* y elegí la opción 3_"
            )
        elif horas_faltantes >= 1 and horas_faltantes < 3:  # Recordatorio de 2 horas
            mensaje = (
                f"⏰ *Recordatorio urgente*\n\n"
                f"Tu turno es en {horas_faltantes} horas:\n\n"
                f"🕒 Hora: {hora}\n"
                f"📍 {peluqueria_nombre}\n\n"
                f"¡Nos vemos pronto! 💈"
            )
        else:
            return
        
        enviar_mensaje(mensaje, turno["telefono"])
        print(f"✅ Recordatorio enviado a {turno['telefono']} para turno de {hora}")
        
    except Exception as e:
        print(f"❌ Error enviando recordatorio: {e}")

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
        
        # ✅ VALIDACIÓN CRÍTICA: Si no se encuentra el cliente, no continuar
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
        
        # Inicializar estado si es nuevo usuario
        with user_states_lock:
            if numero_limpio not in user_states:
                user_states[numero_limpio] = {
                    "paso": "menu",
                    "peluqueria": peluqueria_key
                }
            # Actualizar la peluquería por si cambió
            else:
                user_states[numero_limpio]["peluqueria"] = peluqueria_key
        
        # Comandos globales - MENÚ
        if texto in ["menu", "menú", "inicio", "hola", "hi", "hey"]:
            with user_states_lock:
                user_states[numero_limpio] = {
                    "paso": "menu",
                    "peluqueria": peluqueria_key
                }
            enviar_mensaje(obtener_menu_principal(peluqueria_key), numero)
            return "", 200
        
        # Obtener estado actual
        with user_states_lock:
            estado = user_states[numero_limpio].get("paso", "menu")
        
        # Comando para cancelar operación actual
        if texto in ["cancelar", "salir", "abortar", "stop"]:
            if estado != "menu":
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
            enviar_mensaje("❓ No entendí. Escribí *menu* para ver las opciones.", numero)
    
    # FLUJO PEDIR TURNO
    elif estado == "seleccionar_dia":
        procesar_seleccion_dia(numero_limpio, texto, peluqueria_key, numero)
    elif estado == "seleccionar_horario":
        procesar_seleccion_horario(numero_limpio, texto, numero)
    elif estado == "nombre":
        procesar_nombre_cliente(numero_limpio, texto, peluqueria_key, numero)
    elif estado == "servicio":
        procesar_seleccion_servicio(numero_limpio, texto, peluqueria_key, numero)
    
    # FLUJO CANCELAR TURNO
    elif estado == "seleccionar_turno_cancelar":
        procesar_seleccion_turno_cancelar(numero_limpio, texto, peluqueria_key, numero)
    elif estado == "confirmar_cancelacion":
        procesar_confirmacion_cancelacion(numero_limpio, texto, peluqueria_key, numero)
    
    # FLUJO REAGENDAR
    elif estado == "seleccionar_turno_reagendar":
        procesar_seleccion_turno_reagendar(numero_limpio, texto, numero)
    
    else:
        enviar_mensaje("❓ No entendí. Escribí *menu* para volver al menú.", numero)


# ==================== OPCIÓN 1: PEDIR TURNO ====================

def procesar_pedir_turno_inicio(numero_limpio, peluqueria_key, numero):
    """Inicia el flujo de pedir turno"""
    hoy = datetime.now().date()
    dias = []

    for i in range(7):
        dia = hoy + timedelta(days=i)
        if dia.weekday() != 6:  # excluir domingos
            dias.append(dia)

    with user_states_lock:
        user_states[numero_limpio]["dias"] = dias
        user_states[numero_limpio]["paso"] = "seleccionar_dia"

    dias_espanol = {
        0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 
        4: 'Vie', 5: 'Sáb', 6: 'Dom'
    }
    
    lista = "\n".join(
        f"{i+1}️⃣ {dias_espanol[d.weekday()]} {d.strftime('%d/%m')}"
        for i, d in enumerate(dias)
    )
    
    enviar_mensaje(
        "📅 Elegí el día para tu turno:\n\n" + lista,
        numero
    )


def procesar_seleccion_dia(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selección del día"""
    try:
        index = int(texto) - 1
        
        with user_states_lock:
            dias = user_states[numero_limpio].get("dias", [])

        if 0 <= index < len(dias):
            dia_elegido = dias[index]
            
            horarios = obtener_horarios_disponibles(peluqueria_key, dia_elegido)

            if not horarios:
                enviar_mensaje("Ese día no tiene horarios disponibles 😕\n\nEscribí *menu* para volver.", numero)
                return

            with user_states_lock:
                user_states[numero_limpio]["dia"] = dia_elegido
                user_states[numero_limpio]["horarios"] = horarios
                user_states[numero_limpio]["paso"] = "seleccionar_horario"

            lista = "\n".join(
                f"{i+1}️⃣ {h.strftime('%H:%M')}"
                for i, h in enumerate(horarios)
            )

            enviar_mensaje(
                f"🕒 Horarios disponibles:\n\n{lista}\n\nElegí un número",
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
    
    config = PELUQUERIAS[peluqueria_key]
    servicios = config.get("servicios", [])
    
    if servicios:
        lista = []
        for i, servicio in enumerate(servicios):
            precio_formateado = f"${servicio['precio']:,}".replace(',', '.')
            lista.append(f"{i+1}️⃣ {servicio['nombre']} - {precio_formateado}")
        
        mensaje = (
            "📋 *¿Qué servicio querés?*\n\n" +
            "\n".join(lista) +
            "\n\nElegí un número o escribe el nombre del servicio:"
        )
        enviar_mensaje(mensaje, numero)
    else:
        enviar_mensaje("📋 ¿Qué servicio querés?\nEj: Corte, Tintura, Barba", numero)


def procesar_seleccion_servicio(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la selección del servicio y crea la reserva"""
    config = PELUQUERIAS[peluqueria_key]
    servicios = config.get("servicios", [])
    servicio_seleccionado = None
    
    # Intentar parsear como número
    try:
        index = int(texto) - 1
        if 0 <= index < len(servicios):
            servicio_seleccionado = servicios[index]["nombre"]
    except ValueError:
        # Si no es número, usar el texto que escribió
        servicio_seleccionado = texto.title()
    
    with user_states_lock:
        fecha_hora = user_states[numero_limpio]["fecha_hora"]
        cliente = user_states[numero_limpio]["cliente"]
    
    telefono = numero_limpio

    # Crear reserva en Google Calendar
    if crear_reserva_en_calendar(peluqueria_key, fecha_hora, cliente, servicio_seleccionado, telefono):
        fecha_formateada = formatear_fecha_completa(fecha_hora)
        
        enviar_mensaje(
            f"✅ ¡Listo {cliente}! Turno reservado:\n\n"
            f"📅 {fecha_formateada}\n"
            f"✂️ Servicio: {servicio_seleccionado}\n"
            f"📍 {config['nombre']}\n\n"
            f"¡Te esperamos! 💈\n\n"
            f"Recibirás recordatorios automáticos.",
            numero
        )
    else:
        enviar_mensaje(
            "❌ Hubo un error al crear la reserva. Por favor intentá de nuevo.\n\n"
            "Escribí *menu* para volver.",
            numero
        )

    with user_states_lock:
        user_states[numero_limpio]["paso"] = "menu"


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
    turnos = obtener_turnos_cliente(peluqueria_key, numero_limpio)
    
    if not turnos:
        enviar_mensaje("🔭 No tenés turnos para cancelar.\n\nEscribí *menu* para volver.", numero)
    else:
        with user_states_lock:
            user_states[numero_limpio]["turnos"] = turnos
            user_states[numero_limpio]["paso"] = "seleccionar_turno_cancelar"
        
        lista = []
        for i, turno in enumerate(turnos):
            fecha = turno["inicio"].strftime("%d/%m/%Y")
            hora = turno["inicio"].strftime("%H:%M")
            lista.append(f"{i+1}️⃣ {fecha} a las {hora}")
        
        mensaje = "❌ *Selecciona el turno a cancelar:*\n\n" + "\n".join(lista) + "\n\n0️⃣ Volver al menú"
        enviar_mensaje(mensaje, numero)


def procesar_seleccion_turno_cancelar(numero_limpio, texto, numero):
    """Procesa la selección del turno a cancelar"""
    if texto == "0":
        with user_states_lock:
            user_states[numero_limpio]["paso"] = "menu"
        enviar_mensaje("✅ Cancelación abortada. Escribí *menu* para volver.", numero)
    else:
        try:
            index = int(texto) - 1
            
            with user_states_lock:
                turnos = user_states[numero_limpio].get("turnos", [])
                
                if 0 <= index < len(turnos):
                    turno_seleccionado = turnos[index]
                    user_states[numero_limpio]["turno_a_cancelar"] = turno_seleccionado
                    user_states[numero_limpio]["paso"] = "confirmar_cancelacion"
                    
                    fecha = turno_seleccionado["inicio"].strftime("%d/%m/%Y")
                    hora = turno_seleccionado["inicio"].strftime("%H:%M")
                    
                    enviar_mensaje(
                        f"⚠️ ¿Estás seguro de cancelar el turno?\n\n"
                        f"📅 {fecha} a las {hora}\n"
                        f"✂️ {turno_seleccionado['resumen']}\n\n"
                        f"Escribí *SI* para confirmar o *NO* para cancelar",
                        numero
                    )
                else:
                    enviar_mensaje("❌ Número inválido. Elegí uno de la lista.", numero)
        except ValueError:
            enviar_mensaje("❌ Debe ser un número.", numero)


def procesar_confirmacion_cancelacion(numero_limpio, texto, peluqueria_key, numero):
    """Procesa la confirmación de cancelación"""
    if texto in ["si", "sí"]:
        with user_states_lock:
            turno = user_states[numero_limpio].get("turno_a_cancelar")
        
        if turno and cancelar_turno(peluqueria_key, turno["id"]):
            fecha = turno["inicio"].strftime("%d/%m/%Y")
            hora = turno["inicio"].strftime("%H:%M")
            
            enviar_mensaje(
                f"✅ Turno cancelado exitosamente\n\n"
                f"📅 {fecha} a las {hora}\n\n"
                f"¡Esperamos verte pronto! 💈",
                numero
            )
        else:
            enviar_mensaje("❌ Hubo un error al cancelar. Intentá más tarde.", numero)
        
        with user_states_lock:
            user_states[numero_limpio]["paso"] = "menu"
        
    elif texto == "no":
        enviar_mensaje("✅ Cancelación abortada. Tu turno sigue reservado.\n\nEscribí *menu* para volver.", numero)
        with user_states_lock:
            user_states[numero_limpio]["paso"] = "menu"
    else:
        enviar_mensaje("⚠️ Respondé *SI* o *NO*", numero)


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
    
    # Iniciar sistema de recordatorios en segundo plano
    hilo_recordatorios = threading.Thread(target=sistema_recordatorios, daemon=True)
    hilo_recordatorios.start()
    print("✅ Sistema de recordatorios activado")
    
    # Puerto dinámico para deployment
    port = int(os.environ.get("PORT", 3000))
    print(f"🚀 Servidor iniciando en puerto {port}")
    print("=" * 50)
    
    # En producción, usar debug=False
    app.run(host="0.0.0.0", port=port, debug=False)

