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

def formatear_fecha_espanol(fecha):
    """
    Formatea fecha en español
    """
    dias = {
        'Monday': 'Lunes',
        'Tuesday': 'Martes',
        'Wednesday': 'Miércoles',
        'Thursday': 'Jueves',
        'Friday': 'Viernes',
        'Saturday': 'Sábado',
        'Sunday': 'Domingo'
    }
    
    meses = {
        'January': 'Enero',
        'February': 'Febrero',
        'March': 'Marzo',
        'April': 'Abril',
        'May': 'Mayo',
        'June': 'Junio',
        'July': 'Julio',
        'August': 'Agosto',
        'September': 'Septiembre',
        'October': 'Octubre',
        'November': 'Noviembre',
        'December': 'Diciembre'
    }
    
    # Formato: "Lunes 16/12/2024"
    dia_semana = fecha.strftime('%A')
    dia_semana_es = dias.get(dia_semana, dia_semana)
    
    fecha_str = fecha.strftime('%d/%m/%Y')
    
    return f"{dia_semana_es} {fecha_str}"

def formatear_fecha_completa(fecha):
    """
    Formato más completo: "Lunes 16 de Diciembre, 15:00"
    """
    dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
             'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    dia_semana = dias[fecha.weekday()]
    mes = meses[fecha.month - 1]
    
    return f"{dia_semana} {fecha.day} de {mes}, {fecha.strftime('%H:%M')}"

#----------------------------------------------------------------
app = Flask(__name__)


# ------------------- CONFIGURACIÓN DE META ---------------------


load_dotenv()  # Carga variables de .env

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")



# Inicializar cliente de Twilio
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
# ------------------------------------------------------------------------
SCOPES = ['https://www.googleapis.com/auth/calendar']
# Leer carpeta clientes.json
with open("clientes.json", "r", encoding="utf-8") as f:
    PELUQUERIAS = json.load(f)
# Crear carpeta tokens si no existe
if not os.path.exists('tokens'):
    os.makedirs('tokens')

# ------------------- ARCHIVOS GLOBALES RECORDATORIOS ---------------------
ARCHIVO_RECORDATORIOS = "recordatorios_enviados.json"
ARCHIVO_ESTADOS = "user_states.json"
recordatorios_enviados = {}  # Cambiado a dict para almacenar timestamps
# Cache para services de Google Calendar
services_cache = {}
#-------------------------------------------------------------------------
import base64


def restaurar_token_google_master():
    token_b64 = os.getenv("GOOGLE_TOKEN_MASTER")
    if not token_b64:
        print("❌ GOOGLE_TOKEN_MASTER no configurado")
        return

    os.makedirs("tokens", exist_ok=True)
    token_path = "tokens/master_token.json"
    print("GOOGLE_TOKEN_MASTER =", os.getenv("GOOGLE_TOKEN_MASTER"))


    if not os.path.exists(token_path):
        with open(token_path, "wb") as f:
            f.write(base64.b64decode(token_b64))
        print("✅ Token Google master restaurado")

restaurar_token_google_master()

# ------------------- CONFIGURACIÓN GOOGLE CALENDAR ---------------------


def get_calendar_service(peluqueria_key):
    """Conecta con Google Calendar para una peluquería específica"""
    try:
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

    except KeyError:
        print(f"❌ Peluquería no encontrada: {peluqueria_key}")
        return None

        
    except Exception as e:
        print(f"❌ Error conectando Google Calendar para {peluqueria_key}: {e}")
        return None

def get_calendar_config(peluqueria_key):
    """Obtiene el calendar_id de una peluquería"""
    return PELUQUERIAS[peluqueria_key]["calendar_id"]

def esta_ocupado(horario, ocupados):
    """Verifica si un horario está ocupado con 1 minuto de tolerancia"""
    for ocupado in ocupados:
        if abs((horario - ocupado).total_seconds()) < 60:
            return True
    return False

# Para que cada peluquería tenga horarios diferentes:

