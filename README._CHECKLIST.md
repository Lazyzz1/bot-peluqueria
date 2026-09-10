# TurnosBot — Paquete de automatización del onboarding

Este paquete tiene los archivos nuevos/modificados para automatizar todo
el flujo: pago → aprovisionamiento → bot activo, sin que tengas que tocar
`clientes.json` ni correr `activar_cliente.py` a mano.

## 🚨 Antes que nada: el bug de whatsapp_service.py

Confirmaste que `app/services/whatsapp_service.py` es una copia de
`config.py`. Reconstruí el archivo en base a cómo lo llama el resto del
código (`enviar_mensaje(mensaje, numero)`, `enviar_con_plantilla(...)`).
**Esto es un fix aparte de la automatización** — sin él, ningún mensaje de
WhatsApp sale del bot, tenga o no tenga automatización.

⚠️ Antes de subirlo a producción: probalo en local o en un entorno de
staging primero. Reconstruí el contrato (las firmas de las funciones) en
base a cómo se lo llama, pero no tengo forma de saber si tu implementación
original tenía algo más (reintentos, rate limiting, logging particular a
una base de datos, etc.) — si notás que falta algo específico, decime y lo
sumamos.

## 📁 Archivos incluidos (rutas relativas a cada proyecto)

### Backend (`bot-peluqueria/`)
```
app/services/whatsapp_service.py       ← RECONSTRUIDO (bug crítico)
app/services/provisioning_service.py   ← NUEVO (motor de la automatización)
app/core/config.py                     ← MODIFICADO (PELUQUERIAS dinámico)
app/core/database.py                   ← MODIFICADO (+ colección peluquerias_config)
app/api/webhooks/payments.py           ← MODIFICADO (dispara el aprovisionamiento)
app/__init__.py                        ← MODIFICADO (arranca el hilo de refresco)
```

### Landing (`turnos_landing/`)
```
components/ContratarModal.tsx          ← MODIFICADO (redirige al pago real)
app/gracias/page.tsx                   ← NUEVO (página post-pago)
```

**Importante**: no los pegues a ciegas encima de tu repo real. Especialmente
`app/api/webhooks/payments.py` y `config.py` — si tenés cambios locales que
no estaban en el zip que me pasaste, hacé un diff antes de sobrescribir.

## ✅ Checklist para poner esto en marcha

### 1. Variables de entorno nuevas (Railway)
- `TWILIO_WABA_ID` — el ID de tu WhatsApp Business Account. Lo encontrás en
  Twilio Console → Messaging → Senders, o en el sender de tu número actual.
- Confirmá que `WEBHOOK_URL` en tu `.env` de Railway apunte a la URL pública
  real de tu backend (ej `https://turnosbot-production.up.railway.app`) —
  existe la variable pero no vi que se usara en el código antes de esto.
- Opcional: `PELUQUERIAS_REFRESH_SEGUNDOS` (default 60).

### 2. MercadoPago
- Correr `scripts/crear_plan_mp.py` una vez → copiar el `plan_id` resultante
  a `MERCADOPAGO_PLAN_ID` en Railway.

### 3. LemonSqueezy — punto abierto, revisar
- `crear_checkout_onboarding_lemonsqueezy()` arma un Checkout contra un
  "variant". Si ese variant está configurado como suscripción con trial en
  el dashboard de LemonSqueezy, el evento que dispara la activación real
  probablemente sea `subscription_created`, no `order_created` (que es el
  único que escucha hoy `webhook_lemonsqueezy()`). Sugiero: hacé una compra
  de prueba y mirá en el log de webhooks de LemonSqueezy qué evento llega
  realmente, así lo enganchamos bien.

### 4. Twilio — probar con UN cliente antes de confiar en el resto
- La compra de número (`comprar_numero_twilio()`) gasta dinero real al
  ejecutarse. Probalo primero con un tope de gasto configurado en Twilio.
- El payload de `registrar_whatsapp_sender()` tiene el campo `profile` con
  el nombre del negocio — confirmé `sender_id`/`configuration`/`webhook`
  contra la documentación actual, pero no el detalle fino de `profile`.
  Registrá un sender de prueba, mirá la respuesta real de la API, y
  ajustá los nombres de campo si Twilio te devuelve algo distinto.
- El sender queda `OFFLINE`/`PENDING` un rato hasta que Meta lo aprueba —
  no hay forma de apurar eso desde código.

### 5. Deploy del backend
- Mergear los archivos, redeployar en Railway.
- Al arrancar deberías ver en los logs: `✅ Hilo de refresco de PELUQUERIAS
  iniciado (cada 60s)`.

### 6. Deploy de la landing
- Confirmar que `NEXT_PUBLIC_API_URL` en Vercel apunte a tu backend real
  (hoy cae en el placeholder `https://tu-backend.railway.app` si no está
  seteada).
- Redeployar.

