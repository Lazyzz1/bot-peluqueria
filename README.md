# Bot de Peluquería para WhatsApp

Bot automatizado para gestionar reservas de turnos vía WhatsApp Business API.

## Características
- Reserva de turnos automática
- Integración con Google Calendar
- Cancelación de turnos
- Recordatorios automáticos 24h antes

## Configuración

1. Instalar dependencias:
```bash
pip install -r requirements.txt
```

2. Configurar variables de entorno en `.env`:
```
ACCESS_TOKEN=tu_token_aqui
PHONE_NUMBER_ID=tu_phone_id
VERIFY_TOKEN=12345
```

3. Agregar credenciales de Google Calendar (`token.json`)

4. Ejecutar:
```bash
python peluqueria_bot_prueba.py
```

## Deployment

Ver guía de deployment en Railway.