def obtener_horarios_disponibles(peluqueria_key, dia_seleccionado=None):
    """Genera turnos y revisa eventos ocupados en Google Calendar"""
    try:
        print(f"🔍 DEBUG: Obteniendo horarios para {peluqueria_key}")
        print(f"🔍 DEBUG: Día seleccionado: {dia_seleccionado}")
        
        service = get_calendar_service(peluqueria_key)
        print(f"🔍 DEBUG: Service obtenido: {service is not None}")
        
        calendar_id = get_calendar_config(peluqueria_key)
        print(f"🔍 DEBUG: Calendar ID: {calendar_id}")
        
        if not service:
            print("❌ DEBUG: Service es None, retornando []")
            return []

        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        
        if dia_seleccionado is None:
            dia_seleccionado = ahora.date()

        # Si el día es domingo, retornar vacío
        if dia_seleccionado.weekday() == 6:
            return []

        # ✅ OBTENER HORARIOS DE LA CONFIGURACIÓN
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

        # Resto del código igual...
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
    service = get_calendar_service(peluqueria_key)
    calendar_id = get_calendar_config(peluqueria_key)

    if not service:
        print("❌ No se pudo obtener el servicio de Calendar")
        return []

    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    ahora = datetime.now(tz)
    
    print(f"📅 Peluquería: {peluqueria_key}")
    print(f"📅 Calendar ID: {calendar_id}")
    print(f"📅 Buscando desde: {ahora.isoformat()}")
    print(f"📅 Hasta: {(ahora + timedelta(days=30)).isoformat()}")
    
    try:
        eventos = service.events().list(
            calendarId=calendar_id,
            timeMin=ahora.isoformat(),
            timeMax=(ahora + timedelta(days=30)).isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        print(f"📊 Total de eventos encontrados: {len(eventos.get('items', []))}")
        
    except Exception as e:
        print(f"❌ Error obteniendo eventos: {e}")
        return []
    
    turnos_cliente = []
    
    # Limpiar el teléfono de búsqueda (quitar prefijos y espacios)
    telefono_busqueda = telefono.replace('whatsapp:', '').replace('+', '').replace(' ', '').replace('-', '')
    
    print(f"🔍 Buscando turnos para: {telefono_busqueda}")
    
    if "items" in eventos:
        print(f"📋 Procesando {len(eventos['items'])} eventos...")
        
        for event in eventos["items"]:
            descripcion = event.get("description", "")
            summary = event.get("summary", "Sin título")
            
            # Limpiar la descripción: quitar +, espacios, guiones, "Tel:", saltos de línea
            descripcion_limpia = descripcion.replace('+', '').replace(' ', '').replace('-', '').replace('Tel:', '').replace('\n', '').replace('\r', '')
            
            print(f"\n  📄 Evento: {summary}")
            print(f"     Descripción original: [{descripcion}]")
            print(f"     Descripción limpia: [{descripcion_limpia}]")
            print(f"     Buscando: [{telefono_busqueda}]")
            print(f"     ¿Coincide? {telefono_busqueda in descripcion_limpia}")
            
            # Búsqueda flexible
            if telefono_busqueda in descripcion_limpia:
                try:
                    # Parsear correctamente con timezone
                    inicio_str = event["start"].get("dateTime", event["start"].get("date"))
                    
                    if not inicio_str:
                        print(f"     ⚠️ Evento sin fecha/hora")
                        continue
                    
                    # Si viene con Z (UTC), convertir a Argentina
                    if inicio_str.endswith('Z'):
                        inicio_utc = datetime.fromisoformat(inicio_str.replace("Z", "+00:00"))
                        inicio_arg = inicio_utc.astimezone(tz)
                    else:
                        # Si ya tiene timezone, solo parsearlo
                        inicio_arg = datetime.fromisoformat(inicio_str)
                        if inicio_arg.tzinfo is None:
                            # Si no tiene timezone, asumir Argentina
                            inicio_arg = tz.localize(inicio_arg)
                        else:
                            # Convertir a Argentina
                            inicio_arg = inicio_arg.astimezone(tz)
                    
                    turno_info = {
                        "id": event["id"],
                        "resumen": summary,
                        "inicio": inicio_arg
                    }
                    turnos_cliente.append(turno_info)
                    print(f"     ✅ Turno agregado: {inicio_arg.strftime('%d/%m/%Y %H:%M')}")
                except Exception as e:
                    print(f"     ❌ Error procesando evento: {e}")
                    continue
            else:
                print(f"     ⏭️ No coincide, saltando...")
    else:
        print("⚠️ No hay 'items' en la respuesta de eventos")
    
    print(f"\n📊 Total turnos encontrados: {len(turnos_cliente)}")
    return turnos_cliente

def cancelar_turno(peluqueria_key, event_id):
    try:
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)

        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()
        return True
    except Exception as e:
        print(f"Error cancelando turno: {e}")
        return False


