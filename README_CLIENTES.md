# 🚀 Cómo agregar un nuevo cliente

## Requisitos previos
1. Número de Twilio con WhatsApp habilitado
2. Google Calendar creado para el cliente
3. Acceso al servidor (Railway)

## Pasos

### 1. Ejecutar script de agregar cliente
```bash
python agregar_cliente.py
```

### 2. Configurar número Twilio
- Ir a: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
- Seleccionar el número del cliente
- En "Messaging" → "When a message comes in":
  - URL: `https://tu-bot.railway.app/webhook`
  - Método: HTTP POST

### 3. Reiniciar el bot en Railway
El bot detectará automáticamente el nuevo cliente.

## Precios sugeridos
- **Cliente paga**: USD $80-100/mes
- **Tus costos**: USD $30/mes
- **Tu ganancia**: USD $75-95/mes por cliente

### 4. Números de clientes.
- **Peluquería "nombre"**: +17622660178