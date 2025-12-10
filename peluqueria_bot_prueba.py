from flask import Flask, request
import requests 
from google.auth.transport.requests import Request
import json
from datetime import datetime, timedelta
import pytz
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import threading
import time
from dotenv import load_dotenv

app = Flask(__name__)

# ------------------- CONFIGURACIÓN DE META ---------------------


load_dotenv()  # Carga variables de .env

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

# ------------------- CONFIGURACIÓN GOOGLE CALENDAR ---------------------
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = 'primary'  # Podrías usar otro calendar si querés

# ------------------- ARCHIVOS GLOBALES RECORDATORIOS ---------------------
ARCHIVO_RECORDATORIOS = "recordatorios_enviados.json"
recordatorios_enviados = set()

# ------------------- CONFIGURACIÓN GOOGLE CALENDAR ---------------------

def get_calendar_service():   
    """Conecta con la API de Google Calendar usando token.json"""
    if not os.path.exists('token.json'):
        print("❌ ERROR: No se encontró token.json")
        return None

    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('calendar', 'v3', credentials=creds)

def esta_ocupado(horario, ocupados):
    """Verifica si un horario está ocupado con 1 minuto de tolerancia"""
    for ocupado in ocupados:
        if abs((horario - ocupado).total_seconds()) < 60:
            return True
    return False

