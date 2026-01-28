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
            
            # Refrescar si es necesario
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Guardar credenciales actualizadas
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            
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
            
            hora_inicio = horario_dia.get("inicio", "09:00")
            hora_fin = horario_dia.get("fin", "18:00")
            
            # Crear datetime con timezone local
            inicio_dt = datetime.combine(dia, datetime.strptime(hora_inicio, "%H:%M").time())
            fin_dt = datetime.combine(dia, datetime.strptime(hora_fin, "%H:%M").time())
            
            # Obtener eventos del calendario
            eventos = service.events().list(
                calendarId=calendar_id,
                timeMin=inicio_dt.isoformat(),
                timeMax=fin_dt.isoformat(),
                timeZone=timezone,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            eventos_ocupados = eventos.get('items', [])
            
            # Generar slots de tiempo
            horarios_disponibles = []
            hora_actual = inicio_dt
            
            while hora_actual + timedelta(minutes=duracion_minutos) <= fin_dt:
                slot_inicio = hora_actual
                slot_fin = hora_actual + timedelta(minutes=duracion_minutos)
                
                # Verificar si el slot está ocupado
                ocupado = False
                for evento in eventos_ocupados:
                    # Verificar si el evento es del peluquero correcto
                    peluquero_evento = evento.get('summary', '')
                    if peluquero['nombre'] not in peluquero_evento:
                        continue
                    
                    evento_inicio = datetime.fromisoformat(evento['start'].get('dateTime', evento['start'].get('date')))
                    evento_fin = datetime.fromisoformat(evento['end'].get('dateTime', evento['end'].get('date')))
                    
                    # Verificar solapamiento
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