def crear_reserva_en_calendar(peluqueria_key, fecha_hora, cliente, servicio, telefono):
    """Crea un evento en Google Calendar al confirmar turno"""
    service = get_calendar_service(peluqueria_key)

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

    try:
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)

        service.events().insert(
            calendarId=calendar_id,
            body=evento
        ).execute()

        return True

    except Exception as e:
        print(f"Error creando reserva: {e}")
        return False

# ------------------- RECORDATORIOS ---------------------

def cargar_recordatorios_enviados():
    """
    Carga los recordatorios enviados desde el archivo JSON
    Se ejecuta al iniciar el bot
    """    
    if os.path.exists(ARCHIVO_RECORDATORIOS):
        try:
            with open(ARCHIVO_RECORDATORIOS, "r") as f:
                datos = json.load(f) # Lee el archivo JSON
                return set(datos)   # Convierte la lista a set
        except json.JSONDecodeError:
            # Si el archivo está corrupto, lo renombra y empieza de nuevo
            print("⚠️ Archivo corrupto, creando backup...")
            os.rename(ARCHIVO_RECORDATORIOS, f"{ARCHIVO_RECORDATORIOS}.backup")
            return set()
        except Exception as e:
            print(f"⚠️ Error cargando recordatorios: {e}")
            return set() # Si hay error, devuelve set vacío
        
    # Si el archivo no existe, devuelve set vacío
    return set()



def guardar_recordatorios_enviados(recordatorios):
    """
    Guarda los recordatorios enviados en el archivo JSON
    Se ejecuta cada vez que se envía un recordatorio
    """
    try:
        with open(ARCHIVO_RECORDATORIOS, "w") as f:
            json.dump(list(recordatorios), f, indent=2) # Convierte el set a lista para poder guardarlo en JSON
    except PermissionError:
        print("❌ No hay permisos para escribir el archivo")
    except Exception as e:
        print(f"❌ Error guardando recordatorios: {e}")
        # El bot sigue funcionando, solo no guarda en disco

def limpiar_recordatorios_antiguos():
    """
    Elimina recordatorios de turnos que ya pasaron
    """
    global recordatorios_enviados
    
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    ahora = datetime.now(tz)
    
    # Solo mantener recordatorios de los últimos 7 días
    limite = ahora - timedelta(days=7)
    
    # Esta limpieza es más inteligente pero requiere más lógica
    # Por ahora, simplemente limpiamos cuando hay más de 1000
    if len(recordatorios_enviados) > 1000:
        recordatorios_enviados.clear()
        guardar_recordatorios_enviados(recordatorios_enviados)
        print("🧹 Recordatorios antiguos eliminados")

