"""
Manejador de Información
Gestiona FAQ, ubicación, servicios y reagendar
"""

from app.services.whatsapp_service import whatsapp_service
from app.bot.utils.formatters import formatear_fecha_espanol
from app.utils.calendar_utils import CalendarUtils
from app.bot.states.state_manager import get_state, set_state


class InfoHandler:
    """Manejador de información general y ayuda"""
    
    def __init__(self, peluquerias_config):
        """
        Inicializa el manejador de información
        
        Args:
            peluquerias_config: Diccionario con configuración de clientes
        """
        self.peluquerias = peluquerias_config
        self.calendar_utils = CalendarUtils(peluquerias_config)
    
    def procesar_servicios(self, peluqueria_key, numero):
        """
        Muestra los servicios disponibles de la peluquería
        
        Args:
            peluqueria_key: Identificador del cliente
            numero: Número de WhatsApp del usuario
        """
        config = self.peluquerias.get(peluqueria_key, {})
        servicios = config.get("servicios", [])
        
        if not servicios:
            whatsapp_service.enviar_mensaje(
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
            whatsapp_service.enviar_mensaje(mensaje, numero)
    
    def procesar_faq(self, numero, peluqueria_key=None):
        """
        Muestra preguntas frecuentes
        Puede ser personalizado por peluquería si se proporciona peluqueria_key
        
        Args:
            numero: Número de WhatsApp del usuario
            peluqueria_key: Identificador del cliente (opcional)
        """
        # Verificar si hay FAQs personalizadas
        faqs_custom = None
        if peluqueria_key:
            config = self.peluquerias.get(peluqueria_key, {})
            faqs_custom = config.get("faq")
        
        if faqs_custom:
            # Usar FAQs personalizadas
            mensaje_partes = ["📖 *Preguntas Frecuentes:*\n"]
            for faq in faqs_custom:
                pregunta = faq.get("pregunta", "")
                respuesta = faq.get("respuesta", "")
                mensaje_partes.append(f"*{pregunta}*\n{respuesta}\n")
            
            mensaje_partes.append("Escribí *menu* para volver")
            mensaje = "\n".join(mensaje_partes)
        else:
            # FAQs por defecto
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
        
        whatsapp_service.enviar_mensaje(mensaje, numero)
    
    def procesar_ubicacion(self, peluqueria_key, numero):
        """
        Muestra ubicación y contacto de la peluquería
        
        Args:
            peluqueria_key: Identificador del cliente
            numero: Número de WhatsApp del usuario
        """
        config = self.peluquerias.get(peluqueria_key, {})
        nombre = config.get("nombre", "Peluquería")
        
        # Obtener datos de ubicación de la config
        ubicacion = config.get("ubicacion", {})
        direccion = ubicacion.get("direccion", "Dirección no disponible")
        telefono = ubicacion.get("telefono", "Teléfono no disponible")
        maps_url = ubicacion.get("maps_url")
        
        # Construir mensaje de horarios
        horarios_config = config.get("horarios", {})
        if horarios_config:
            horarios_texto = self._formatear_horarios(horarios_config)
        else:
            horarios_texto = """Lunes a Viernes: 08:00 - 21:00
Sábados: 08:00 - 19:00
Domingos: Cerrado"""
        
        # Construir mensaje completo
        mensaje = f"""📍 *Ubicación de {nombre}:*

Dirección: {direccion}

🕒 *Horarios:*
{horarios_texto}

📞 *Contacto:*
Teléfono: {telefono}"""
        
        # Agregar link de Google Maps si está disponible
        if maps_url:
            mensaje += f"\n\n🗺️ Ver en Google Maps:\n{maps_url}"
        
        mensaje += "\n\nEscribí *menu* para volver"
        
        whatsapp_service.enviar_mensaje(mensaje, numero)
    
    def procesar_reagendar_inicio(self, numero_limpio, peluqueria_key, numero):
        """
        Inicia el flujo de reagendar turno
        
        Args:
            numero_limpio: Número sin prefijo whatsapp:
            peluqueria_key: Identificador del cliente
            numero: Número completo con prefijo
        """
        turnos = self.calendar_utils.obtener_turnos_cliente(peluqueria_key, numero_limpio)
        
        if not turnos:
            whatsapp_service.enviar_mensaje(
                "🔭 No tenés turnos para reagendar.\n\nEscribí *menu* para volver.",
                numero
            )
        else:
            # Guardar en Redis con serialización
            estado_usuario = get_state(numero_limpio) or {}
            
            # Serializar turnos (datetime → ISO string)
            turnos_serializables = []
            for turno in turnos:
                turnos_serializables.append({
                    "id": turno["id"],
                    "resumen": turno["resumen"],
                    "inicio": turno["inicio"].isoformat()
                })
            
            estado_usuario["turnos"] = turnos_serializables
            estado_usuario["paso"] = "seleccionar_turno_reagendar"
            set_state(numero_limpio, estado_usuario)
            
            # Formatear lista de turnos
            lista = []
            for i, turno in enumerate(turnos):
                fecha = formatear_fecha_espanol(turno["inicio"])
                hora = turno["inicio"].strftime("%H:%M")
                lista.append(f"{i+1}️⃣ {fecha} a las {hora}")
            
            mensaje = "🔄 *Selecciona el turno a reagendar:*\n\n" + "\n".join(lista)
            whatsapp_service.enviar_mensaje(mensaje, numero)
    
    def procesar_seleccion_turno_reagendar(self, numero_limpio, texto, numero):
        """
        Procesa la selección del turno a reagendar
        
        Args:
            numero_limpio: Número sin prefijo
            texto: Opción seleccionada por el usuario
            numero: Número completo
        """
        try:
            opcion = int(texto) - 1
            
            # Obtener de Redis
            estado_usuario = get_state(numero_limpio) or {}
            turnos = estado_usuario.get("turnos", [])
            
            if opcion < 0 or opcion >= len(turnos):
                whatsapp_service.enviar_mensaje(
                    "❌ Opción inválida. Elegí un número de la lista.",
                    numero
                )
                return
            
            turno_seleccionado = turnos[opcion]
            
            # Guardar en Redis
            estado_usuario["turno_a_reagendar"] = turno_seleccionado
            estado_usuario["paso"] = "menu"
            set_state(numero_limpio, estado_usuario)
            
            whatsapp_service.enviar_mensaje(
                "ℹ️ Para reagendar:\n\n"
                "1️⃣ Primero cancelá tu turno actual (opción 3)\n"
                "2️⃣ Luego pedí uno nuevo (opción 1)\n\n"
                "Escribí *menu* para volver",
                numero
            )
        
        except ValueError:
            whatsapp_service.enviar_mensaje(
                "❌ Enviá solo el número del turno.",
                numero
            )
    
    def procesar_ver_turnos(self, numero_limpio, peluqueria_key, numero):
        """
        Muestra los turnos del cliente
        
        Args:
            numero_limpio: Número sin prefijo
            peluqueria_key: Identificador del cliente
            numero: Número completo
        """
        turnos = self.calendar_utils.obtener_turnos_cliente(peluqueria_key, numero_limpio)
        
        if not turnos:
            whatsapp_service.enviar_mensaje(
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
            whatsapp_service.enviar_mensaje(mensaje, numero)
    
    def _formatear_horarios(self, horarios_config):
        """
        Formatea los horarios de la peluquería para mostrar
        
        Args:
            horarios_config: Diccionario con horarios por día
        
        Returns:
            str: Horarios formateados
        """
        dias_español = {
            'lunes': 'Lunes',
            'martes': 'Martes',
            'miercoles': 'Miércoles',
            'jueves': 'Jueves',
            'viernes': 'Viernes',
            'sabado': 'Sábado',
            'domingo': 'Domingo'
        }
        
        horarios_texto = []
        
        # Agrupar días con el mismo horario
        horarios_agrupados = {}
        for dia, horario in horarios_config.items():
            if isinstance(horario, list) and len(horario) >= 2:
                # Formato simple o partidos
                if isinstance(horario[0], list):
                    # Horarios partidos: [["09:00", "13:00"], ["15:00", "19:00"]]
                    horario_str = " y ".join([f"{h[0]} - {h[1]}" for h in horario])
                else:
                    # Formato simple: ["09:00", "18:00"]
                    horario_str = f"{horario[0]} - {horario[1]}"
                
                if horario_str not in horarios_agrupados:
                    horarios_agrupados[horario_str] = []
                horarios_agrupados[horario_str].append(dia)
        
        # Formatear salida
        for horario_str, dias in horarios_agrupados.items():
            dias_formateados = [dias_español.get(d, d.capitalize()) for d in dias]
            
            if len(dias_formateados) > 2:
                # Varios días: "Lunes a Viernes"
                dias_texto = f"{dias_formateados[0]} a {dias_formateados[-1]}"
            else:
                # Pocos días: "Lunes y Martes"
                dias_texto = " y ".join(dias_formateados)
            
            horarios_texto.append(f"{dias_texto}: {horario_str}")
        
        # Verificar si domingo está cerrado (no en config)
        if 'domingo' not in horarios_config:
            horarios_texto.append("Domingos: Cerrado")
        
        return "\n".join(horarios_texto)


# Instancia global (se inicializa desde app/__init__.py)
info_handler = None


def inicializar_info_handler(peluquerias_config):
    """Inicializa el manejador de información globalmente"""
    global info_handler
    info_handler = InfoHandler(peluquerias_config)
    return info_handler