def obtener_horarios_disponibles():
    """Genera turnos cada 30 min y revisa eventos ocupados en Google Calendar"""

    try:
        service = get_calendar_service()
        if not service:
            return []

        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        
        # Empezar desde las 8 AM o desde ahora (lo que sea más tarde)
        hora_inicio = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
        if ahora > hora_inicio:
            # Redondear a la próxima media hora
            minutos = 30 if ahora.minute < 30 else 0
            hora = ahora.hour if minutos == 30 else ahora.hour + 1
            if hora < 19:  # Solo si aún no cerramos
                hora_inicio = ahora.replace(hour=hora, minute=minutos, second=0, microsecond=0)
        
        hora_fin = ahora.replace(hour=19, minute=0, second=0, microsecond=0)
        
        # Si ya cerró la peluquería
        if ahora >= hora_fin:
            return []
    # Consulta a Google Calendar para obtener todos los eventos (turnos ya reservados) dentro de un rango de tiempo.
    # Extrae las horas de inicio de cada evento → ocupados = [09:00, 11:00, ...]
    # Genera todos los horarios posibles (8:00, 8:30, 9:00, 9:30... hasta 19:00)
    # Filtra los que NO están en ocupados
    # Le muestra al usuario solo los horarios disponibles
        eventos = service.events().list(
            calendarId=CALENDAR_ID, # Calendario principal del usuario
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
        # Generar horarios libres
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

def obtener_turnos_cliente(telefono):
    """Busca todos los turnos futuros de un cliente por su teléfono"""
    service = get_calendar_service()
    
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    ahora = datetime.now(tz)
    
    # Buscar eventos desde ahora hasta 30 días adelante
    eventos = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=ahora.isoformat(),
        timeMax=(ahora + timedelta(days=30)).isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    turnos_cliente = []
    
    if "items" in eventos:
        for event in eventos["items"]:
            descripcion = event.get("description", "")
            if telefono in descripcion:
                try:
                    turno_info = {
                        "id": event["id"],
                        "resumen": event.get("summary", "Sin título"),
                        "inicio": datetime.fromisoformat(
                            event["start"]["dateTime"].replace("Z", "+00:00")
                        )
                    }
                    turnos_cliente.append(turno_info)
                except Exception as e:
                    print(f"Error procesando evento: {e}")
                    continue
    
    return turnos_cliente

def cancelar_turno(event_id):
    """Elimina un evento del calendario por su ID"""
    try:
        service = get_calendar_service()
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()
        return True
    except Exception as e:
        print(f"Error cancelando turno: {e}")
        return False


def crear_reserva_en_calendar(fecha_hora, cliente, servicio, telefono):
    """Crea un evento en Google Calendar al confirmar turno"""
    service = get_calendar_service()

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

    service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()

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
def guardar_recordatorios_enviados(recordatorios):
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

def obtener_turnos_proximos(horas_anticipacion=24):
    """
    Obtiene turnos que ocurrirán en X horas
    Por defecto busca turnos en las próximas 24 horas
    """
    try:
        service = get_calendar_service()
        if not service:
            return []
        
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        
        # Rango de búsqueda: desde ahora hasta ahora + horas_anticipacion
        tiempo_inicio = ahora + timedelta(hours=horas_anticipacion - 1)  # 23 horas desde ahora
        tiempo_fin = ahora + timedelta(hours=horas_anticipacion + 1)     # 25 horas desde ahora
        
        eventos = service.events().list(
            calendarId=CALENDAR_ID,
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
                    inicio = datetime.fromisoformat(
                        event["start"]["dateTime"].replace("Z", "+00:00")
                    )
                    
                    descripcion = event.get("description", "")
                    
                    # Extraer teléfono de la descripción
                    # Formato: "Cliente: Juan\Tel: 5492974924147"
                    telefono = None
                    for linea in descripcion.split("\n"):
                        if linea.startswith("Tel:"):
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
                f"📍 Peluquería El Corte\n\n"
                f"¡Te esperamos! 💈\n\n"
                f"_Si necesitás cancelar, escribí *menu* y elegí la opción 3_"
            )
        elif horas_faltantes >= 1 and horas_faltantes < 3:  # Recordatorio de 2 horas
            mensaje = (
                f"⏰ *Recordatorio urgente*\n\n"
                f"Tu turno es en {horas_faltantes} horas:\n\n"
                f"🕒 Hora: {hora}\n"
                f"📍 Peluquería El Corte\n\n"
                f"¡Nos vemos pronto! 💈"
            )
        else:
            return  # No enviar si no es momento
        
        enviar_mensaje(mensaje, turno["telefono"])
        print(f"✅ Recordatorio enviado a {turno['telefono']} para turno de {hora}")
        
    except Exception as e:
        print(f"❌ Error enviando recordatorio: {e}")
        

def sistema_recordatorios():
    """
    Sistema que corre en segundo plano verificando turnos cada hora
    """
    global recordatorios_enviados
    
    # ✅ 1. CARGAR recordatorios previos al iniciar
    recordatorios_enviados = cargar_recordatorios_enviados()
    print(f"📂 Cargados {len(recordatorios_enviados)} recordatorios previos")
    print("🔔 Sistema de recordatorios iniciado")
    
    while True:
        try:
            ahora = datetime.now().strftime('%H:%M')
            print(f"\n⏰ [{ahora}] Verificando turnos próximos...")
            
            # Recordatorios de 24 horas
            turnos_24h = obtener_turnos_proximos(horas_anticipacion=24)
            for turno in turnos_24h:
                recordatorio_id = f"{turno['id']}_24h"
                
                if recordatorio_id not in recordatorios_enviados:
                    enviar_recordatorio(turno)
                    recordatorios_enviados.add(recordatorio_id)
                    
                    # ✅ 2. GUARDAR inmediatamente después de enviar
                    guardar_recordatorios_enviados(recordatorios_enviados)
                    
                    print(f"   📤 Recordatorio 24h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")
            
            # Recordatorios de 2 horas
            turnos_2h = obtener_turnos_proximos(horas_anticipacion=2)
            for turno in turnos_2h:
                recordatorio_id = f"{turno['id']}_2h"
                
                if recordatorio_id not in recordatorios_enviados:
                    enviar_recordatorio(turno)
                    recordatorios_enviados.add(recordatorio_id)
                    
                    # ✅ 2. GUARDAR inmediatamente
                    guardar_recordatorios_enviados(recordatorios_enviados)
                    
                    print(f"   📤 Recordatorio 2h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")
            
            print("   ✅ Verificación completada. Próxima en 1 hora.")
            
            # Limpiar recordatorios antiguos
            if len(recordatorios_enviados) > 1000:
                print("   🧹 Limpiando recordatorios antiguos...")
                recordatorios_enviados.clear()
                
                # ✅ 3. GUARDAR después de limpiar
                guardar_recordatorios_enviados(recordatorios_enviados)
                
                print("   ✅ Limpieza completada")
            
        except Exception as e:
            print(f"   ❌ Error en sistema de recordatorios: {e}")
        
        # Esperar 1 hora
        time.sleep(3600)

# ------------------- MENSAJERÍA WHATSAPP ---------------------

user_states = {}

def enviar_mensaje(texto, numero):
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "text": {"body": texto}
    }
    
    try:
        print(f"\n📤 Intentando enviar mensaje a: {numero}")
        print(f"📝 Contenido: {texto[:50]}...")  # Primeros 50 caracteres
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        # PARA VER EL ERROR COMPLETO
        if response.status_code != 200:
            print(f"❌ Error {response.status_code}")
            print(f"📄 Respuesta completa: {response.text}")
            print(f"🔑 Token usado: {ACCESS_TOKEN[:20]}...")  # Primeros 20 caracteres
            print(f"📞 Phone ID: {PHONE_NUMBER_ID}")
        
        response.raise_for_status()
        print("✅ Mensaje enviado correctamente")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error enviando mensaje: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"📄 Detalles: {e.response.text}")