### 7. Prueba end-to-end
- Completá el formulario vos mismo con un negocio de prueba.
- Confirmá que te redirige a MercadoPago/LemonSqueezy de verdad.
- Cargá una tarjeta de test, confirmá el trial.
- Mirá que te lleguen los dos avisos por WhatsApp (a vos y al "dueño").
- Revisá en Mongo (`peluquerias_config`) que la config haya quedado bien
  armada, sobre todo `horarios` y `servicios` — son los campos que se
  parsean desde texto libre y son los más propensos a salir raros.
- Si el sender ya pasó a `ONLINE`, mandale un mensaje de prueba al número
  nuevo y confirmá que el bot responde.

### 8. Cliente que cancela en el trial
- Ya está la lógica (`liberar_recursos_si_estaba_en_trial`), pero probala
  una vez de punta a punta: cancelá una suscripción de prueba en trial y
  confirmá que el número se libera en Twilio.

## 🆕 Función nueva: cobro de seña por turno

### Archivos que se suman
```
app/services/pagos/base.py                 ← interfaz común (Mercado Pago, Stripe futuro...)
app/services/pagos/mercadopago_provider.py ← OAuth connect + cobro con el token DEL NEGOCIO
app/services/pagos/__init__.py             ← registry (obtener_proveedor)
app/api/routes/pagos.py                    ← /pagos/conectar y /pagos/callback
app/bot/handlers/booking_handler.py        ← MODIFICADO (pide seña si requiere_pago=True)
app/api/webhooks/payments.py               ← MODIFICADO (confirma el turno cuando se paga la seña)
app/core/database.py                       ← MODIFICADO otra vez (+ conexiones_pago, turnos_pendientes_pago)
app/services/provisioning_service.py       ← MODIFICADO otra vez (manda el link de conectar MP al dueño)
app/__init__.py                            ← MODIFICADO otra vez (registra el blueprint de pagos)
```

### Cómo queda armado
Cada negocio conecta **su propia** cuenta de MercadoPago (OAuth) — la seña
cae directo en su cuenta, nunca pasa por la tuya. Está armado como una
capa (`app/services/pagos/`) para poder sumar Stripe el día de mañana sin
tocar `booking_handler.py` ni el webhook.

Flujo: cliente pide turno → si el negocio tiene `requiere_pago: true` y ya
conectó MercadoPago → el bot genera el link de la seña (mitad del total) →
cliente paga → MercadoPago avisa por webhook → **recién ahí** se crea el
turno en el calendario y se le manda al cliente:
```
✅ ¡Seña recibida!
Tu turno quedó confirmado para el martes 10 de septiembre a las 15:00.
Total del servicio: $16.000
Seña abonada: $8.000
Saldo a pagar en el local: $8.000.
```
Si el negocio NO tiene `requiere_pago` activado (default para todos, hasta
que conecten su cuenta), el flujo sigue exactamente igual que antes — cero
impacto en `cliente_001` mientras no conecte nada.

### Variables de entorno nuevas
- `MERCADOPAGO_CLIENT_ID` y `MERCADOPAGO_CLIENT_SECRET` — de una
  **Aplicación** de MercadoPago Developers (es distinto de tu
  `MERCADOPAGO_ACCESS_TOKEN` personal actual). Se crea gratis en tu panel
  de desarrollador de MercadoPago.
- Confirmá de nuevo que `APP_URL` o `WEBHOOK_URL` apunten a tu backend
  real — de ahí sale la `redirect_uri` del OAuth.
- En tu Aplicación de MercadoPago Developers, tenés que cargar la
  Redirect URL exacta: `https://TU-BACKEND/api/pagos/callback/mercadopago`
  (si no coincide letra por letra, MP rechaza el OAuth).

### ⚠️ Puntos a verificar con una prueba real (no pude probar nada de esto en vivo)
- **El más importante**: hoy `payment_service.verificar_webhook_mercadopago()`
  (la que trae los detalles del pago cuando llega el webhook) usa TU
  propio `MERCADOPAGO_ACCESS_TOKEN`. Cuando el pago se creó con el token
  del NEGOCIO conectado, no tengo 100% de certeza de que tu token de
  plataforma pueda leer ese pago igual — es el patrón más común en
  integraciones marketplace, pero MercadoPago podría exigir consultar el
  pago con el mismo token que lo creó. Hacé una seña de prueba end-to-end
  y fijate si `payment_info` llega completo al webhook; si no, avisame y
  ajustamos `verificar_webhook_mercadopago` para buscar la conexión por
  `external_reference` antes de pedir el pago.
- Probá el flujo de refresh del `access_token` del negocio (dura 180
  días, no vas a poder probarlo "de verdad" ahora, pero al menos revisá
  que `_access_token_valido` no rompa nada en el camino feliz).
- Sumá la Redirect URL en tu panel de MercadoPago Developers ANTES de
  probar — si no, el callback falla con `invalid redirect_uri`.

- `verificar_suscripcion.py` (período de gracia) — sigue funcionando igual,
  ahora simplemente va a encontrar el `peluqueria_key` que antes cargabas
  a mano.
- El resto de los handlers del bot (booking, cancelación, etc.) — no
  necesitan ningún cambio, siguen leyendo de `PELUQUERIAS` como siempre.
