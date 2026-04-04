"""
Servicio de Google Calendar
Maneja toda la interacción con la API de Google Calendar
"""

import os
import json
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from threading import Lock

# Cache de servicios por cliente (thread-safe)
services_cache = {}
services_lock = Lock()

SCOPES = ['https://www.googleapis.com/auth/calendar']


class CalendarService:
    """Servicio para interactuar con Google Calendar"""
    
    def __init__(self, peluquerias_config):
        """
        Inicializa el servicio de calendario
        
        Args:
            peluquerias_config: Diccionario con configuración de clientes
        """
        self.peluquerias = peluquerias_config
        self.services_cache = {}
        self.cache_lock = Lock()
    
    def get_calendar_service(self, peluqueria_key):
        """
        Obtiene o crea un servicio de Calendar para un cliente específico
        
        Args:
            peluqueria_key: Identificador del cliente (ej: "peluqueria_roca")
        
        Returns:
            Resource: Servicio de Google Calendar
        """
        with self.cache_lock:
            # Si ya está en cache, devolverlo
            if peluqueria_key in self.services_cache:
                return self.services_cache[peluqueria_key]
            
            config = self.peluquerias.get(peluqueria_key)
            if not config:
                raise ValueError(f"Cliente {peluqueria_key} no encontrado")
            
            calendar_id = config.get("calendar_id")
            if not calendar_id:
                raise ValueError(f"Cliente {peluqueria_key} no tiene calendar_id configurado")
            
            # Construir ruta del token
            token_path = f"tokens/{peluqueria_key}_token.json"
            
            if not os.path.exists(token_path):
                raise FileNotFoundError(
                    f"No se encontró token para {peluqueria_key} en {token_path}"
                )
            
            # Cargar credenciales
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
            # Refrescar si es necesario e invalidar cache viejo
            if creds and creds.expired and creds.refresh_token:
                print(f"Renovando token de Calendar para {peluqueria_key}...")
                creds.refresh(Request())
                # Guardar credenciales actualizadas
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
                # Invalidar cache para forzar nuevo servicio con creds frescas
                self.services_cache.pop(peluqueria_key, None)
                print(f"Token renovado y cache invalidado para {peluqueria_key}")
            
            if not creds or not creds.valid:
                raise ValueError(
                    f"Token invalido para {peluqueria_key}. "
                    f"Necesitas reautorizar Google Calendar."
                )
            
            # Crear servicio
            service = build('calendar', 'v3', credentials=creds)
            
            # Guardar en cache
            self.services_cache[peluqueria_key] = service
            
            print(f"✅ Servicio de Calendar creado para {peluqueria_key}")
            return service
    
    def buscar_turnos_disponibles(self, peluqueria_key, peluquero, dia, duracion_minutos=30):
        """
        Busca horarios disponibles para un peluquero en un día específico
        
        Args:
            peluqueria_key: Identificador del cliente
            peluquero: Diccionario con datos del peluquero
            dia: Objeto date del día a buscar
            duracion_minutos: Duración del turno en minutos
        
        Returns:
            list: Lista de horarios disponibles como strings "HH:MM"
        """
        try:
            service = self.get_calendar_service(peluqueria_key)
            config = self.peluquerias[peluqueria_key]
            calendar_id = config["calendar_id"]
            timezone = config["timezone"]
            
            # Obtener horarios del peluquero
            horarios = peluquero.get("horarios", {})
            dia_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'][dia.weekday()]
            
            horario_dia = horarios.get(dia_semana)
            if not horario_dia:
                return []

            # Normalizar formato de horarios — soporta 3 formatos del clientes.json:
            # 1. Lista simple:   ["09:00", "18:00"]
            # 2. Horario partido: [["09:00", "13:00"], ["17:00", "20:00"]]
            # 3. Diccionario (legacy): {"inicio": "09:00", "fin": "18:00"}
            def parsear_franjas(horario):
                """Devuelve lista de tuplas (hora_inicio_str, hora_fin_str)"""
                if isinstance(horario, dict):
                    return [(horario.get("inicio", "09:00"), horario.get("fin", "18:00"))]
                if isinstance(horario, list):
                    if len(horario) == 0:
                        return []
                    # Horario partido: [["09:00", "13:00"], ["17:00", "20:00"]]
                    if isinstance(horario[0], list):
                        return [(h[0], h[1]) for h in horario if len(h) >= 2]
                    # Lista simple: ["09:00", "18:00"]
                    if len(horario) >= 2 and isinstance(horario[0], str):
                        return [(horario[0], horario[1])]
                return [("09:00", "18:00")]

            franjas = parsear_franjas(horario_dia)
            if not franjas:
                return []

            # Obtener todos los eventos del día completo (cubre todas las franjas)
            dia_inicio_dt = datetime.combine(dia, datetime.strptime("00:00", "%H:%M").time())
            dia_fin_dt = datetime.combine(dia, datetime.strptime("23:59", "%H:%M").time())

            eventos = service.events().list(
                calendarId=calendar_id,
                timeMin=dia_inicio_dt.isoformat(),
                timeMax=dia_fin_dt.isoformat(),
                timeZone=timezone,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            eventos_ocupados = eventos.get('items', [])

            # Generar slots para cada franja horaria
            horarios_disponibles = []

            for hora_inicio_str, hora_fin_str in franjas:
                inicio_dt = datetime.combine(dia, datetime.strptime(hora_inicio_str, "%H:%M").time())
                fin_dt = datetime.combine(dia, datetime.strptime(hora_fin_str, "%H:%M").time())
                hora_actual = inicio_dt

                while hora_actual + timedelta(minutes=duracion_minutos) <= fin_dt:
                    slot_inicio = hora_actual
                    slot_fin = hora_actual + timedelta(minutes=duracion_minutos)

                    ocupado = False
                    for evento in eventos_ocupados:
                        peluquero_evento = evento.get('summary', '')
                        if peluquero['nombre'] not in peluquero_evento:
                            continue

                        evento_inicio_str = evento['start'].get('dateTime', evento['start'].get('date'))
                        evento_fin_str = evento['end'].get('dateTime', evento['end'].get('date'))

                        try:
                            evento_inicio = datetime.fromisoformat(evento_inicio_str.replace('Z', '+00:00'))
                            evento_fin = datetime.fromisoformat(evento_fin_str.replace('Z', '+00:00'))
                            # Comparar sin timezone para simplicidad
                            evento_inicio = evento_inicio.replace(tzinfo=None)
                            evento_fin = evento_fin.replace(tzinfo=None)
                        except Exception:
                            continue

                        if not (slot_fin <= evento_inicio or slot_inicio >= evento_fin):
                            ocupado = True
                            break

                    if not ocupado:
                        horarios_disponibles.append(hora_actual.strftime("%H:%M"))

                    hora_actual += timedelta(minutes=duracion_minutos)

            return horarios_disponibles
        
        except HttpError as e:
            print(f"❌ Error de Google Calendar API: {e}")
            return []
        except Exception as e:
            print(f"❌ Error al buscar turnos: {e}")
            return []
    
    def crear_evento_calendario(self, peluqueria_key, peluquero, cliente_nombre, cliente_telefono, 
                               fecha_hora_inicio, duracion_minutos=30):
        """
        Crea un evento en Google Calendar
        
        Args:
            peluqueria_key: Identificador del cliente
            peluquero: Diccionario con datos del peluquero
            cliente_nombre: Nombre del cliente
            cliente_telefono: Teléfono del cliente
            fecha_hora_inicio: Datetime del inicio del turno
            duracion_minutos: Duración del turno
        
        Returns:
            dict: Información del evento creado o None si falló
        """
        try:
            service = self.get_calendar_service(peluqueria_key)
            config = self.peluquerias[peluqueria_key]
            calendar_id = config["calendar_id"]
            timezone = config["timezone"]
            
            fecha_hora_fin = fecha_hora_inicio + timedelta(minutes=duracion_minutos)
            
            evento = {
                'summary': f'{peluquero["nombre"]} - {cliente_nombre}',
                'description': f'Cliente: {cliente_nombre}\nTeléfono: {cliente_telefono}',
                'start': {
                    'dateTime': fecha_hora_inicio.isoformat(),
                    'timeZone': timezone,
                },
                'end': {
                    'dateTime': fecha_hora_fin.isoformat(),
                    'timeZone': timezone,
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 60},
                    ],
                },
            }
            
            evento_creado = service.events().insert(
                calendarId=calendar_id, 
                body=evento
            ).execute()
            
            print(f"✅ Evento creado: {evento_creado.get('id')}")
            
            return {
                'id': evento_creado.get('id'),
                'link': evento_creado.get('htmlLink'),
                'inicio': fecha_hora_inicio,
                'fin': fecha_hora_fin
            }
        
        except HttpError as e:
            print(f"❌ Error al crear evento: {e}")
            return None
        except Exception as e:
            print(f"❌ Error inesperado al crear evento: {e}")
            return None
    
    def cancelar_evento_calendario(self, peluqueria_key, evento_id):
        """
        Cancela un evento en Google Calendar
        
        Args:
            peluqueria_key: Identificador del cliente
            evento_id: ID del evento a cancelar
        
        Returns:
            bool: True si se canceló exitosamente
        """
        try:
            service = self.get_calendar_service(peluqueria_key)
            config = self.peluquerias[peluqueria_key]
            calendar_id = config["calendar_id"]
            
            service.events().delete(
                calendarId=calendar_id,
                eventId=evento_id
            ).execute()
            
            print(f"✅ Evento {evento_id} cancelado")
            return True
        
        except HttpError as e:
            print(f"❌ Error al cancelar evento: {e}")
            return False
        except Exception as e:
            print(f"❌ Error inesperado al cancelar: {e}")
            return False
    
    def obtener_turnos_proximos(self, peluqueria_key, dias_adelante=7):
        """
        Obtiene todos los turnos próximos del calendario
        
        Args:
            peluqueria_key: Identificador del cliente
            dias_adelante: Cantidad de días a buscar hacia adelante
        
        Returns:
            list: Lista de eventos próximos
        """
        try:
            service = self.get_calendar_service(peluqueria_key)
            config = self.peluquerias[peluqueria_key]
            calendar_id = config["calendar_id"]
            timezone = config["timezone"]
            
            ahora = datetime.now()
            hasta = ahora + timedelta(days=dias_adelante)
            
            eventos = service.events().list(
                calendarId=calendar_id,
                timeMin=ahora.isoformat(),
                timeMax=hasta.isoformat(),
                timeZone=timezone,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return eventos.get('items', [])
        
        except HttpError as e:
            print(f"❌ Error al obtener turnos próximos: {e}")
            return []
        except Exception as e:
            print(f"❌ Error inesperado: {e}")
            return []


def get_calendar_service(peluqueria_key, peluquerias_config):
    """
    Función legacy para compatibilidad con código existente
    """
    service = CalendarService(peluquerias_config)
    return service.get_calendar_service(peluqueria_key)