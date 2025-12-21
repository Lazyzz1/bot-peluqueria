# 🧪 Guía de Desarrollo Local

## Prerrequisitos

1. **Python 3.8+**
2. **ngrok** - [Descargar aquí](https://ngrok.com/download)
3. **Twilio Sandbox** - Ya lo tienes configurado

## Instalación
```bash
# 1. Clonar repositorio (si no lo tienes)
git clone tu-repo.git
cd tu-repo

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Copiar configuración
cp .env .env.local
# Edita .env.local con tus datos de desarrollo
```

## Uso

### Iniciar desarrollo local
```bash
python run_local.py
```

El script:
1. ✅ Verifica dependencias
2. ✅ Inicia ngrok automáticamente
3. ✅ Te da la URL pública
4. ✅ Inicia el bot en modo debug

### Configurar Twilio Sandbox

1. Copia la URL que te da ngrok (ej: `https://abc123.ngrok.io`)
2. Ve a: https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
3. En "When a message comes in" pega: `https://abc123.ngrok.io/webhook`
4. Guarda cambios

### Probar el bot

1. Envía el código de join a tu WhatsApp sandbox
2. Escribe `hola` para iniciar
3. Los logs aparecerán en tu terminal

## Estructura de Archivos
```
.
├── peluqueria_bot_prueba.py   # Bot principal
├── run_local.py                # Script de desarrollo ← NUEVO
├── clientes.json               # Base de datos
├── .env                        # Config producción (Railway)
├── .env.local                  # Config desarrollo ← NUEVO
└── README_DEV.md               # Esta guía
```

## Diferencias Desarrollo vs Producción

| Feature | Desarrollo | Producción |
|---------|-----------|------------|
| Puerto | 3000 (local) | Dinámico (Railway) |
| Debug | ✅ Activado | ❌ Desactivado |
| Recordatorios | ❌ Desactivados | ✅ Activados |
| Hot Reload | ✅ Activado | ❌ Desactivado |
| Logs | Verbose | Normal |
| Cliente | `dev_local` | `cliente_001`, etc. |

## Tips de Desarrollo

### Ver logs en tiempo real

Los logs aparecen automáticamente en tu terminal.

### Reiniciar el bot

- Automático: Guarda cambios → se reinicia solo
- Manual: `Ctrl+C` → `python run_local.py`

### Detener ngrok

Se detiene automáticamente al cerrar el script.

### Ver dashboard de ngrok

Ve a: http://localhost:4040

## Troubleshooting

### "ngrok no encontrado"
```bash
# Mac
brew install ngrok

# Windows (Chocolatey)
choco install ngrok

# Linux
sudo snap install ngrok
```

### "Port already in use"
```bash
# Cambiar puerto al ejecutar
python run_local.py
# Cuando pregunte, escribe: 3001 (u otro puerto)
```

### "No se puede conectar a Twilio"

Verifica que:
1. La URL de ngrok esté actualizada en Twilio
2. El formato sea: `https://...ngrok.io/webhook`
3. El método sea HTTP POST

### Cliente de desarrollo no aparece
```bash
# Elimina clientes.json y vuelve a ejecutar
rm clientes.json
python run_local.py
```

## Flujo de Trabajo Recomendado

1. **Desarrollo:**
```bash
   python run_local.py
   # Hacer cambios en el código
   # Probar en WhatsApp
```

2. **Commit:**
```bash
   git add .
   git commit -m "feat: nueva funcionalidad"
```

3. **Deploy a producción:**
```bash
   git push origin main
   # Railway despliega automáticamente
```

## Cliente de Desarrollo

El script crea automáticamente un cliente llamado `dev_local` en `clientes.json`:
```json
{
  "dev_local": {
    "nombre": "🧪 Desarrollo Local",
    "numero_twilio": "+14155238886",
    ...
  }
}
```

Este cliente:
- ✅ Usa el sandbox de Twilio
- ✅ Tiene servicios de prueba
- ✅ No interfiere con clientes reales

## Comandos Útiles
```bash
# Ver logs en vivo
python run_local.py

# Probar sin ngrok (solo localhost)
python peluqueria_bot_prueba.py

# Actualizar dependencias
pip install -r requirements.txt --upgrade

# Limpiar caché de Python
find . -type d -name __pycache__ -exec rm -r {} +
```