@app.route("/webhook", methods=["GET", "POST"])

def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Token inválido"

    if request.method == "POST":
        body = request.get_json()
        print("--- MENSAJE RECIBIDO ---")
        print(json.dumps(body, indent=2, ensure_ascii=False))

        try:
            numero = body['entry'][0]['changes'][0]['value']['messages'][0]['from']
            texto = body['entry'][0]['changes'][0]['value']['messages'][0]['text']['body'].strip().lower()
        except:
            return "ok" # Esperar su respuesta

    # ✅ SI ES USUARIO NUEVO → Mostrar menú automáticamente
        if numero not in user_states:
            user_states[numero] = {"paso": "menu"}
            enviar_mensaje(
                "👋 ¡Hola! Bienvenido a *Peluquería El Corte* 💈\n\n"
                "Elige una opción:\n"
                "1️⃣ Pedir turno\n"
                "2️⃣ Ver mis turnos\n"
                "3️⃣ Cancelar turno\n"
                "4️⃣ Servicios\n"
                "0️⃣ Salir\n\n"
                "Escribí el número de la opción o *menu* para volver aquí",
                numero
            )
            return "ok" # Esperar su respuesta

        estado = user_states[numero]["paso"]

        # ✅ Comando para volver al menú en cualquier momento
        if texto == "menu":
            user_states[numero]["paso"] = "menu"
            enviar_mensaje(
                "📋 *Menú principal:*\n\n"
                "1️⃣ Pedir turno\n"
                "2️⃣ Ver mis turnos\n"
                "3️⃣ Cancelar turno\n"
                "4️⃣ Servicios\n"
                "0️⃣ Salir",
                numero
            )
            return "ok" # Esperar su respuesta
        
        # Comando para cancelar operación actual
        if texto in ["cancelar", "salir", "abortar", "stop"]:
            # Solo cancelar si NO está en el menú principal
            if estado != "menu":
                # Resetea el estado
                user_states[numero]["paso"] = "menu"
                enviar_mensaje(
                    "❌ Operación cancelada.\n\n"
                    "Volviste al menú principal.\n"
                    "Escribí *menu* para ver las opciones.",
                    numero
                )
                return "ok"

        # OPCIÓN 1: 'PEDIR TURNO'
        if estado == "menu" and texto == "1":
            horarios = obtener_horarios_disponibles()
            if not horarios:
                enviar_mensaje("😞 No hay horarios disponibles hoy.", numero)
            else:
                user_states[numero]["horarios"] = horarios
                user_states[numero]["paso"] = "seleccionar_horario"
                lista = "\n".join([f"{i+1}️⃣ {h.strftime('%H:%M')}" for i, h in enumerate(horarios)])
                enviar_mensaje("⏱ Horarios disponibles hoy:\n\n" + lista + "\n\nElegí un número:", numero)

        elif estado == "seleccionar_horario":
            try:
                index = int(texto) - 1
                if 0 <= index < len(user_states[numero]["horarios"]):
                    fecha_hora = user_states[numero]["horarios"][index]
                    user_states[numero]["fecha_hora"] = fecha_hora
                    user_states[numero]["paso"] = "nombre"
                    enviar_mensaje("Perfecto ✂️ ¿A nombre de quién tomo el turno?", numero)
                else:
                    enviar_mensaje("Número fuera de rango. Elegí uno válido.", numero)
            except ValueError:
                enviar_mensaje("Debe ser un número", numero)

        elif estado == "nombre":
            user_states[numero]["cliente"] = texto.title()
            user_states[numero]["paso"] = "servicio"
            enviar_mensaje("📌 ¿Qué servicio querés?\nEj: Corte, Tintura, Barba", numero)

        elif estado == "servicio":
            fecha_hora = user_states[numero]["fecha_hora"]
            cliente = user_states[numero]["cliente"]
            telefono = numero
            servicio = texto.title()

            crear_reserva_en_calendar(fecha_hora, cliente, servicio, telefono)

            enviar_mensaje(
                f"📅 ¡Listo {cliente}! Turno reservado:\n"
                f"🕒 {fecha_hora.strftime('%H:%M')}\n"
                f"✂️ Servicio: {servicio}\n"
                f"📍 Peluquería El Corte\n"
                f"¡Te esperamos!",
                numero
            )

            user_states[numero]["paso"] = "menu"

        # OPCIÓN 2: 'VER MIS TURNOS'
        elif estado == "menu" and texto == "2":
            turnos = obtener_turnos_cliente(numero)
            
            if not turnos:
                enviar_mensaje("📭 No tenés turnos reservados.", numero)
            else:
                lista = []
                for i, turno in enumerate(turnos):
                    fecha = turno["inicio"].strftime("%d/%m/%Y")
                    hora = turno["inicio"].strftime("%H:%M")
                    lista.append(f"{i+1}. {fecha} a las {hora} - {turno['resumen']}")
                
                mensaje = "📅 *Tus turnos:*\n\n" + "\n".join(lista)
                enviar_mensaje(mensaje, numero)
        # OPCIÓN 3: 'CANCELAR TURNO'
        elif estado == "menu" and texto == "3":
            turnos = obtener_turnos_cliente(numero)
            
            if not turnos:
                enviar_mensaje("📭 No tenés turnos para cancelar.", numero)
            else:
                user_states[numero]["turnos"] = turnos
                user_states[numero]["paso"] = "seleccionar_turno_cancelar"
                
                lista = []
                for i, turno in enumerate(turnos):
                    fecha = turno["inicio"].strftime("%d/%m/%Y")
                    hora = turno["inicio"].strftime("%H:%M")
                    lista.append(f"{i+1}️⃣ {fecha} a las {hora}")
                
                mensaje = "❌ *Selecciona el turno a cancelar:*\n\n" + "\n".join(lista) + "\n\n0️⃣ Volver al menú"
                enviar_mensaje(mensaje, numero)

        elif estado == "seleccionar_turno_cancelar":
            if texto == "0":
                user_states[numero]["paso"] = "menu"
                enviar_mensaje("✅ Cancelación abortada. Escribí *menu* para volver.", numero)
            else:
                try:
                    index = int(texto) - 1
                    if 0 <= index < len(user_states[numero]["turnos"]):
                        turno_seleccionado = user_states[numero]["turnos"][index]
                        user_states[numero]["turno_a_cancelar"] = turno_seleccionado
                        user_states[numero]["paso"] = "confirmar_cancelacion"
                        
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
                turno = user_states[numero]["turno_a_cancelar"]
                
                if cancelar_turno(turno["id"]):
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
                
                user_states[numero]["paso"] = "menu"
                
            elif texto == "no":
                enviar_mensaje("✅ Cancelación abortada. Tu turno sigue reservado.", numero)
                user_states[numero]["paso"] = "menu"
            else:
                enviar_mensaje("⚠️ Respondé *SI* o *NO*", numero)

        #OPCIÓN 4: 'SERVICIOS'
        elif estado == "menu" and texto == "4":
            enviar_mensaje(
                "✂️ *Nuestros servicios:*\n\n"
                "• Corte clásico\n"
                "• Corte moderno\n"
                "• Barba y bigote\n"
                "• Tintura\n"
                "• Tratamientos capilares\n\n"
                "Escribí *menu* para volver",
                numero
            )

        elif estado == "menu" and texto == "0":
            enviar_mensaje(
                "👋 ¡Gracias por contactarnos!\n\n"
                "Cuando quieras volver, escribí *hola* o *menu*\n\n"
                "Peluquería *El Míster* 💈",
                numero
            )
            # Opcional: limpiar el estado del usuario
            user_states[numero]["paso"] = "finalizado"

        else:
            enviar_mensaje("❓ No entendí. Escribí *menu* para volver al menú.", numero)
        
            return "ok"
    
if __name__ == "__main__":
    print("Bot iniciado en puerto 3000")
    # Iniciar recordatorios
    hilo_recordatorios = threading.Thread(target=sistema_recordatorios, daemon=True)
    hilo_recordatorios.start()
    print("✅ Sistema de recordatorios activado")


    # ✅ Puerto dinámico
    port = int(os.getenv("PORT", 3000))  # Usa variable PORT del servidor, o 3000 por defecto
    app.run(host="0.0.0.0", port=port, debug=False)  # debug=False en producción
  
  
    # Debug true: para ver todos los errores detallados, el servidor se reinicia automáticamente al guardar cambios,
    # y ves todas las peticiones HTTP