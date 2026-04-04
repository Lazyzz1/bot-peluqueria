"""
Servicio de Notificaciones y Recordatorios
Gestiona recordatorios automáticos y notificaciones
"""

import threading
import time
from datetime import datetime, timedelta
import json
import os
from threading import Lock
from app.services.whatsapp_service import whatsapp_service
from app.services.calendar_service import CalendarService
from app.bot.utils.formatters import formatear_fecha_espanol
from app.utils.time_utils import ahora_local
from app.bot.states.state_manager import get_state

try:
    from app.core.database import (
        obtener_turnos_proximos_db,
        marcar_recordatorio_enviado,
        recordatorio_ya_enviado
    )
    MONGODB_DISPONIBLE = True
except ImportError:
    MONGODB_DISPONIBLE = False
    def obtener_turnos_proximos_db(*args, **kwargs): return []
    def marcar_recordatorio_enviado(*args, **kwargs): return False
    def recordatorio_ya_enviado(*args, **kwargs): return False

# Redis para deduplicacion de recordatorios (sobrevive reinicios de Railway)
try:
    from app.bot.states.state_manager import redis_client as _redis
    REDIS_DISPONIBLE = True
except Exception:
    _redis = None
    REDIS_DISPONIBLE = False

def _recordatorio_ya_enviado_redis(recordatorio_id: str) -> bool:
    """Verifica en Redis si ya se envio este recordatorio."""
    if not REDIS_DISPONIBLE or not _redis:
        return False
    try:
        return bool(_redis.exists(f"rec:{recordatorio_id}"))
    except Exception:
        return False

def _marcar_recordatorio_redis(recordatorio_id: str):
    """Marca en Redis que este recordatorio fue enviado. Expira en 48hs."""
    if not REDIS_DISPONIBLE or not _redis:
        return
    try:
        _redis.setex(f"rec:{recordatorio_id}", 172800, "1")  # 48hs en segundos
    except Exception as e:
        print(f"Advertencia: no se pudo marcar recordatorio en Redis: {e}")


