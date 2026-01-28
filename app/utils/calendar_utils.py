"""
Utilidades de Calendario
Funciones auxiliares para trabajar con horarios y turnos en Google Calendar
"""

from datetime import datetime, timedelta
import pytz
from app.services.calendar_service import CalendarService
from app.utils.time_utils import ahora_local, crear_datetime_local

try:
    from app.core.database import obtener_turnos_por_telefono
    MONGODB_DISPONIBLE = True
except ImportError:
    MONGODB_DISPONIBLE = False
    def obtener_turnos_por_telefono(*args, **kwargs): return []


class CalendarUtils:
    """Utilidades para trabajar con horarios y turnos"""
    
    def __init__(self, peluquerias_config):
        """
        Inicializa las utilidades de calendario
        
        Args:
            peluquerias_config: Diccionario con configuración de clientes
        """
        self.peluquerias = peluquerias_config
        self.calendar_service = CalendarService(peluquerias_config)
    
    def obtener_horarios_disponibles(self, peluqueria_key, dia_seleccionado=None):
        """
        Genera turnos y revisa eventos ocupados en Google Calendar
        (sin peluquero específico - horarios generales del local)
        
        Args:
            peluqueria_key: Identificador del cliente
            dia_seleccionado: Objeto date (opcional, default: hoy)
        
        Returns:
            list: Lista de datetime con horarios disponibles
        """
        try:
            if peluqueria_key not in self.peluquerias:
                print(f"❌ Peluquería inválida: {peluqueria_key}")
                return []
            
            config = self.peluquerias.get(peluqueria_key, {})
            timezone = config.get("timezone", "America/Argentina/Buenos_Aires")
            tz = pytz.timezone(timezone)
            
            service = self.calendar_service.get_calendar_service(peluqueria_key)
            
            if not service:
                print("❌ Service es None, retornando []")
                return []
            
            calendar_id = config.get("calendar_id")
            
            # Obtener hora actual local
            ahora = ahora_local(peluqueria_key, self.peluquerias)
            
            if dia_seleccionado is None:
                dia_seleccionado = ahora.date()
            
            # Si el día es domingo, retornar vacío (cerrado)
            if dia_seleccionado.weekday() == 6:
                return []
            
            # Obtener horarios de la configuración
            dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
            dia_nombre = dias_semana[dia_seleccionado.weekday()]
            
            # Si la peluquería tiene horarios configurados, usarlos
            if "horarios" in config and dia_nombre in config["horarios"]:
                horario_config = config["horarios"][dia_nombre]
                hora_apertura = int(horario_config[0].split(':')[0])
                minuto_apertura = int(horario_config[0].split(':')[1])
                hora_cierre = int(horario_config[1].split(':')[0])
                minuto_cierre = int(horario_config[1].split(':')[1])
            else:
                # Horarios por defecto
                hora_apertura = 8
                minuto_apertura = 0
                hora_cierre = 21
                minuto_cierre = 0
            
            hora_inicio = tz.localize(
                datetime.combine(
                    dia_seleccionado,
                    datetime.min.time()
                ).replace(hour=hora_apertura, minute=minuto_apertura)
            )
            
            hora_fin = tz.localize(
                datetime.combine(
                    dia_seleccionado,
                    datetime.min.time()
                ).replace(hour=hora_cierre, minute=minuto_cierre)
            )
            
            # Si es hoy, ajustar hora_inicio al siguiente slot disponible
            if dia_seleccionado == ahora.date():
                if ahora > hora_inicio:
                    minutos = (ahora.minute // 30 + 1) * 30
                    if minutos >= 60:
                        hora_inicio = ahora.replace(
                            hour=ahora.hour + 1,
                            minute=0,
                            second=0,
                            microsecond=0
                        )
                    else:
                        hora_inicio = ahora.replace(
                            minute=minutos,
                            second=0,
                            microsecond=0
                        )
            
            # Obtener eventos del calendario
            eventos = service.events().list(
                calendarId=calendar_id,
                timeMin=hora_inicio.isoformat(),
                timeMax=hora_fin.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            # Extraer horarios ocupados
            ocupados = []
            if "items" in eventos:
                for event in eventos["items"]:
                    try:
                        start_str = event["start"].get("dateTime")
                        if start_str:
                            start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                            ocupados.append(start)
                    except Exception:
                        continue
            
            # Generar horarios libres
            horarios_libres = []
            horario = hora_inicio
            while horario < hora_fin:
                if not self._esta_ocupado(horario, ocupados):
                    horarios_libres.append(horario)
                horario += timedelta(minutes=30)
            
            return horarios_libres
        
        except Exception as e:
            print(f"❌ Error obteniendo horarios: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def obtener_horarios_peluquero(self, peluqueria_key, dia_seleccionado, peluquero_id):
        """
        Obtiene horarios disponibles de un peluquero específico
        SOPORTA HORARIOS PARTIDOS (mañana y tarde)
        MANEJA FORMATO MIXTO CORRECTAMENTE
        
        Args:
            peluqueria_key: Identificador del cliente
            dia_seleccionado: Objeto date
            peluquero_id: ID del peluquero
        
        Returns:
            list: Lista de datetime con horarios disponibles
        """
        try:
            config = self.peluquerias.get(peluqueria_key, {})
            ahora = ahora_local(peluqueria_key, self.peluquerias)
            
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
            
            # Normalizar formato ANTES de procesar
            # Detectar si primer elemento es string (formato viejo) o list (formato nuevo)
            if horarios_dia and isinstance(horarios_dia[0], str):
                # Formato viejo: ["09:00", "18:00"] → [["09:00", "18:00"]]
                horarios_dia = [horarios_dia]
                print(f"📅 {peluquero['nombre']} - {dia_nombre}: formato viejo convertido")
            else:
                print(f"📅 {peluquero['nombre']} - {dia_nombre}: formato nuevo (partidos)")
            
            # Obtener servicio de Calendar
            service = self.calendar_service.get_calendar_service(peluqueria_key)
            calendar_id = config.get("calendar_id")
            
            if not service:
                print("❌ No se pudo obtener servicio de Calendar")
                return []
            
            # Procesar cada rango horario
            horarios_libres = []
            
            for idx, rango in enumerate(horarios_dia):
                # Validación estricta
                if not isinstance(rango, list) or len(rango) != 2:
                    print(f"❌ Rango inválido en posición {idx}: {rango}")
                    continue
                
                hora_inicio_str, hora_fin_str = rango
                
                # Validar que sean strings
                if not isinstance(hora_inicio_str, str) or not isinstance(hora_fin_str, str):
                    print(f"❌ Formato de hora inválido: {hora_inicio_str}, {hora_fin_str}")
                    continue
                
                try:
                    # Parsear horas
                    hora_inicio = crear_datetime_local(
                        peluqueria_key,
                        self.peluquerias,
                        dia_seleccionado,
                        hora_inicio_str
                    )
                    
                    hora_fin = crear_datetime_local(
                        peluqueria_key,
                        self.peluquerias,
                        dia_seleccionado,
                        hora_fin_str
                    )
                    
                except (ValueError, IndexError) as e:
                    print(f"❌ Error parseando {hora_inicio_str}-{hora_fin_str}: {e}")
                    continue
                
                # Si es hoy, ajustar hora_inicio
                if dia_seleccionado == ahora.date():
                    if ahora > hora_inicio:
                        minutos = (ahora.minute // 30 + 1) * 30
                        if minutos >= 60:
                            hora_inicio = ahora.replace(
                                hour=ahora.hour + 1,
                                minute=0,
                                second=0,
                                microsecond=0
                            )
                        else:
                            hora_inicio = ahora.replace(
                                minute=minutos,
                                second=0,
                                microsecond=0
                            )
                    
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
                            # Verificar si es del peluquero correcto
                            summary = event.get("summary", "")
                            descripcion = event.get("description", "")
                            
                            if (peluquero['nombre'] in summary or 
                                f"Peluquero: {peluquero['nombre']}" in descripcion):
                                start_str = event["start"].get("dateTime")
                                if start_str:
                                    start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                                    ocupados.append(start)
                        except Exception:
                            continue
                
                # Generar slots libres
                horario = hora_inicio
                while horario < hora_fin:
                    if not self._esta_ocupado(horario, ocupados):
                        horarios_libres.append(horario)
                    horario += timedelta(minutes=30)
            
            print(f"✅ {peluquero['nombre']} - {dia_nombre}: {len(horarios_libres)} slots disponibles")
            return horarios_libres
        
        except Exception as e:
            print(f"❌ Error obteniendo horarios del peluquero: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def obtener_hora_cierre(self, peluqueria_key, dia_seleccionado, peluquero=None):
        """
        Obtiene la hora de cierre para un día específico
        Considera horarios del peluquero si está especificado
        
        Args:
            peluqueria_key: Identificador del cliente
            dia_seleccionado: Objeto date
            peluquero: Dict del peluquero (opcional)
        
        Returns:
            datetime: Hora de cierre con timezone local
        """
        try:
            config = self.peluquerias.get(peluqueria_key, {})
            timezone = config.get("timezone", "America/Argentina/Buenos_Aires")
            tz = pytz.timezone(timezone)
            
            dias_semana = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
            dia_nombre = dias_semana[dia_seleccionado.weekday()]
            
            # Si hay peluquero, usar sus horarios
            if peluquero:
                horarios_dia = peluquero.get("horarios", {}).get(dia_nombre)
                if horarios_dia:
                    # Manejar formato partidos
                    if isinstance(horarios_dia[0], list):
                        # Formato nuevo: [["09:00", "13:00"], ["14:00", "18:00"]]
                        # Tomar el cierre del último rango
                        hora_cierre_str = horarios_dia[-1][1]
                    else:
                        # Formato viejo: ["09:00", "18:00"]
                        hora_cierre_str = horarios_dia[1]
                    
                    hora_cierre = tz.localize(
                        datetime.combine(
                            dia_seleccionado,
                            datetime.min.time()
                        ).replace(
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
                datetime.combine(
                    dia_seleccionado,
                    datetime.min.time()
                ).replace(
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
                datetime.combine(
                    dia_seleccionado,
                    datetime.min.time()
                ).replace(hour=21, minute=0)
            )
    
    def obtener_turnos_cliente(self, peluqueria_key, telefono):
        """
        Obtiene todos los turnos futuros de un cliente
        
        Args:
            peluqueria_key: Identificador del cliente
            telefono: Número de teléfono del cliente
        
        Returns:
            list: Lista de turnos del cliente con formato:
                  [{"id": str, "resumen": str, "inicio": datetime}, ...]
        """
        try:
            # Intentar obtener de MongoDB primero
            if MONGODB_DISPONIBLE:
                turnos_db = obtener_turnos_por_telefono(peluqueria_key, telefono)
                if turnos_db:
                    return turnos_db
            
            # Fallback a Google Calendar
            if peluqueria_key not in self.peluquerias:
                print(f"❌ Peluquería inválida: {peluqueria_key}")
                return []
            
            config = self.peluquerias.get(peluqueria_key, {})
            timezone = config.get("timezone", "America/Argentina/Buenos_Aires")
            tz = pytz.timezone(timezone)
            
            service = self.calendar_service.get_calendar_service(peluqueria_key)
            calendar_id = config.get("calendar_id")
            
            if not service:
                print("❌ No se pudo obtener el servicio de Calendar")
                return []
            
            ahora = ahora_local(peluqueria_key, self.peluquerias)
            
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
                        descripcion_limpia = descripcion.replace(
                            '+', ''
                        ).replace(
                            ' ', ''
                        ).replace(
                            '-', ''
                        ).replace(
                            'Tel:', ''
                        ).replace(
                            '\n', ''
                        ).replace(
                            '\r', ''
                        )
                        
                        # Búsqueda flexible
                        if telefono_busqueda in descripcion_limpia:
                            inicio_str = event["start"].get("dateTime", event["start"].get("date"))
                            
                            if not inicio_str:
                                continue
                            
                            # Parsear fecha con timezone
                            if inicio_str.endswith('Z'):
                                inicio_utc = datetime.fromisoformat(inicio_str.replace("Z", "+00:00"))
                                inicio_local = inicio_utc.astimezone(tz)
                            else:
                                inicio_local = datetime.fromisoformat(inicio_str)
                                if inicio_local.tzinfo is None:
                                    inicio_local = tz.localize(inicio_local)
                                else:
                                    inicio_local = inicio_local.astimezone(tz)
                            
                            turno_info = {
                                "id": event["id"],
                                "resumen": summary,
                                "inicio": inicio_local
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
    
    def _esta_ocupado(self, horario, ocupados):
        """
        Verifica si un horario está ocupado con 1 minuto de tolerancia
        
        Args:
            horario: datetime a verificar
            ocupados: Lista de datetime ocupados
        
        Returns:
            bool: True si está ocupado
        """
        for ocupado in ocupados:
            if abs((horario - ocupado).total_seconds()) < 60:
                return True
        return False


# Instancia global (se inicializa desde app/__init__.py)
calendar_utils = None


def inicializar_calendar_utils(peluquerias_config):
    """Inicializa las utilidades de calendario globalmente"""
    global calendar_utils
    calendar_utils = CalendarUtils(peluquerias_config)
    return calendar_utils


# Funciones legacy para compatibilidad con código existente
def obtener_horarios_disponibles(peluqueria_key, dia_seleccionado=None):
    """Función legacy de compatibilidad"""
    if calendar_utils is None:
        raise RuntimeError("calendar_utils no está inicializado")
    return calendar_utils.obtener_horarios_disponibles(peluqueria_key, dia_seleccionado)


def obtener_horarios_peluquero(peluqueria_key, dia_seleccionado, peluquero_id):
    """Función legacy de compatibilidad"""
    if calendar_utils is None:
        raise RuntimeError("calendar_utils no está inicializado")
    return calendar_utils.obtener_horarios_peluquero(peluqueria_key, dia_seleccionado, peluquero_id)


def obtener_hora_cierre(peluqueria_key, dia_seleccionado, peluquero=None):
    """Función legacy de compatibilidad"""
    if calendar_utils is None:
        raise RuntimeError("calendar_utils no está inicializado")
    return calendar_utils.obtener_hora_cierre(peluqueria_key, dia_seleccionado, peluquero)


def obtener_turnos_cliente(peluqueria_key, telefono):
    """Función legacy de compatibilidad"""
    if calendar_utils is None:
        raise RuntimeError("calendar_utils no está inicializado")
    return calendar_utils.obtener_turnos_cliente(peluqueria_key, telefono)