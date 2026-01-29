"""
Manejador del Menú Principal
Gestiona el menú principal y las opciones del bot
"""

from app.services.whatsapp_service import whatsapp_service
from app.utils.translations import t


class MenuHandler:
    """Manejador del menú principal del bot"""
    
    def __init__(self, peluquerias_config):
        """
        Inicializa el manejador del menú
        
        Args:
            peluquerias_config: Diccionario con configuración de clientes
        """
        self.peluquerias = peluquerias_config
    
    def mostrar_menu_principal(self, peluqueria_key, numero, idioma="es"):
        """
        Muestra el menú principal al usuario
        
        Args:
            peluqueria_key: Identificador del cliente
            numero: Número de WhatsApp del usuario
            idioma: Idioma del menú (default: español)
        """
        config = self.peluquerias.get(peluqueria_key, {})
        nombre = config.get("nombre", "Peluquería")
        
        # Detectar idioma del cliente si está configurado
        idioma_config = config.get("idioma", idioma)
        
        # Generar menú
        mensaje = self._generar_menu(nombre, idioma_config)
        
        whatsapp_service.enviar_mensaje(mensaje, numero)
    
    def _generar_menu(self, nombre_peluqueria, idioma="es"):
        """
        Genera el texto del menú principal
        
        Args:
            nombre_peluqueria: Nombre de la peluquería
            idioma: Idioma del menú
        
        Returns:
            str: Mensaje del menú formateado
        """
        if idioma == "en":
            return self._generar_menu_ingles(nombre_peluqueria)
        else:
            return self._generar_menu_espanol(nombre_peluqueria)
    
    def _generar_menu_espanol(self, nombre):
        """Genera el menú en español"""
        return f"""👋 *¡Bienvenido a {nombre}!*

¿Qué querés hacer?

1️⃣ Pedir turno
2️⃣ Ver mis turnos
3️⃣ Cancelar turno
4️⃣ Ver servicios
5️⃣ Reagendar turno
6️⃣ Preguntas frecuentes
7️⃣ Ubicación y contacto
0️⃣ Salir

Escribí el número de la opción que querés"""
    
    def _generar_menu_ingles(self, nombre):
        """Genera el menú en inglés"""
        return f"""👋 *Welcome to {nombre}!*

What would you like to do?

1️⃣ Book appointment
2️⃣ View my appointments
3️⃣ Cancel appointment
4️⃣ View services
5️⃣ Reschedule appointment
6️⃣ FAQ
7️⃣ Location & contact
0️⃣ Exit

Type the number of the option you want"""
    
    def mostrar_mensaje_bienvenida(self, peluqueria_key, numero, idioma="es"):
        """
        Muestra un mensaje de bienvenida personalizado
        
        Args:
            peluqueria_key: Identificador del cliente
            numero: Número de WhatsApp
            idioma: Idioma del mensaje
        """
        config = self.peluquerias.get(peluqueria_key, {})
        nombre = config.get("nombre", "Peluquería")
        
        # Mensaje personalizado si existe en config
        mensaje_custom = config.get("mensaje_bienvenida")
        
        if mensaje_custom:
            whatsapp_service.enviar_mensaje(mensaje_custom, numero)
        else:
            if idioma == "en":
                mensaje = f"👋 Hello! Welcome to {nombre}'s booking system"
            else:
                mensaje = f"👋 ¡Hola! Bienvenido al sistema de turnos de {nombre}"
            
            whatsapp_service.enviar_mensaje(mensaje, numero)
        
        # Mostrar menú
        self.mostrar_menu_principal(peluqueria_key, numero, idioma)
    
    def mostrar_opcion_invalida(self, numero, texto="", idioma="es"):
        """
        Muestra mensaje cuando el usuario envía una opción inválida
        
        Args:
            numero: Número de WhatsApp
            texto: Texto enviado por el usuario
            idioma: Idioma del mensaje
        """
        if idioma == "en":
            mensaje = f"❓ I didn't understand '{texto}'\n\nPlease choose a number from the menu:"
        else:
            mensaje = f"❓ No entendí '{texto}'\n\nPor favor elegí un número del menú:"
        
        whatsapp_service.enviar_mensaje(mensaje, numero)


# Instancia global (se inicializa desde el orquestador)
menu_handler = None


def inicializar_menu_handler(peluquerias_config):
    """Inicializa el manejador de menú globalmente"""
    global menu_handler
    menu_handler = MenuHandler(peluquerias_config)
    return menu_handler