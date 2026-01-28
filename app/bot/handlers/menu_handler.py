"""
Manejador del menú principal del bot
"""
from app.services.whatsapp_service import whatsapp_service
from app.bot.states.state_manager import get_state, set_state


class MenuHandler:
    """Maneja las opciones del menú principal"""
    
    def __init__(self, peluquerias):
        """
        Args:
            peluquerias (dict): Configuración de peluquerías
        """
        self.peluquerias = peluquerias
    
    def mostrar_menu(self, numero, peluqueria_key):
        """
        Muestra el menú principal
        
        Args:
            numero (str): Número de WhatsApp
            peluqueria_key (str): ID de la peluquería
        """
        config = self.peluquerias.get(peluqueria_key, {})
        nombre = config.get("nombre", "Peluquería")
        
        whatsapp_service.enviar_menu_principal(numero, nombre)
    
    def procesar_opcion(self, numero, opcion, peluqueria_key):
        """
        Procesa la opción seleccionada del menú
        
        Args:
            numero (str): Número de WhatsApp
            opcion (str): Opción seleccionada
            peluqueria_key (str): ID de la peluquería
            
        Returns:
            str: Próximo paso del flujo
        """
        numero_limpio = numero.replace("whatsapp:", "")
        config = self.peluquerias.get(peluqueria_key, {})
        
        # Mapeo de opciones
        opciones = {
            "1": self._iniciar_reserva,
            "2": self._ver_turnos,
            "3": self._cancelar_turno,
            "4": self._reagendar_turno,
            "5": self._ver_precios,
            "6": self._ver_faq,
            "7": self._ver_ubicacion,
            "0": self._salir
        }
        
        handler = opciones.get(opcion)
        
        if handler:
            return handler(numero, numero_limpio, config)
        else:
            whatsapp_service.enviar_mensaje(
                "❌ Opción inválida. Elegí un número del 0 al 7.",
                numero
            )
            return "menu"
    
    def _iniciar_reserva(self, numero, numero_limpio, config):
        """Opción 1: Iniciar reserva de turno"""
        # Obtener peluqueros activos
        peluqueros_activos = [
            p for p in config.get("peluqueros", [])
            if p.get("activo", True)
        ]
        
        if not peluqueros_activos:
            whatsapp_service.enviar_mensaje(
                "😕 No hay peluqueros disponibles en este momento.\n\n"
                "Por favor, intenta más tarde.",
                numero
            )
            return "menu"
        
        # Guardar estado
        estado = get_state(numero_limpio) or {}
        estado["paso"] = "seleccionar_peluquero"
        estado["peluqueros_disponibles"] = peluqueros_activos
        set_state(numero_limpio, estado)
        
        # Mostrar lista
        from app.bot.utils.formatters import formatear_item_lista
        
        lista = "\n".join(
            formatear_item_lista(i, p["nombre"])
            for i, p in enumerate(peluqueros_activos)
        )
        
        whatsapp_service.enviar_mensaje(
            f"✂️ *Seleccioná tu peluquero:*\n\n{lista}\n\nEscribí el número:",
            numero
        )
        
        return "seleccionar_peluquero"
    
    def _ver_turnos(self, numero, numero_limpio, config):
        """Opción 2: Ver turnos del cliente"""
        from app.core.database import obtener_turnos_por_telefono
        
        turnos = obtener_turnos_por_telefono(numero_limpio)
        
        if not turnos:
            whatsapp_service.enviar_mensaje(
                "📅 No tenés turnos reservados.\n\n"
                "Escribí *1* para reservar uno.",
                numero
            )
            return "menu"
        
        # Formatear turnos
        mensaje = "📅 *Tus turnos:*\n\n"
        
        for i, turno in enumerate(turnos, 1):
            mensaje += f"{i}. {turno['fecha']} - {turno['hora']}\n"
            mensaje += f"   ✂️ Con {turno['peluquero']}\n\n"
        
        mensaje += "Escribí *menu* para volver"
        
        whatsapp_service.enviar_mensaje(mensaje, numero)
        return "menu"
    
    def _cancelar_turno(self, numero, numero_limpio, config):
        """Opción 3: Cancelar turno"""
        from app.core.database import obtener_turnos_por_telefono
        
        turnos = obtener_turnos_por_telefono(numero_limpio)
        
        if not turnos:
            whatsapp_service.enviar_mensaje(
                "📅 No tenés turnos para cancelar.\n\n"
                "Escribí *menu* para volver.",
                numero
            )
            return "menu"
        
        # Guardar turnos en estado
        estado = get_state(numero_limpio) or {}
        estado["paso"] = "confirmar_cancelacion"
        estado["turnos"] = turnos
        set_state(numero_limpio, estado)
        
        # Mostrar lista
        from app.bot.utils.formatters import formatear_item_lista
        
        mensaje = "❌ *Cancelar turno:*\n\n"
        for i, turno in enumerate(turnos):
            mensaje += formatear_item_lista(
                i,
                f"{turno['fecha']} - {turno['hora']} con {turno['peluquero']}"
            ) + "\n"
        
        mensaje += "\nEscribí el número del turno a cancelar:"
        
        whatsapp_service.enviar_mensaje(mensaje, numero)
        return "confirmar_cancelacion"
    
    def _reagendar_turno(self, numero, numero_limpio, config):
        """Opción 4: Reagendar turno"""
        whatsapp_service.enviar_mensaje(
            "ℹ️ Para reagendar:\n\n"
            "1️⃣ Primero cancelá tu turno actual (opción 3)\n"
            "2️⃣ Luego pedí uno nuevo (opción 1)\n\n"
            "Escribí *menu* para volver",
            numero
        )
        return "menu"
    
    def _ver_precios(self, numero, numero_limpio, config):
        """Opción 5: Ver precios"""
        from app.bot.utils.formatters import formatear_precio
        
        servicios = config.get("servicios", [])
        
        if not servicios:
            whatsapp_service.enviar_mensaje(
                "💰 Contactanos para consultar precios.\n\n"
                "Escribí *menu* para volver.",
                numero
            )
            return "menu"
        
        mensaje = "💰 *Nuestros servicios:*\n\n"
        
        for servicio in servicios:
            nombre = servicio.get("nombre", "Servicio")
            precio = servicio.get("precio", 0)
            mensaje += f"• {nombre}: {formatear_precio(precio)}\n"
        
        mensaje += "\nEscribí *menu* para volver"
        
        whatsapp_service.enviar_mensaje(mensaje, numero)
        return "menu"
    
    def _ver_faq(self, numero, numero_limpio, config):
        """Opción 6: Preguntas frecuentes"""
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
        return "menu"
    
    def _ver_ubicacion(self, numero, numero_limpio, config):
        """Opción 7: Ubicación y contacto"""
        nombre = config.get("nombre", "Peluquería")
        direccion = config.get("direccion", "Calle Ejemplo 123")
        telefono = config.get("telefono", "+54 9 11 1234-5678")
        
        mensaje = f"""📍 *Ubicación de {nombre}:*

Dirección: {direccion}

🕐 *Horarios:*
Lunes a Viernes: 08:00 - 21:00
Sábados: 08:00 - 19:00
Domingos: Cerrado

📞 *Contacto:*
Teléfono: {telefono}

Escribí *menu* para volver"""
        
        whatsapp_service.enviar_mensaje(mensaje, numero)
        return "menu"
    
    def _salir(self, numero, numero_limpio, config):
        """Opción 0: Salir del menú"""
        nombre = config.get("nombre", "Peluquería")
        
        whatsapp_service.enviar_mensaje(
            "👋 ¡Gracias por contactarnos!\n\n"
            "Cuando quieras volver, escribí *hola* o *menu*\n\n"
            f"*{nombre}* 💈",
            numero
        )
        
        # Actualizar estado
        estado = get_state(numero_limpio) or {}
        estado["paso"] = "finalizado"
        set_state(numero_limpio, estado)
        
        return "finalizado"