"""
Manejador de Cancelación de Turnos
Gestiona el flujo completo de cancelación de turnos
"""

from datetime import datetime
from app.bot.utils.formatters import formatear_item_lista
from app.services.whatsapp_service import whatsapp_service
from app.services.calendar_service import CalendarService
from app.bot.states.state_manager import get_state, set_state

try:
    from app.core.database import cancelar_turno_db, obtener_turnos_por_telefono
    MONGODB_DISPONIBLE = True
except ImportError:
    MONGODB_DISPONIBLE = False
    def cancelar_turno_db(*args, **kwargs): return False
    def obtener_turnos_por_telefono(*args, **kwargs): return []


class CancellationHandler:
    """Manejador del flujo de cancelación de turnos"""
    
    def __init__(self, peluquerias_config):
        """
        Inicializa el manejador de cancelación
        
        Args:
            peluquerias_config: Diccionario con configuración de clientes
        """
        self.peluquerias = peluquerias_config
        self.calendar_service = CalendarService(peluquerias_config)
    
    def iniciar_cancelacion(self, numero_limpio, peluqueria_key, numero):
        """
        Inicia el flujo de cancelación mostrando los turnos del cliente
        
        Args:
            numero_limpio: Número de teléfono sin prefijo whatsapp:
            peluqueria_key: Identificador del cliente
            numero: Número completo con prefijo whatsapp:
        """
        try:
            turnos = self._obtener_turnos_cliente(peluqueria_key, numero_limpio)
            
            if not turnos:
                whatsapp_service.enviar_mensaje(
                    "🔭 No tenés turnos para cancelar.\n\n"
                    "Escribí *menu* para volver.",
                    numero
                )
                return
            
            # Guardar turnos en estado
            estado_usuario = get_state(numero_limpio) or {}
            
            # Convertir turnos a formato serializable
            turnos_serializables = []
            for turno in turnos:
                turnos_serializables.append({
                    "id": turno["id"],
                    "resumen": turno["resumen"],
                    "inicio": turno["inicio"].isoformat()
                })
            
            estado_usuario["turnos"] = turnos_serializables
            estado_usuario["paso"] = "seleccionar_turno_cancelar"
            set_state(numero_limpio, estado_usuario)
            
            # Formatear lista de turnos
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
            whatsapp_service.enviar_mensaje(mensaje, numero)
            
        except Exception as e:
            print(f"❌ Error en iniciar_cancelacion: {e}")
            import traceback
            traceback.print_exc()
            whatsapp_service.enviar_mensaje(
                "❌ Hubo un error al buscar tus turnos.\n\n"
                "Por favor intentá de nuevo escribiendo *menu*",
                numero
            )
    
    def procesar_seleccion_turno(self, numero_limpio, texto, peluqueria_key, numero):
        """
        Procesa la selección del turno a cancelar
        
        Args:
            numero_limpio: Número sin prefijo
            texto: Opción seleccionada
            peluqueria_key: Identificador del cliente
            numero: Número completo
        """
        try:
            config = self.peluquerias.get(peluqueria_key, {})
            print(f"🔍 [{config.get('nombre', peluqueria_key)}] Usuario {numero_limpio} cancelando turno")
            
            if texto == "0":
                print("   ↳ Cancelación abortada")
                
                estado_usuario = get_state(numero_limpio) or {}
                estado_usuario["paso"] = "menu"
                set_state(numero_limpio, estado_usuario)
                
                whatsapp_service.enviar_mensaje("✅ Cancelación abortada. Escribí *menu* para volver.", numero)
                return
            
            try:
                index = int(texto) - 1
                print(f"   ↳ Seleccionó turno #{index + 1}")
            except ValueError:
                print(f"   ↳ Entrada inválida: '{texto}'")
                whatsapp_service.enviar_mensaje("❌ Debe ser un número. Elegí uno de la lista o 0 para volver.", numero)
                return
            
            # Obtener turnos del estado
            estado_usuario = get_state(numero_limpio) or {}
            turnos_serializados = estado_usuario.get("turnos", [])
            
            if index < 0 or index >= len(turnos_serializados):
                print(f"   ↳ Índice fuera de rango: {index}")
                whatsapp_service.enviar_mensaje("❌ Número inválido. Elegí uno de la lista.", numero)
                return
            
            turno_seleccionado = turnos_serializados[index]
            
            # Guardar turno a cancelar en estado
            estado_usuario["turno_a_cancelar"] = turno_seleccionado
            estado_usuario["paso"] = "confirmar_cancelacion"
            set_state(numero_limpio, estado_usuario)
            
            try:
                # Convertir fecha de ISO string a datetime
                inicio = datetime.fromisoformat(turno_seleccionado["inicio"])
                
                fecha = inicio.strftime("%d/%m/%Y")
                hora = inicio.strftime("%H:%M")
                resumen = turno_seleccionado.get("resumen", "Turno")
                
                print(f"   ↳ Pidiendo confirmación para: {fecha} {hora}")
            except Exception as e:
                print(f"❌ Error formateando fecha del turno: {e}")
                whatsapp_service.enviar_mensaje(
                    "❌ Error al procesar el turno.\n\n"
                    "Escribí *menu* para volver.",
                    numero
                )
                return
            
            whatsapp_service.enviar_mensaje(
                "⚠️ ¿Estás seguro de cancelar el turno?\n\n"
                f"📅 {fecha} a las {hora}\n"
                f"✂️ {resumen}\n\n"
                "Escribí *SI* para confirmar o *NO* para cancelar",
                numero
            )
            
        except Exception as e:
            print(f"❌ Error en procesar_seleccion_turno: {e}")
            import traceback
            traceback.print_exc()
            whatsapp_service.enviar_mensaje(
                "❌ Error al procesar la cancelación.\n\n"
                "Escribí *menu* para volver.",
                numero
            )
    
    def procesar_confirmacion(self, numero_limpio, texto, peluqueria_key, numero):
        """
        Procesa la confirmación de la cancelación
        
        Args:
            numero_limpio: Número sin prefijo
            texto: Respuesta del usuario (SI/NO)
            peluqueria_key: Identificador del cliente
            numero: Número completo
        """
        try:
            config = self.peluquerias.get(peluqueria_key, {})
            estado_usuario = get_state(numero_limpio) or {}
            
            if texto.upper() == "SI":
                turno = estado_usuario.get("turno_a_cancelar")
                if not turno:
                    whatsapp_service.enviar_mensaje(
                        "❌ No se encontró el turno a cancelar.\n\n"
                        "Escribí *menu* para volver.",
                        numero
                    )
                    return
                
                evento_id = turno.get("id")
                print(f"🗑️ Cancelando evento {evento_id}")
                
                # Cancelar en Google Calendar
                exito_calendar = self.calendar_service.cancelar_evento_calendario(
                    peluqueria_key,
                    evento_id
                )
                
                # Cancelar en MongoDB si está disponible
                if MONGODB_DISPONIBLE:
                    cancelar_turno_db(peluqueria_key, evento_id)
                
                if exito_calendar:
                    inicio = datetime.fromisoformat(turno["inicio"])
                    fecha = inicio.strftime("%d/%m/%Y")
                    hora = inicio.strftime("%H:%M")
                    
                    whatsapp_service.enviar_mensaje(
                        f"✅ Turno cancelado exitosamente\n\n"
                        f"📅 {fecha} a las {hora}\n\n"
                        f"Podés pedir un nuevo turno cuando quieras.\n\n"
                        f"Escribí *menu* para volver.",
                        numero
                    )
                    print(f"✅ Turno cancelado: {evento_id}")
                else:
                    whatsapp_service.enviar_mensaje(
                        "❌ No se pudo cancelar el turno.\n\n"
                        "Por favor contactá directamente con nosotros.\n\n"
                        "Escribí *menu* para volver.",
                        numero
                    )
                    print(f"❌ Error al cancelar turno: {evento_id}")
            
            elif texto.upper() == "NO":
                whatsapp_service.enviar_mensaje(
                    "✅ Cancelación abortada.\n\n"
                    "Tu turno sigue activo.\n\n"
                    "Escribí *menu* para volver.",
                    numero
                )
                print(f"↩️ Cancelación abortada por el usuario")
            
            else:
                whatsapp_service.enviar_mensaje(
                    "❌ Respuesta no válida.\n\n"
                    "Escribí *SI* para confirmar o *NO* para cancelar.",
                    numero
                )
                return
            
            # Resetear estado
            estado_usuario["paso"] = "menu"
            estado_usuario.pop("turno_a_cancelar", None)
            set_state(numero_limpio, estado_usuario)
            
        except Exception as e:
            print(f"❌ Error en procesar_confirmacion: {e}")
            import traceback
            traceback.print_exc()
            whatsapp_service.enviar_mensaje(
                "❌ Error al procesar la confirmación.\n\n"
                "Escribí *menu* para volver.",
                numero
            )
    
    def _obtener_turnos_cliente(self, peluqueria_key, telefono):
        """
        Obtiene los turnos de un cliente desde Google Calendar
        
        Args:
            peluqueria_key: Identificador del cliente
            telefono: Número de teléfono del cliente
        
        Returns:
            list: Lista de turnos del cliente
        """
        try:
            # Intentar obtener de MongoDB primero
            if MONGODB_DISPONIBLE:
                turnos_db = obtener_turnos_por_telefono(peluqueria_key, telefono)
                if turnos_db:
                    return turnos_db
            
            # Fallback a Google Calendar
            config = self.peluquerias[peluqueria_key]
            calendar_id = config["calendar_id"]
            service = self.calendar_service.get_calendar_service(peluqueria_key)
            
            # Buscar eventos próximos
            ahora = datetime.now()
            eventos = service.events().list(
                calendarId=calendar_id,
                timeMin=ahora.isoformat(),
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            turnos = []
            for evento in eventos.get('items', []):
                descripcion = evento.get('description', '')
                if telefono in descripcion:
                    inicio_str = evento['start'].get('dateTime', evento['start'].get('date'))
                    inicio = datetime.fromisoformat(inicio_str.replace('Z', '+00:00'))
                    
                    turnos.append({
                        'id': evento['id'],
                        'resumen': evento.get('summary', 'Turno'),
                        'inicio': inicio
                    })
            
            return turnos
        
        except Exception as e:
            print(f"❌ Error al obtener turnos: {e}")
            return []