def obtener_turnos_proximos(peluqueria_key, horas_anticipacion=24):
    """
    Obtiene turnos que ocurrirán en X horas
    Por defecto busca turnos en las próximas 24 horas
    """
    try:
        service = get_calendar_service(peluqueria_key)
        calendar_id = get_calendar_config(peluqueria_key)
        if not service:
            return []
        
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        
        # Rango de búsqueda: desde ahora hasta ahora + horas_anticipacion
        tiempo_inicio = ahora + timedelta(hours=horas_anticipacion - 1)  # 23 horas desde ahora
        tiempo_fin = ahora + timedelta(hours=horas_anticipacion + 1)     # 25 horas desde ahora
        
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
                    # Extraer info del turno
                    inicio_str = event["start"]["dateTime"]

                    # Convertir a timezone Argentina
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
                    
                    # Extraer teléfono de la descripción
                    # Formato: "Cliente: Juan\Tel: 5492974924147"
                    telefono = None
                    for linea in descripcion.split("\n"):
                        if "Tel:" in linea:
                            # Extraer solo el número, limpiando espacios
                            telefono = linea.replace("Tel:", "").strip()
                            break
                    
                    if telefono:
                        turno_info = {
                            "telefono": telefono,
                            "inicio": inicio,
                            "resumen": event.get("summary", "Turno"),
                            "id": event["id"]
                        }
                        turnos_recordar.append(turno_info)
                        
                except Exception as e:
                    print(f"Error procesando evento para recordatorio: {e}")
                    continue
        
        return turnos_recordar
    
    except Exception as e:
        print(f"❌ Error obteniendo turnos próximos: {e}")
        return []


def enviar_recordatorio(turno):
    # Verificar si el usuario tiene recordatorios activos
    if turno["telefono"] in user_states:
        if not user_states[turno["telefono"]].get("recordatorios_activos", True):
            print(f"⏭️ Usuario {turno['telefono']} tiene recordatorios desactivados")
            return
    

    """Envía un recordatorio de turno al cliente"""
    try:
        fecha = turno["inicio"].strftime("%d/%m/%Y")
        hora = turno["inicio"].strftime("%H:%M")
        
        # Calcular cuánto falta
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        diferencia = turno["inicio"] - ahora
        horas_faltantes = int(diferencia.total_seconds() / 3600)
        
        if horas_faltantes >= 20:  # Recordatorio de 24 horas
            mensaje = (
                f"🔔 *Recordatorio de turno*\n\n"
                f"Hola! Te recordamos que tenés turno mañana:\n\n"
                f"📅 Fecha: {fecha}\n"
                f"🕒 Hora: {hora}\n"
                f"✂️ {turno['resumen']}\n"
                f"📍 Peluquería el Míster\n\n"
                f"¡Te esperamos! 💈\n\n"
                f"_Si necesitás cancelar, escribí *menu* y elegí la opción 3_"
            )
        elif horas_faltantes >= 1 and horas_faltantes < 3:  # Recordatorio de 2 horas
            mensaje = (
                f"⏰ *Recordatorio urgente*\n\n"
                f"Tu turno es en {horas_faltantes} horas:\n\n"
                f"🕒 Hora: {hora}\n"
                f"📍 Peluquería el Míster\n\n"
                f"¡Nos vemos pronto! 💈"
            )
        else:
            return  # No enviar si no es momento
        
        enviar_mensaje(mensaje, turno["telefono"])
        print(f"✅ Recordatorio enviado a {turno['telefono']} para turno de {hora}")
        
    except Exception as e:
        print(f"❌ Error enviando recordatorio: {e}")
        

def sistema_recordatorios():
    global recordatorios_enviados
    
    recordatorios_enviados = cargar_recordatorios_enviados()
    print(f"📂 Cargados {len(recordatorios_enviados)} recordatorios previos")
    print("🔔 Sistema de recordatorios iniciado")
    
    while True:
        try:
            ahora = datetime.now().strftime('%H:%M')
            print(f"\n⏰ [{ahora}] Verificando turnos próximos...")
            
            # ✅ Verificar TODAS las peluquerías
            for peluqueria_key in PELUQUERIAS.keys():
                print(f"   Verificando {PELUQUERIAS[peluqueria_key]['nombre']}...")
                
                # Recordatorios de 24 horas
                turnos_24h = obtener_turnos_proximos(peluqueria_key, horas_anticipacion=24)
                for turno in turnos_24h:
                    recordatorio_id = f"{turno['id']}_24h"
                    
                    if recordatorio_id not in recordatorios_enviados:
                        enviar_recordatorio(turno)
                        recordatorios_enviados.add(recordatorio_id)
                        guardar_recordatorios_enviados(recordatorios_enviados)
                        print(f"   📤 Recordatorio 24h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")
                
                # Recordatorios de 2 horas
                turnos_2h = obtener_turnos_proximos(peluqueria_key, horas_anticipacion=2)
                for turno in turnos_2h:
                    recordatorio_id = f"{turno['id']}_2h"
                    
                    if recordatorio_id not in recordatorios_enviados:
                        enviar_recordatorio(turno)
                        recordatorios_enviados.add(recordatorio_id)
                        guardar_recordatorios_enviados(recordatorios_enviados)
                        print(f"   📤 Recordatorio 2h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")
            
            print("   ✅ Verificación completada. Próxima en 1 hora.")
            
            # Limpiar recordatorios antiguos
            if len(recordatorios_enviados) > 1000:
                recordatorios_enviados.clear()
                guardar_recordatorios_enviados(recordatorios_enviados)
                print("   ✅ Limpieza completada")
            
        except Exception as e:
            print(f"   ❌ Error en sistema de recordatorios: {e}")
        
        time.sleep(3600)