class NotificationService:
    """Servicio para gestionar notificaciones y recordatorios"""
    
    def __init__(self, peluquerias_config, templates_config=None):
        """
        Inicializa el servicio de notificaciones
        
        Args:
            peluquerias_config: Diccionario con configuración de clientes
            templates_config: Configuración de plantillas de Twilio
        """
        self.peluquerias = peluquerias_config
        self.calendar_service = CalendarService(peluquerias_config)
        self.templates = templates_config or {}
        
        # Cache en memoria como fallback si Redis no está disponible
        self.recordatorios_enviados = set()
        self.recordatorios_lock = Lock()
        
        # Archivo para persistencia (fallback si Redis no disponible)
        self.archivo_recordatorios = "recordatorios_enviados.json"
        
        if REDIS_DISPONIBLE:
            print("   ✅ Recordatorios: usando Redis (persistente entre reinicios)")
        else:
            print("   ⚠️  Recordatorios: usando archivo JSON (se pierde al reiniciar)")
            self._cargar_recordatorios_enviados()
    
    def _cargar_recordatorios_enviados(self):
        """Carga los recordatorios enviados desde archivo JSON"""
        if os.path.exists(self.archivo_recordatorios):
            try:
                with open(self.archivo_recordatorios, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                    with self.recordatorios_lock:
                        self.recordatorios_enviados = set(datos)
                print(f"📂 Cargados {len(self.recordatorios_enviados)} recordatorios previos")
            except json.JSONDecodeError:
                print("⚠️ Archivo corrupto, creando backup...")
                os.rename(self.archivo_recordatorios, f"{self.archivo_recordatorios}.backup")
            except Exception as e:
                print(f"⚠️ Error cargando recordatorios: {e}")
    
    def _guardar_recordatorios_enviados(self):
        """Guarda los recordatorios enviados en archivo JSON"""
        try:
            with self.recordatorios_lock:
                with open(self.archivo_recordatorios, "w", encoding="utf-8") as f:
                    json.dump(list(self.recordatorios_enviados), f, indent=2)
        except Exception as e:
            print(f"❌ Error guardando recordatorios: {e}")
    
    def obtener_turnos_proximos(self, peluqueria_key, horas_anticipacion=24):
        """
        Obtiene turnos que ocurrirán en X horas
        
        Args:
            peluqueria_key: Identificador del cliente
            horas_anticipacion: Horas de anticipación (24 o 2)
        
        Returns:
            list: Lista de turnos próximos
        """
        try:
            # Intentar obtener de MongoDB primero
            if MONGODB_DISPONIBLE:
                turnos_db = obtener_turnos_proximos_db(peluqueria_key, horas_anticipacion)
                if turnos_db:
                    return turnos_db
            
            # Fallback a Google Calendar
            config = self.peluquerias.get(peluqueria_key, {})
            if not config:
                return []
            
            timezone = config.get("timezone", "America/Argentina/Buenos_Aires")
            calendar_id = config.get("calendar_id")
            
            if not calendar_id:
                return []
            
            service = self.calendar_service.get_calendar_service(peluqueria_key)
            
            # Calcular ventana de tiempo
            ahora = ahora_local(peluqueria_key, self.peluquerias)
            tiempo_inicio = ahora + timedelta(hours=horas_anticipacion - 1)
            tiempo_fin = ahora + timedelta(hours=horas_anticipacion + 1)
            
            # Obtener eventos del calendario
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
                        inicio_str = event["start"].get("dateTime")
                        if not inicio_str:
                            continue
                        
                        # Parsear fecha con timezone
                        if inicio_str.endswith('Z'):
                            inicio = datetime.fromisoformat(inicio_str.replace("Z", "+00:00"))
                        else:
                            inicio = datetime.fromisoformat(inicio_str)
                        
                        # Extraer teléfono de la descripción
                        descripcion = event.get("description", "")
                        telefono = None
                        for linea in descripcion.split("\n"):
                            if "Tel:" in linea or "Teléfono:" in linea:
                                telefono = linea.split(":")[-1].strip()
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
    
    def enviar_recordatorio(self, turno, horas_anticipacion=24):
        """
        Envía un recordatorio de turno al cliente
        
        Args:
            turno: Diccionario con información del turno
            horas_anticipacion: 24 o 2 horas
        
        Returns:
            bool: True si se envió exitosamente
        """
        try:
            telefono = turno["telefono"]
            peluqueria_key = turno.get("peluqueria")
            
            # Verificar si ya se envió (MongoDB)
            if MONGODB_DISPONIBLE:
                turno_id = turno.get("_id") or turno.get("id")
                tipo_recordatorio = "24h" if horas_anticipacion == 24 else "2h"
                if recordatorio_ya_enviado(turno_id, tipo_recordatorio):
                    print(f"⏭️ Recordatorio ya enviado para {turno_id}")
                    return False
            
            # Verificar si el usuario tiene recordatorios activos
            estado_usuario = get_state(telefono)
            if estado_usuario:
                if not estado_usuario.get("recordatorios_activos", True):
                    print(f"⏭️ Usuario {telefono} tiene recordatorios desactivados")
                    return False
            
            # Formatear datos
            fecha = formatear_fecha_espanol(turno["inicio"])
            hora = turno["inicio"].strftime("%H:%M")
            
            # Extraer información del resumen
            resumen = turno.get("resumen", "Turno")
            partes = resumen.split(" - ")
            
            # Intentar extraer servicio y nombre
            if len(partes) >= 2:
                servicio = partes[-2] if len(partes) >= 3 else partes[0]
            else:
                servicio = "Tu servicio"
            
            if len(partes) >= 3:
                nombre_cliente = partes[-1]
            else:
                nombre_cliente = "Cliente"
            
            # Calcular tiempo restante
            ahora = ahora_local(peluqueria_key, self.peluquerias)
            diferencia = turno["inicio"] - ahora
            horas_faltantes = int(diferencia.total_seconds() / 3600)
            
            print(f"📤 Enviando recordatorio a {telefono} ({horas_faltantes}h antes)")
            
            # Enviar según tipo de recordatorio
            if horas_anticipacion == 24:
                # Usar plantilla si está configurada
                template_sid = self.templates.get("TEMPLATE_RECORDATORIO")
                if template_sid:
                    resultado = whatsapp_service.enviar_con_plantilla(
                        telefono=telefono,
                        content_sid=template_sid,
                        variables={
                            "1": nombre_cliente,
                            "2": fecha,
                            "3": hora,
                            "4": servicio
                        }
                    )
                else:
                    # Mensaje normal
                    mensaje = (
                        f"⏰ *Recordatorio de turno*\n\n"
                        f"👤 {nombre_cliente}\n"
                        f"📅 Fecha: {fecha}\n"
                        f"🕐 Hora: {hora}\n"
                        f"✂️ Servicio: {servicio}\n\n"
                        f"¡Te esperamos mañana! 👈"
                    )
                    resultado = whatsapp_service.enviar_mensaje(mensaje, telefono)
                
                if resultado:
                    print("✅ Recordatorio 24h enviado")
            
            elif horas_anticipacion == 2:
                mensaje = (
                    f"⏰ *Recordatorio urgente*\n\n"
                    f"Tu turno es en {horas_faltantes} horas:\n\n"
                    f"🕐 Hora: {hora}\n"
                    f"✂️ {servicio}\n\n"
                    f"¡Nos vemos pronto! 👈"
                )
                resultado = whatsapp_service.enviar_mensaje(mensaje, telefono)
                
                if resultado:
                    print("✅ Recordatorio 2h enviado")
            
            # Marcar como enviado en MongoDB
            if resultado and MONGODB_DISPONIBLE:
                turno_id = turno.get("_id") or turno.get("id")
                tipo_recordatorio = "24h" if horas_anticipacion == 24 else "2h"
                marcar_recordatorio_enviado(turno_id, tipo_recordatorio)
                print("✅ Recordatorio marcado en MongoDB")
            
            return resultado
        
        except Exception as e:
            print(f"❌ Error enviando recordatorio: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _ya_enviado(self, recordatorio_id: str) -> bool:
        """Verifica si ya se envio un recordatorio. Redis > MongoDB > memoria."""
        # 1. Redis (persiste entre reinicios)
        if _recordatorio_ya_enviado_redis(recordatorio_id):
            return True
        # 2. Memoria in-process (fallback)
        with self.recordatorios_lock:
            return recordatorio_id in self.recordatorios_enviados

    def _marcar_enviado(self, recordatorio_id: str):
        """Marca un recordatorio como enviado en Redis y en memoria."""
        _marcar_recordatorio_redis(recordatorio_id)
        with self.recordatorios_lock:
            self.recordatorios_enviados.add(recordatorio_id)
        self._guardar_recordatorios_enviados()

    def sistema_recordatorios_loop(self):
        """
        Loop principal del sistema de recordatorios
        Se ejecuta en un thread separado
        """
        print("📢 Sistema de recordatorios iniciado")
        
        while True:
            try:
                # Obtener hora actual para logging
                print(f"\n⏰ Verificando turnos próximos...")
                
                # Verificar TODAS las peluquerías
                for peluqueria_key in self.peluquerias.keys():
                    try:
                        config = self.peluquerias[peluqueria_key]
                        print(f"   Verificando {config['nombre']}...")
                        
                        # Recordatorios de 24 horas
                        turnos_24h = self.obtener_turnos_proximos(peluqueria_key, horas_anticipacion=24)
                        for turno in turnos_24h:
                            recordatorio_id = f"{turno['id']}_24h"
                            if self._ya_enviado(recordatorio_id):
                                continue
                            if self.enviar_recordatorio(turno, horas_anticipacion=24):
                                self._marcar_enviado(recordatorio_id)
                                print(f"   📤 Recordatorio 24h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")

                        # Recordatorios de 2 horas
                        turnos_2h = self.obtener_turnos_proximos(peluqueria_key, horas_anticipacion=2)
                        for turno in turnos_2h:
                            recordatorio_id = f"{turno['id']}_2h"
                            if self._ya_enviado(recordatorio_id):
                                continue
                            if self.enviar_recordatorio(turno, horas_anticipacion=2):
                                self._marcar_enviado(recordatorio_id)
                                print(f"   📤 Recordatorio 2h enviado para turno {turno['inicio'].strftime('%d/%m %H:%M')}")
                    
                    except Exception as e:
                        print(f"   ❌ Error procesando {peluqueria_key}: {e}")
                        continue
                
                print("   ✅ Verificación completada. Próxima en 1 hora.")
                
                # Limpiar recordatorios antiguos
                with self.recordatorios_lock:
                    if len(self.recordatorios_enviados) > 1000:
                        self.recordatorios_enviados.clear()
                        self._guardar_recordatorios_enviados()
                        print("   🗑️ Limpieza de cache completada")
            
            except Exception as e:
                print(f"   ❌ Error en sistema de recordatorios: {e}")
                import traceback
                traceback.print_exc()
            
            # Esperar 1 hora
            time.sleep(3600)
    
    def iniciar_sistema_recordatorios(self):
        """
        Inicia el sistema de recordatorios en un thread separado
        """
        hilo_recordatorios = threading.Thread(
            target=self.sistema_recordatorios_loop,
            daemon=True,
            name="RecordatoriosThread"
        )
        hilo_recordatorios.start()
        print("✅ Sistema de recordatorios activado en background")
        return hilo_recordatorios
    
    def notificar_peluquero(self, peluquero, cliente, servicio, fecha_hora, config, telefono_cliente):
        """
        Envía notificación al peluquero sobre nuevo turno
        
        Args:
            peluquero: Diccionario con datos del peluquero
            cliente: Nombre del cliente
            servicio: Servicio reservado
            fecha_hora: Datetime del turno
            config: Configuración de la peluquería
            telefono_cliente: Teléfono del cliente
        
        Returns:
            bool: True si se envió exitosamente
        """
        try:
            telefono_peluquero = peluquero.get("telefono")
            
            if not telefono_peluquero:
                print(f"⚠️ Peluquero {peluquero['nombre']} no tiene teléfono configurado")
                return False
            
            # Formatear datos
            fecha_formateada = formatear_fecha_espanol(fecha_hora)
            hora = fecha_hora.strftime("%H:%M")
            telefono_formateado = self._formatear_telefono(telefono_cliente)
            
            # Crear mensaje
            mensaje = (
                f"🆕 *Nuevo turno - {config['nombre']}*\n\n"
                f"👤 Cliente: {cliente}\n"
                f"📱 Teléfono: {telefono_formateado}\n"
                f"📅 Fecha: {fecha_formateada}\n"
                f"🕐 Hora: {hora}\n"
                f"✂️ Servicio: {servicio}"
            )
            
            print(f"📱 Notificando a {peluquero['nombre']}")
            resultado = whatsapp_service.enviar_mensaje(mensaje, telefono_peluquero)
            
            if resultado:
                print("✅ Notificación enviada al peluquero")
            
            return resultado
        
        except Exception as e:
            print(f"❌ Error notificando peluquero: {e}")
            return False
    
    def _formatear_telefono(self, telefono):
        """Formatea teléfono para mostrar"""
        if not telefono:
            return "No disponible"
        
        tel_limpio = str(telefono).replace("whatsapp:", "").strip()
        
        # Argentina con 9
        if tel_limpio.startswith("+549"):
            codigo_area = tel_limpio[4:7]
            primera = tel_limpio[7:11]
            segunda = tel_limpio[11:]
            return f"+54 9 {codigo_area} {primera}-{segunda}"
        
        # Argentina sin 9
        elif tel_limpio.startswith("+54"):
            codigo_area = tel_limpio[3:6]
            primera = tel_limpio[6:10]
            segunda = tel_limpio[10:]
            return f"+54 {codigo_area} {primera}-{segunda}"
        
        # USA
        elif tel_limpio.startswith("+1"):
            area = tel_limpio[2:5]
            primera = tel_limpio[5:8]
            segunda = tel_limpio[8:]
            return f"+1 ({area}) {primera}-{segunda}"
        
        return tel_limpio


# Instancia global del servicio (se inicializa desde app/__init__.py)
notification_service = None


def inicializar_notification_service(peluquerias_config, templates_config=None):
    """Inicializa el servicio de notificaciones global"""
    global notification_service
    notification_service = NotificationService(peluquerias_config, templates_config)
    return notification_service