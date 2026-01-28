📦 Guía de Migración - De Monolito a Estructura Modular
🎯 Objetivo
Esta guía te ayudará a migrar tu código desde peluqueria_bot_prueba.py (2500+ líneas) a la nueva estructura modular.
📋 Estado Actual vs Nueva Estructura
Antes (Monolito)
peluqueria_bot_prueba.py (2500+ líneas)
├── Configuración mezclada
├── Servicios mezclados
├── Handlers mezclados
└── Todo en un archivo
Después (Modular)
app/
├── core/           → Configuración y núcleo
├── services/       → Servicios externos (Twilio, Calendar)
├── bot/            → Lógica del bot
│   ├── handlers/   → Manejadores por funcionalidad
│   └── utils/      → Utilidades
└── api/            → Endpoints HTTP
🔄 Mapa de Migración
1. Configuración (Líneas 1-136)
Desde: peluqueria_bot_prueba.py líneas 45-136
Hacia: app/core/config.py
python# ANTES (en peluqueria_bot_prueba.py)
load_dotenv()
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
PELUQUERIAS = json.load(...)

# DESPUÉS (en app/core/config.py)
class Config:
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    # ...

PELUQUERIAS = cargar_clientes()
2. Servicio de WhatsApp (Líneas 280-350)
Desde: Función enviar_mensaje() líneas ~280-350
Hacia: app/services/whatsapp_service.py
python# ANTES
def enviar_mensaje(mensaje, numero):
    message = twilio_client.messages.create(...)

# DESPUÉS
class WhatsAppService:
    def enviar_mensaje(self, mensaje, numero_destino):
        message = self.client.messages.create(...)

whatsapp_service = WhatsAppService()
3. Formateo de Datos (Líneas 152-240)
Desde: Funciones formatear_*() líneas 152-240
Hacia: app/bot/utils/formatters.py
python# ANTES (disperso en el archivo principal)
def formatear_telefono(telefono):
    # ...

def formatear_fecha_espanol(fecha):
    # ...

# DESPUÉS (todo en formatters.py)
# Todas las funciones de formateo juntas y organizadas
4. Manejador de Menú (Líneas 1800-2200)
Desde: Función procesar_mensaje_menu() y opciones
Hacia: app/bot/handlers/menu_handler.py
python# ANTES (mezclado)
def procesar_mensaje_menu(numero, texto, peluqueria_key):
    if texto == "1":
        # reservar turno
    elif texto == "2":
        # ver turnos
    # ...

# DESPUÉS (clase organizada)
class MenuHandler:
    def procesar_opcion(self, numero, opcion, peluqueria_key):
        opciones = {
            "1": self._iniciar_reserva,
            "2": self._ver_turnos,
            # ...
        }
        return opciones[opcion](...)
5. Webhook de WhatsApp (Líneas 2100-2300)
Desde: Ruta /webhook en archivo principal
Hacia: app/api/webhooks/whatsapp.py
python# ANTES
@app.route("/webhook", methods=["POST"])
def webhook():
    # lógica mezclada

# DESPUÉS
# whatsapp_bp Blueprint separado con lógica clara
@whatsapp_bp.route("/webhook", methods=["POST"])
def webhook_whatsapp():
    # Lógica organizada por estados
🚀 Pasos de Migración
Fase 1: Configuración Base ✅ (Ya completada)

✅ app/core/config.py - Configuración centralizada
✅ .env.example - Plantilla de variables de entorno
✅ requirements.txt - Dependencias
✅ .gitignore - Archivos ignorados

Fase 2: Servicios Externos ✅ (Ya completada)

✅ app/services/whatsapp_service.py - Servicio WhatsApp/Twilio
⏳ app/services/calendar_service.py - Calendario de Google
⏳ app/services/notification_service.py - Sistema de recordatorios
⏳ app/core/database.py - MongoDB/Redis

Fase 3: Lógica del Bot (Parcial)

✅ app/bot/handlers/menu_handler.py - Menú principal
✅ app/bot/utils/formatters.py - Formateo de datos
⏳ app/bot/handlers/booking_handler.py - Reserva de turno
⏳ app/bot/handlers/cancellation_handler.py - Cancelación
⏳ app/bot/states/state_manager.py - Gestión de estados

Fase 4: API y Endpoints ✅ (Completado Ya)

✅ app/api/webhooks/whatsapp.py - Libro web WhatsApp
✅ app/api/routes/health.py - Chequeo de salud
⏳ app/api/routes/static.py - Página de destino

Fase 5: Punto de entrada ✅ (Completado Ya)

✅ app/__init__.py - Matraz de fábrica
✅ run.py - Principal del punto de entrada

📝 Archivos Pendientes por Crear
Alta prioridad

app/services/calendar_service.py

Migrar funciones de Google Calendar
Líneas ~400-800 del archivo original
Gestión de credenciales OAuth


app/bot/handlers/booking_handler.py

Proceso completo de reserva
Selección de peluquero, día, hora
Confirmación del turno


app/bot/states/state_manager.py

Gestión de estados con Redis
Ya tienes importaciones de esto en el código original


app/core/database.py

MongoDB para persistencia
Ya tienes importaciones de esto (líneas 23-43)



Media Prioridad

app/bot/handlers/cancellation_handler.py

Proceso de cancelación de turnos


app/services/notification_service.py

Sistema de recordatorios automáticos
Hilo que se ejecuta en segundo plano



Baja Prioridad

app/models/- Modelos de datos
tests/- Tests unitarios
scripts/- Scripts de utilidad

🔨 Cómo Continuar
Opción A: Migración Manual (Recomendada)

Identificar funcionalidad en peluqueria_bot_prueba.py
Copiar código relevante a nuevo archivo
Adaptar cantidades estructura y
Probar funcionalidad aislada
Integrar con el resto del sistema

Opción B: Migración Progresiva

Mantener peluqueria_bot_prueba.py funcionando
Crear nuevos archivos en paralelo
Ir moviendo funcionalidad gradualmente
Probar cada cambio
Deprecar archivo viejo cuando esté completo

✅ Checklist de Migración

 Configuración centralizada
 Servicio de WhatsApp
 Formateo de datos
 Estructura básica de Flask
 Libro web de WhatsApp
 Chequeo de salud
 Servicio de calendario de Google
 Manejador de reservas completo
 Manejador de cancelación
 Gerente de Estado (Redis)
 Base de datos (MongoDB)
 Sistema de recordatorios
 Modelos de datos
 Pruebas

🎯 Próximos Pasos Sugeridos

Crear calendar_service.py - Es crítico para el funcionamiento
Crear booking_handler.py - Flujo principal del bot
Crear state_manager.py - Gestión de conversaciones
Probar flujo completo - Desde menú hasta confirmación
Agregar tests - Asegurar calidad

💡 Tips de Migración

No migres todo de golpe - Hazlo por módulos
Prueba cada módulo antes de continuar
Mantén el código viejo como referencia
Documenta cambios importantes
Utiliza ramas de git intentar

🐛 Posibles Problemas

Imports circulares - Usar importaciones dentro de funciones
Estado compartido - Usar Redis/MongoDB correctamente
Timezone issues - Ya manejado en time_utils
Credenciales Google - Migrar tokens correctamente