# ------------------- MENSAJERÍA WHATSAPP ---------------------

user_states = {}

def enviar_mensaje(texto, numero):
    """
    Envía mensaje por WhatsApp usando Twilio
    """
    try:
        # Asegurar formato correcto del número
        if not numero.startswith('whatsapp:'):
            numero = f'whatsapp:{numero}'
        
        print(f"\n📤 Intentando enviar mensaje a: {numero}")
        print(f"📝 Contenido: {texto[:50]}...")
        
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
    Detecta qué peluquería según el número de Twilio que recibió el mensaje
    """
    numero = to_number.replace("whatsapp:", "")
    
    # Buscar coincidencia exacta
    if numero in PELUQUERIAS:
        return numero
    
    # Si es sandbox, siempre usa "sandbox"
    if "+14155238886" in numero:
        return "sandbox"
    
    # Por defecto, sandbox
    print(f"⚠️ Número no reconocido: {numero}, usando sandbox")
    return "sandbox"


@app.route("/webhook", methods=["POST"])
def webhook():
    
    peluqueria_key = detectar_peluqueria(request.values.get('To', ''))

    """
    Webhook para recibir mensajes de Twilio WhatsApp
    """
    # Obtener datos del mensaje
    incoming_msg = request.values.get('Body', '').strip().lower()
    numero = request.values.get('From', '')  # Viene como "whatsapp:+5492974924147"
    
    print("--- MENSAJE RECIBIDO ---")
    print(f"De: {numero}")
    print(f"Mensaje: {incoming_msg}")
    
    # Limpiar número (quitar "whatsapp:" si viene)
    numero_limpio = numero.replace('whatsapp:', '')
    texto = incoming_msg  # Renombrar para compatibilidad con el resto del código
    
    # SI ES USUARIO NUEVO → Mostrar menú automáticamente
    if texto in ["menu", "menú", "inicio", "hola", "hi"]:
        user_states[numero_limpio] = {"paso": "menu"}
        enviar_mensaje(
            "👋 ¡Hola! Bienvenido a *Peluquería el Míster* 💈\n\n"
            "Elige una opción:\n"
            "1️⃣ Pedir turno\n"
            "2️⃣ Ver mis turnos\n"
            "3️⃣ Cancelar turno\n"
            "4️⃣ Servicios y precios\n"
            "5️⃣ Reagendar turno\n"
            "6️⃣ Preguntas frecuentes\n"
            "7️⃣ Ubicación y contacto\n"
            "0️⃣ Salir\n\n"
            "Escribí el número de la opción",
            numero
    )
        return "", 200
            

    estado = user_states[numero_limpio]["paso"]

    # ✅ Comando para volver al menú en cualquier momento
    if numero_limpio not in user_states:
        user_states[numero_limpio] = {"paso": "menu"}
        enviar_mensaje(
            "👋 ¡Hola! Bienvenido a *Peluquería el Míster* 💈\n\n"
            "Elige una opción:\n"
            "1️⃣ Pedir turno\n"
            "2️⃣ Ver mis turnos\n"
            "3️⃣ Cancelar turno\n"
            "4️⃣ Servicios y precios\n"
            "5️⃣ Reagendar turno\n"
            "6️⃣ Preguntas frecuentes\n"
            "7️⃣ Ubicación y contacto\n"
            "0️⃣ Salir\n\n"
            "Escribí el número de la opción",
            numero
        )
        return "", 200
    
    # Comando para cancelar operación actual
    if texto in ["cancelar", "salir", "abortar", "stop"]:
        if estado != "menu":
            user_states[numero_limpio]["paso"] = "menu"
            enviar_mensaje(
                "❌ Operación cancelada.\n\n"
                "Volviste al menú principal.\n"
                "Escribí *menu* para ver las opciones.",
                numero
            )
            return "", 200
    

    
    # OPCIÓN 1: 'PEDIR TURNO'
    if estado == "menu" and texto == "1":
        hoy = datetime.now().date()
        dias = []

        for i in range(7):
            dia = hoy + timedelta(days=i)
            if dia.weekday() != 6:  # excluir domingos
                dias.append(dia)

        user_states[numero_limpio]["dias"] = dias
        user_states[numero_limpio]["paso"] = "seleccionar_dia"

        dias_espanol = {
            0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 
            4: 'Vie', 5: 'Sáb', 6: 'Dom'
}
        # Formato en Español
        lista = "\n".join(
            f"{i+1}️⃣ {dias_espanol[d.weekday()]} {d.strftime('%d/%m')}"
            for i, d in enumerate(dias)
)
        enviar_mensaje(
            "📅 Elegí el día para tu turno:\n\n" + lista,
            numero
        )


    elif estado == "seleccionar_dia":
        try:
            index = int(texto) - 1
            dias = user_states[numero_limpio]["dias"]

            if 0 <= index < len(dias):
                dia_elegido = dias[index]
                user_states[numero_limpio]["dia"] = dia_elegido

                horarios = obtener_horarios_disponibles(
                    peluqueria_key,
                    dia_elegido
                )

                if not horarios:
                    enviar_mensaje("Ese día no tiene horarios disponibles 😕", numero)
                    return "", 200

                user_states[numero_limpio]["horarios"] = horarios
                user_states[numero_limpio]["paso"] = "seleccionar_horario"

                lista = "\n".join(
                    f"{i+1}️⃣ {h.strftime('%H:%M')}"
                    for i, h in enumerate(horarios)
                )

                enviar_mensaje(
                    f"Horarios disponibles:\n\n{lista}",
                    numero
                )
            else:
                enviar_mensaje("Número fuera de rango", numero)

        except ValueError:
            enviar_mensaje("Debe ser un número", numero)


    elif estado == "seleccionar_horario":
        try:
            index = int(texto) - 1
            if 0 <= index < len(user_states[numero_limpio]["horarios"]):
                fecha_hora = user_states[numero_limpio]["horarios"][index]
                user_states[numero_limpio]["fecha_hora"] = fecha_hora
                user_states[numero_limpio]["paso"] = "nombre"
                enviar_mensaje("Perfecto ✂️ ¿A nombre de quién tomo el turno?", numero)
            else:
                enviar_mensaje("Número fuera de rango. Elegí uno válido.", numero)
        except ValueError:
            enviar_mensaje("Debe ser un número", numero)

    elif estado == "nombre":
        user_states[numero_limpio]["cliente"] = texto.title()
        user_states[numero_limpio]["paso"] = "servicio"
    
        # Mostrar servicios disponibles
        config = PELUQUERIAS[peluqueria_key]
        servicios = config.get("servicios", [])
    
        if servicios:
            lista = []
            for i, servicio in enumerate(servicios):
                lista.append(f"{i+1}️⃣ {servicio['nombre']} - ${servicio['precio']:,}".replace(',', '.'))
        
            mensaje = (
                "📌 *¿Qué servicio querés?*\n\n" +
                "\n".join(lista) +
                "\n\nElegí un número o escribe el nombre del servicio:"
        )
            enviar_mensaje(mensaje, numero)
        else:
            enviar_mensaje("📌 ¿Qué servicio querés?\nEj: Corte, Tintura, Barba", numero)


    elif estado == "servicio":
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
    
        fecha_hora = user_states[numero_limpio]["fecha_hora"]
        cliente = user_states[numero_limpio]["cliente"]
        telefono = numero_limpio

        crear_reserva_en_calendar(peluqueria_key, fecha_hora, cliente, servicio_seleccionado, telefono)

        enviar_mensaje(
            f"📅 ¡Listo {cliente}! Turno reservado:\n"
            f"🕒 {fecha_hora.strftime('%H:%M')}\n"
            f"✂️ Servicio: {servicio_seleccionado}\n"
            f"📍 {config['nombre']}\n"
            f"¡Te esperamos!",
            numero
        )

        user_states[numero_limpio]["paso"] = "menu"

    # En "Ver mis turnos" (opción 2):
    elif estado == "menu" and texto == "2":
        turnos = obtener_turnos_cliente(peluqueria_key, numero_limpio)
    
        if not turnos:
            enviar_mensaje("📭 No tenés turnos reservados.", numero)
        else:
            lista = []
            for i, turno in enumerate(turnos):
                fecha_formateada = formatear_fecha_espanol(turno["inicio"])  # ✅
                hora = turno["inicio"].strftime("%H:%M")
                lista.append(f"{i+1}. {fecha_formateada} a las {hora}\n   {turno['resumen']}")
        
            mensaje = "📅 *Tus turnos:*\n\n" + "\n\n".join(lista)
            enviar_mensaje(mensaje, numero)
            
    # OPCIÓN 3: 'CANCELAR TURNO'
    elif estado == "menu" and texto == "3":
        turnos = obtener_turnos_cliente(peluqueria_key, numero_limpio)
        
        if not turnos:
            enviar_mensaje("📭 No tenés turnos para cancelar.", numero)
        else:
            user_states[numero_limpio]["turnos"] = turnos
            user_states[numero_limpio]["paso"] = "seleccionar_turno_cancelar"
            
            lista = []
            for i, turno in enumerate(turnos):
                fecha = turno["inicio"].strftime("%d/%m/%Y")
                hora = turno["inicio"].strftime("%H:%M")
                lista.append(f"{i+1}️⃣ {fecha} a las {hora}")
            
            mensaje = "❌ *Selecciona el turno a cancelar:*\n\n" + "\n".join(lista) + "\n\n0️⃣ Volver al menú"
            enviar_mensaje(mensaje, numero)

    elif estado == "seleccionar_turno_cancelar":
        if texto == "0":
            user_states[numero_limpio]["paso"] = "menu"
            enviar_mensaje("✅ Cancelación abortada. Escribí *menu* para volver.", numero)
        else:
            try:
                index = int(texto) - 1
                if 0 <= index < len(user_states[numero_limpio]["turnos"]):
                    turno_seleccionado = user_states[numero_limpio]["turnos"][index]
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

    elif estado == "confirmar_cancelacion":
        if texto in ["si", "sí"]:
            turno = user_states[numero_limpio]["turno_a_cancelar"]
            
            if cancelar_turno(peluqueria_key, turno["id"]):
                fecha = turno["inicio"].strftime("%d/%m/%Y")
                hora = turno["inicio"].strftime("%H:%M")
                
                enviar_mensaje(
                    f"✅ Turno cancelado exitosamente\n\n"
                    f"📅 {fecha} a las {hora}\n"
                    f"¡Esperamos verte pronto! 💈",
                    numero
                )
            else:
                enviar_mensaje("❌ Hubo un error al cancelar. Intentá más tarde.", numero)
            
            user_states[numero_limpio]["paso"] = "menu"
            
        elif texto == "no":
            enviar_mensaje("✅ Cancelación abortada. Tu turno sigue reservado.", numero)
            user_states[numero_limpio]["paso"] = "menu"
        else:
            enviar_mensaje("⚠️ Respondé *SI* o *NO*", numero)

    # OPCIÓN 4: 'SERVICIOS'
    elif estado == "menu" and texto == "4":
        config = PELUQUERIAS[peluqueria_key]
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
    
    # OPCIÓN 5: 'REAGENDAR TURNO'
    elif estado == "menu" and texto == "5":
        turnos = obtener_turnos_cliente(peluqueria_key, numero_limpio)
    
        if not turnos:
            enviar_mensaje("📭 No tenés turnos para reagendar.", numero)
        else:
            user_states[numero_limpio]["turnos"] = turnos
            user_states[numero_limpio]["paso"] = "seleccionar_turno_reagendar"
        
            lista = []
            for i, turno in enumerate(turnos):
                fecha = formatear_fecha_espanol(turno["inicio"])
                hora = turno["inicio"].strftime("%H:%M")
                lista.append(f"{i+1}️⃣ {fecha} a las {hora}")
        
            mensaje = "🔄 *Selecciona el turno a reagendar:*\n\n" + "\n".join(lista)
            enviar_mensaje(mensaje, numero)
    elif user_states[numero_limpio]["paso"] == "seleccionar_turno_reagendar":
        try:
            opcion = int(texto) - 1
            turnos = user_states[numero_limpio]["turnos"]

            if opcion < 0 or opcion >= len(turnos):
                enviar_mensaje("❌ Opción inválida. Elegí un número de la lista.", numero)
                return

            turno_seleccionado = turnos[opcion]

            user_states[numero_limpio]["turno_a_reagendar"] = turno_seleccionado
            user_states[numero_limpio]["paso"] = "elegir_nueva_fecha"

            enviar_mensaje(
                "📅 Indicá la nueva fecha para el turno (por ejemplo: 25/12):",
                numero
            )

        except ValueError:
            enviar_mensaje("❌ Enviá solo el número del turno.", numero)


    # OPCIÓN 6: 'PREGUNTAS FRECUENTES (FAQ)'
    elif estado == "menu" and texto == "6":
        mensaje = """
    *Preguntas Frecuentes:*

