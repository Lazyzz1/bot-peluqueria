"""
Manejador de Reservas de Turnos
Gestiona el flujo completo de reserva de turnos
"""

from datetime import datetime, timedelta
from app.bot.utils.formatters import formatear_item_lista, formatear_fecha_espanol
from app.services.whatsapp_service import whatsapp_service
from app.services.calendar_service import CalendarService
from app.utils.time_utils import crear_datetime_local
from app.utils.calendar_utils import CalendarUtils
from app.bot.states.state_manager import get_state, set_state

try:
    from app.core.database import guardar_turno, guardar_cliente
    MONGODB_DISPONIBLE = True
except ImportError:
    MONGODB_DISPONIBLE = False
    def guardar_turno(*args, **kwargs): return None
    def guardar_cliente(*args, **kwargs): return None


class BookingHandler:
    """Manejador del flujo de reserva de turnos"""
    
    def __init__(self, peluquerias_config):
        """
        Inicializa el manejador de reservas
        
        Args:
            peluquerias_config: Diccionario con configuración de clientes
        """
        self.peluquerias = peluquerias_config
        self.calendar_service = CalendarService(peluquerias_config)
        self.calendar_utils = CalendarUtils(peluquerias_config)
    
    def iniciar_reserva(self, numero_limpio, peluqueria_key, numero):
        """
        Inicia el flujo de reserva mostrando los peluqueros disponibles
        
        Args:
            numero_limpio: Número de teléfono sin prefijo whatsapp:
            peluqueria_key: Identificador del cliente
            numero: Número completo con prefijo whatsapp:
        """
        config = self.peluquerias.get(peluqueria_key, {})
        peluqueros = config.get("peluqueros", [])
        
        # Filtrar solo peluqueros activos
        peluqueros_activos = [p for p in peluqueros if p.get("activo", True)]
        
        if not peluqueros or not peluqueros_activos:
            whatsapp_service.enviar_mensaje(
                "😕 No hay peluqueros disponibles en este momento.\n\n"
                "Escribí *menu* para volver.",
                numero
            )
            return
        
        # Cambiar estado a seleccionar peluquero
        estado_usuario = get_state(numero_limpio) or {}
        estado_usuario["paso"] = "seleccionar_peluquero"
        estado_usuario["peluqueros_disponibles"] = peluqueros_activos
        set_state(numero_limpio, estado_usuario)
        
        # Mostrar lista de peluqueros activos
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
        
        # Nota sobre peluqueros no disponibles
        peluqueros_inactivos = [p for p in peluqueros if not p.get("activo", True)]
        nota_inactivos = ""
        
        if peluqueros_inactivos:
            nombres_inactivos = ", ".join([p['nombre'] for p in peluqueros_inactivos])
            nota_inactivos = f"\n\n_⚠️ No disponibles: {nombres_inactivos}_"
            
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
        
        whatsapp_service.enviar_mensaje(mensaje, numero)
    
    def procesar_seleccion_peluquero(self, numero_limpio, texto, peluqueria_key, numero):
        """
        Procesa la selección del peluquero y muestra días disponibles
        
        Args:
            numero_limpio: Número de teléfono sin prefijo
            texto: Opción seleccionada por el usuario
            peluqueria_key: Identificador del cliente
            numero: Número completo con prefijo
        """
        try:
            estado_usuario = get_state(numero_limpio) or {}
            peluqueros = estado_usuario.get("peluqueros_disponibles", [])
            
            # Fallback a config si no hay lista
            if not peluqueros:
                config = self.peluquerias.get(peluqueria_key, {})
                peluqueros = [p for p in config.get("peluqueros", []) if p.get("activo", True)]
            
            index = int(texto) - 1
            
            if 0 <= index < len(peluqueros):
                peluquero_seleccionado = peluqueros[index]
                
                # Verificar que esté activo
                if not peluquero_seleccionado.get("activo", True):
                    whatsapp_service.enviar_mensaje(
                        f"😕 {peluquero_seleccionado['nombre']} no está disponible.\n\n"
                        "Escribí *menu* para elegir otro peluquero.",
                        numero
                    )
                    estado_usuario["paso"] = "menu"
                    set_state(numero_limpio, estado_usuario)
                    return
                
                # Guardar peluquero seleccionado
                estado_usuario["peluquero"] = peluquero_seleccionado
                
                print(f"✅ Peluquero guardado: {peluquero_seleccionado['nombre']}")
                
                # Generar días disponibles
                hoy = datetime.now().date()
                dias = []
                dias_semana_map = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
                
                for i in range(7):
                    dia = hoy + timedelta(days=i)
                    dia_nombre = dias_semana_map[dia.weekday()]
                    
                    if dia_nombre in peluquero_seleccionado.get("dias_trabajo", []):
                        dias.append(dia)
                
                if not dias:
                    whatsapp_service.enviar_mensaje(
                        f"😕 {peluquero_seleccionado['nombre']} no tiene días disponibles esta semana.\n\n"
                        "Escribí *menu* para elegir otro peluquero.",
                        numero
                    )
                    estado_usuario["paso"] = "menu"
                    set_state(numero_limpio, estado_usuario)
                    return
                
                # Guardar días como ISO strings
                estado_usuario["dias"] = [d.isoformat() for d in dias]
                estado_usuario["paso"] = "seleccionar_dia"
                set_state(numero_limpio, estado_usuario)
                
                print(f"✅ Estado cambiado a: seleccionar_dia con {len(dias)} días disponibles")
                
                # Mostrar días
                dias_espanol = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
                lista = "\n".join(
                    formatear_item_lista(i, f"{dias_espanol[d.weekday()]} {d.strftime('%d/%m')}")
                    for i, d in enumerate(dias)
                )
                
                whatsapp_service.enviar_mensaje(
                    f"📅 Días disponibles de *{peluquero_seleccionado['nombre']}*:\n\n{lista}\n\nElegí un número:",
                    numero
                )
            else:
                whatsapp_service.enviar_mensaje("❌ Número inválido. Elegí uno de la lista.", numero)
        
        except ValueError:
            whatsapp_service.enviar_mensaje("❌ Debe ser un número.", numero)
        except Exception as e:
            print(f"❌ Error en procesar_seleccion_peluquero: {e}")
            import traceback
            traceback.print_exc()
            whatsapp_service.enviar_mensaje(
                "❌ Ocurrió un error. Escribí *menu* para reintentar.",
                numero
            )
            estado_usuario = get_state(numero_limpio) or {}
            estado_usuario["paso"] = "menu"
            set_state(numero_limpio, estado_usuario)
    
    def procesar_seleccion_dia(self, numero_limpio, texto, peluqueria_key, numero):
        """
        Procesa la selección del día y muestra horarios disponibles
        
        Args:
            numero_limpio: Número de teléfono sin prefijo
            texto: Opción seleccionada
            peluqueria_key: Identificador del cliente
            numero: Número completo
        """
        try:
            index = int(texto) - 1
            estado_usuario = get_state(numero_limpio) or {}
            dias_iso = estado_usuario.get("dias", [])
            dias = [datetime.fromisoformat(d).date() for d in dias_iso]
            peluquero = estado_usuario.get("peluquero")

            if 0 <= index < len(dias):
                dia_elegido = dias[index]
                
                # Buscar horarios disponibles
                horarios = self.calendar_service.buscar_turnos_disponibles(
                    peluqueria_key,
                    peluquero,
                    dia_elegido
                )

                if not horarios:
                    whatsapp_service.enviar_mensaje(
                        "Ese día no tiene horarios disponibles 😕\n\n"
                        "Escribí *menu* para volver.",
                        numero
                    )
                    return
                
                # Convertir horarios a datetime para el estado
                config = self.peluquerias[peluqueria_key]
                timezone = config["timezone"]
                horarios_dt = []
                for hora_str in horarios:
                    hora_dt = datetime.strptime(hora_str, "%H:%M").time()
                    fecha_hora = crear_datetime_local(
                        dia_elegido.year,
                        dia_elegido.month,
                        dia_elegido.day,
                        hora_dt.hour,
                        hora_dt.minute,
                        timezone
                    )
                    horarios_dt.append(fecha_hora)
                
                # Guardar en estado
                estado_usuario["dia"] = dia_elegido.isoformat()
                estado_usuario["horarios"] = [h.isoformat() for h in horarios_dt]
                estado_usuario["paso"] = "seleccionar_horario"
                set_state(numero_limpio, estado_usuario)

                lista = "\n".join(
                    formatear_item_lista(i, h.strftime('%H:%M'))
                    for i, h in enumerate(horarios_dt)
                )

                mensaje_extra = ""
                if peluquero:
                    mensaje_extra = f"\n👤 Con: *{peluquero['nombre']}*\n"

                whatsapp_service.enviar_mensaje(
                    f"🕒 Horarios disponibles:{mensaje_extra}\n{lista}\n\nElegí un número, o escribí *menu* para volver al Menú",
                    numero
                )
            else:
                whatsapp_service.enviar_mensaje("❌ Número fuera de rango. Elegí uno de la lista.", numero)

        except ValueError:
            whatsapp_service.enviar_mensaje("❌ Debe ser un número.", numero)
    
    def procesar_seleccion_horario(self, numero_limpio, texto, numero):
        """
        Procesa la selección del horario
        
        Args:
            numero_limpio: Número sin prefijo
            texto: Opción seleccionada
            numero: Número completo
        """
        try:
            index = int(texto) - 1
            
            estado_usuario = get_state(numero_limpio) or {}
            horarios_iso = estado_usuario.get("horarios", [])
            horarios = [datetime.fromisoformat(h) for h in horarios_iso]
            
            if 0 <= index < len(horarios):
                fecha_hora = horarios[index]
                
                # Guardar horario seleccionado
                estado_usuario["fecha_hora"] = fecha_hora.isoformat()
                estado_usuario["paso"] = "nombre"
                set_state(numero_limpio, estado_usuario)
            
                whatsapp_service.enviar_mensaje("Perfecto ✂️ ¿A nombre de quién tomo el turno?", numero)
        
        except (ValueError, IndexError):
            whatsapp_service.enviar_mensaje("❌ Número inválido. Elegí uno de la lista.", numero)
    
    def procesar_nombre_cliente(self, numero_limpio, texto, peluqueria_key, numero):
        """
        Procesa el nombre del cliente y muestra servicios
        
        Args:
            numero_limpio: Número sin prefijo
            texto: Nombre ingresado
            peluqueria_key: Identificador del cliente
            numero: Número completo
        """
        estado_usuario = get_state(numero_limpio) or {}
        estado_usuario["cliente"] = texto.title()
        estado_usuario["paso"] = "servicio"
        
        peluquero = estado_usuario.get("peluquero")
        config = self.peluquerias[peluqueria_key]
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
            estado_usuario["servicios_disponibles"] = servicios_a_mostrar
            set_state(numero_limpio, estado_usuario)
            
            mensaje_peluquero = ""
            if peluquero:
                mensaje_peluquero = f"Con *{peluquero['nombre']}*\n\n"
            
            mensaje = (
                "📋 *¿Qué servicio(s) querés?*\n\n"
                f"{mensaje_peluquero}" +
                "\n".join(lista) +
                "\n\n💡 *Podés elegir varios servicios*\n"
                "Ejemplos:\n"
                "• Un servicio: 1\n"
                "• Varios: 1,2 o 1,3\n"
            )
            whatsapp_service.enviar_mensaje(mensaje, numero)
        else:
            whatsapp_service.enviar_mensaje("📋 ¿Qué servicio querés?\nEj: Corte, Tintura, Barba", numero)
    
    def procesar_seleccion_servicio(self, numero_limpio, texto, peluqueria_key, numero):
        """
        Procesa la selección del servicio y crea la reserva
        
        Args:
            numero_limpio: Número sin prefijo
            texto: Servicios seleccionados
            peluqueria_key: Identificador del cliente
            numero: Número completo
        """
        config = self.peluquerias[peluqueria_key]
        estado_usuario = get_state(numero_limpio) or {}
        
        servicios_disponibles = estado_usuario.get("servicios_disponibles", config.get("servicios", []))
        
        # Obtener fecha_hora del estado
        fecha_hora_iso = estado_usuario.get("fecha_hora")
        if not fecha_hora_iso:
            whatsapp_service.enviar_mensaje("❌ Error: No se encontró la fecha seleccionada. Escribí *menu*", numero)
            return
        
        fecha_hora = datetime.fromisoformat(fecha_hora_iso)
        cliente = estado_usuario.get("cliente")
        peluquero = estado_usuario.get("peluquero")
        
        # Parsear servicios seleccionados
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
            whatsapp_service.enviar_mensaje("❌ Servicio no válido.\n\nEscribí *menu* para volver.", numero)
            return
        
        # Crear nombres legibles
        if len(servicios_seleccionados) == 1:
            nombre_servicios = servicios_seleccionados[0]["nombre"]
        else:
            nombre_servicios = " + ".join(s["nombre"] for s in servicios_seleccionados)
        
        precio_total = sum(s["precio"] for s in servicios_seleccionados)
        
        # Validar disponibilidad de tiempo
        dia_iso = estado_usuario.get("dia")
        if dia_iso:
            dia_seleccionado = datetime.fromisoformat(dia_iso).date()
        else:
            dia_seleccionado = fecha_hora.date()
        
        # Obtener hora de cierre
        hora_cierre = self._obtener_hora_cierre(peluqueria_key, dia_seleccionado, peluquero)
        hora_fin_turno = fecha_hora + timedelta(minutes=duracion_total)
        
        if hora_fin_turno > hora_cierre:
            minutos_faltantes = int((hora_fin_turno - hora_cierre).total_seconds() / 60)
            whatsapp_service.enviar_mensaje(
                "⏰ *No hay suficiente tiempo*\n\n"
                f"Los servicios duran *{duracion_total} minutos*\n\n"
                f"📅 Inicio: {fecha_hora.strftime('%H:%M')}\n"
                f"⏱️ Fin: {hora_fin_turno.strftime('%H:%M')}\n"
                f"🔒 Cierre: {hora_cierre.strftime('%H:%M')}\n\n"
                f"❌ Faltan {minutos_faltantes} minutos.\n\n"
                "Escribí *menu* para elegir otro horario.",
                numero
            )
            return
        
        # Crear reserva
        print(f"📅 Creando reserva para {cliente} - {nombre_servicios}")
        
        if self._crear_reserva(
            peluqueria_key,
            fecha_hora,
            cliente,
            servicios_seleccionados,
            duracion_total,
            numero_limpio,
            peluquero
        ):
            fecha_formateada = formatear_fecha_espanol(fecha_hora)
            hora = fecha_hora.strftime("%H:%M")
            
            print("✅ Reserva creada, enviando confirmación...")
            
            # Enviar confirmación
            whatsapp_service.enviar_mensaje(
                "✅ *Turno confirmado*\n\n"
                f"👤 Cliente: {cliente}\n"
                f"📅 Fecha: {fecha_formateada}\n"
                f"🕐 Hora: {hora}\n"
                f"✂️ Servicio(s): {nombre_servicios}\n"
                f"💰 Total: ${precio_total:,}\n\n"
                "¡Te esperamos! 👈".replace(',', '.'),
                numero
            )
            
            # Notificar al peluquero
            if peluquero and peluquero.get("telefono"):
                self._notificar_peluquero(
                    peluquero,
                    cliente,
                    nombre_servicios,
                    fecha_hora,
                    config,
                    numero_limpio
                )
        else:
            whatsapp_service.enviar_mensaje("❌ Error al crear la reserva.\n\nEscribí *menu*", numero)

        estado_usuario["paso"] = "menu"
        set_state(numero_limpio, estado_usuario)
    
    def _obtener_hora_cierre(self, peluqueria_key, dia, peluquero):
        """
        Obtiene la hora de cierre para un día específico
        Usa calendar_utils
        """
        return self.calendar_utils.obtener_hora_cierre(peluqueria_key, dia, peluquero)
    
    def _crear_reserva(self, peluqueria_key, fecha_hora, cliente, servicios, duracion, telefono, peluquero):
        """
        Crea la reserva en Google Calendar y MongoDB
        
        Returns:
            bool: True si se creó exitosamente
        """
        try:
            # Crear evento en Google Calendar
            evento = self.calendar_service.crear_evento_calendario(
                peluqueria_key,
                peluquero,
                cliente,
                telefono,
                fecha_hora,
                duracion
            )
            
            if not evento:
                return False
            
            # Guardar en MongoDB si está disponible
            if MONGODB_DISPONIBLE:
                nombre_servicios = " + ".join(s["nombre"] for s in servicios)
                precio_total = sum(s["precio"] for s in servicios)
                
                guardar_turno(
                    peluqueria_key,
                    evento['id'],
                    fecha_hora,
                    cliente,
                    telefono,
                    nombre_servicios,
                    precio_total,
                    duracion,
                    peluquero.get("nombre") if peluquero else None
                )
                
                guardar_cliente(peluqueria_key, cliente, telefono)
            
            return True
        
        except Exception as e:
            print(f"❌ Error al crear reserva: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _notificar_peluquero(self, peluquero, cliente, servicios, fecha_hora, config, telefono_cliente):
        """Envía notificación al peluquero sobre el nuevo turno"""
        try:
            telefono_peluquero = peluquero.get("telefono")
            if not telefono_peluquero:
                return
            
            fecha_formateada = formatear_fecha_espanol(fecha_hora)
            hora = fecha_hora.strftime("%H:%M")
            telefono_formateado = formatear_telefono(telefono_cliente)
            
            mensaje = (
                f"🆕 *Nuevo turno - {config['nombre']}*\n\n"
                f"👤 Cliente: {cliente}\n"
                f"📱 Teléfono: {telefono_formateado}\n"
                f"📅 Fecha: {fecha_formateada}\n"
                f"🕐 Hora: {hora}\n"
                f"✂️ Servicio: {servicios}"
            )
            
            whatsapp_service.enviar_mensaje(mensaje, f"whatsapp:{telefono_peluquero}")
            print(f"✅ Notificación enviada a {peluquero['nombre']}")
        
        except Exception as e:
            print(f"⚠️ Error al notificar peluquero: {e}")


def formatear_telefono(telefono):
    """
    Formatea teléfono según código de país
    
    Args:
        telefono: +5492974210130, +12624767007, etc.
    
    Returns:
        str: Teléfono formateado legible
    """
    if not telefono:
        return "No disponible"
    
    tel_limpio = str(telefono).replace("whatsapp:", "").strip()
    
    # Argentina con 9 (celular): +54 9 297 4210-130
    if tel_limpio.startswith("+549"):
        codigo_area = tel_limpio[4:7]
        primera = tel_limpio[7:11]
        segunda = tel_limpio[11:]
        return f"+54 9 {codigo_area} {primera}-{segunda}"
    
    # Argentina sin 9 (fijo)
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
    
    return tel_limpio