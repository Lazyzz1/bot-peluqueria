# 🤖 Bot de WhatsApp para Peluquerías

Sistema automatizado de gestión de turnos para peluquerías vía WhatsApp.

## 🌟 Características

- ✅ Reserva de turnos 24/7
- ✅ Integración con Google Calendar
- ✅ Recordatorios automáticos (24h y 2h antes)
- ✅ Cancelación y reagendado de turnos
- ✅ Multi-peluquería (SaaS)
- ✅ WhatsApp Business API

## 🚀 Instalación Local

### Requisitos
- Python 3.11+
- Cuenta de Twilio
- Cuenta de Google Cloud (Calendar API)
- WhatsApp Business (para producción)

### Pasos

1. **Clonar repositorio:**
```bash
git clone https://github.com/TU_USUARIO/bot-peluqueria.git
cd bot-peluqueria
```

2. **Crear entorno virtual:**
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. **Instalar dependencias:**
```bash
pip install -r requirements.txt
```

<<<<<<< HEAD
4. **Configurar variables de entorno:**
```bash
cp .env.example .env
# Editar .env con tus credenciales
=======
2. Configurar variables de entorno en `.env`:
```
ACCESS_TOKEN=tu_token_aqui
PHONE_NUMBER_ID=tu_phone_id
VERIFY_TOKEN=marcelino
>>>>>>> a359c75 (Agregar archivos de deploy)
```

5. **Configurar Google Calendar:**
```bash
python autenticar_google.py sandbox
```

6. **Configurar clientes:**
```bash
cp clientes.json.example clientes.json
# Editar clientes.json con tus datos
```

7. **Ejecutar bot:**
```bash
python peluqueria_bot_prueba.py
```

<<<<<<< HEAD
## 🌐 Deploy en Railway
=======
## Uso
Este software se ofrece como servicio a negocios de estética y peluquería.

## Responsable
Lucas Romero  
Email: tuemail@gmail.com  
País: Argentina

## Deployment
>>>>>>> a359c75 (Agregar archivos de deploy)

1. Push a GitHub
2. Conectar Railway con tu repo
3. Configurar variables de entorno
4. Subir tokens de Google Calendar
5. Deploy automático

Ver guía completa: [DEPLOY.md](DEPLOY.md)

## 📱 Funcionalidades

### Para Clientes:
- Pedir turno (con selección de día y horario)
- Ver turnos reservados
- Cancelar turnos
- Reagendar turnos
- Ver servicios y precios
- Preguntas frecuentes
- Ubicación y contacto

### Para Peluqueros:
- Gestión automática de agenda
- Recordatorios automáticos
- Sincronización con Google Calendar
- Sin intervención manual

## 💰 Modelo de Negocio

- **Código fuente:** USD $149 (licencia única)
- **SaaS:** USD $50-80/mes por cliente
- **Instalación + Soporte:** USD $249

## 📄 Licencia

Uso personal o comercial permitido con atribución.
Reventa del código fuente requiere licencia extendida.

## 🆘 Soporte

- Email: lucasbenavides710@gmail.com
- WhatsApp: +54 9 2974924147
- Issues: GitHub Issues

## 🙏 Créditos

Desarrollado por Lazyzz1.