*¿Puedo cambiar la hora?*
Cancelá el turno actual y reservá uno nuevo

*¿Con cuánto tiempo de anticipación debo reservar?*
Podés reservar hasta con 30 días de anticipación

*¿Qué pasa si llego tarde?*
Intentá llegar 5 min antes. Si llegás más de 15 min tarde, tu turno podría ser reasignado

*¿Formas de pago?*
Efectivo, débito y crédito

Escribí *menu* para volver
"""
        enviar_mensaje(mensaje, numero)
    #OPCIÓN 7: 'UBICACÓN Y CONTACTO'
    elif estado == "menu" and texto == "7":
        config = PELUQUERIAS[peluqueria_key]
        mensaje = f"""
        *Ubicación de {config['nombre']}:*

    Dirección: Calle Ejemplo 123, Buenos Aires

🕒 *Horarios:*
Lunes a Viernes: 08:00 - 20:00
Sábados: 08:00 - 19:00
Domingos: Cerrado

📞 *Contacto:*
Teléfono: +54 9 11 1234-5678


Escribí *menu* para volver
"""
        enviar_mensaje(mensaje, numero)

    elif estado == "menu" and texto == "0":
        enviar_mensaje(
            "👋 ¡Gracias por contactarnos!\n\n"
            "Cuando quieras volver, escribí *hola* o *menu*\n\n"
            "Peluquería *Demo* 💈",
            numero
        )
        user_states[numero_limpio]["paso"] = "finalizado"

    else:
        enviar_mensaje("❓ No entendí. Escribí *menu* para volver al menú.", numero)
    
    return "", 200



if __name__ == "__main__":
    print("Bot iniciado en puerto 3000")
    # Iniciar recordatorios
    hilo_recordatorios = threading.Thread(target=sistema_recordatorios, daemon=True)
    hilo_recordatorios.start()
    print("✅ Sistema de recordatorios activado")


    # ✅ Puerto dinámico
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
  
  
    # Debug true: para ver todos los errores detallados, el servidor se reinicia automáticamente al guardar cambios,
    # y ves todas las peticiones HTTP