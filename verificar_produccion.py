"""
Verifica que todo esté listo para producción
"""

import os
import json

print("🔍 VERIFICACIÓN PRE-PRODUCCIÓN - TurnosBot")
print("="*60)

checks = []

# ── 1. Variables de entorno ──────────────────────────────────
def check_env(var):
    val = os.getenv(var, "")
    return bool(val and val not in ("TU_TOKEN_ACA", "TU_LINK_ACA", "123456"))

# Cargar .env si existe
if os.path.exists('.env'):
    from dotenv import load_dotenv
    load_dotenv()

# Twilio
twilio_ok = all([check_env(v) for v in [
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_NUMBER"
]])
checks.append(("Variables Twilio", twilio_ok))

# MercadoPago
mp_ok = check_env("MERCADOPAGO_ACCESS_TOKEN")
checks.append(("MERCADOPAGO_ACCESS_TOKEN", mp_ok))

mp_plan = check_env("MERCADOPAGO_PLAN_ID")
checks.append(("MERCADOPAGO_PLAN_ID (suscripción)", mp_plan,
               "Ejecutá scripts/crear_plan_mp.py si no lo tenés"))

# LemonSqueezy
ls_ok = all([check_env(v) for v in [
    "LEMONSQUEEZY_API_KEY", "LEMONSQUEEZY_STORE_ID", "LEMONSQUEEZY_VARIANT_ID"
]])
checks.append(("Variables LemonSqueezy", ls_ok))

ls_webhook = check_env("LEMONSQUEEZY_WEBHOOK_SECRET")
checks.append(("LEMONSQUEEZY_WEBHOOK_SECRET", ls_webhook))

# MongoDB
mongo_ok = check_env("MONGODB_URI")
checks.append(("MONGODB_URI", mongo_ok))

# Redis
redis_ok = check_env("REDIS_HOST") or check_env("REDIS_URL")
checks.append(("Redis configurado", redis_ok))

# Admin WhatsApp
admin_ok = check_env("ADMIN_WHATSAPP")
checks.append(("ADMIN_WHATSAPP (alertas)", admin_ok,
               "Necesario para recibir avisos de pagos y suscripciones"))

# URLs
app_url_ok = check_env("APP_URL")
checks.append(("APP_URL (Railway)", app_url_ok))

# ── 2. Archivos del proyecto ─────────────────────────────────
checks.append(("clientes.json", os.path.exists('config/clientes.json') or
               os.path.exists('clientes.json')))

checks.append(("requirements.txt", os.path.exists('requirements.txt')))
checks.append(("Procfile", os.path.exists('Procfile')))
checks.append((".gitignore", os.path.exists('.gitignore')))

# ── 3. Tokens de Google Calendar ────────────────────────────
if os.path.exists('tokens'):
    token_files = [f for f in os.listdir('tokens') if f.endswith('_token.json')]
    checks.append((f"Tokens Google Calendar ({len(token_files)} encontrados)",
                   len(token_files) > 0))

    # Verificar que no estén vencidos sin refresh_token
    try:
        from google.oauth2.credentials import Credentials
        tokens_invalidos = []
        for tf in token_files:
            creds = Credentials.from_authorized_user_file(
                f"tokens/{tf}",
                ['https://www.googleapis.com/auth/calendar']
            )
            if not creds.refresh_token:
                tokens_invalidos.append(tf)
        if tokens_invalidos:
            checks.append((f"Tokens válidos", False,
                           f"Sin refresh_token: {', '.join(tokens_invalidos)}"))
        else:
            checks.append(("Tokens válidos (tienen refresh_token)", True))
    except Exception as e:
        checks.append(("Validar tokens", False, str(e)))
else:
    checks.append(("Carpeta tokens/", False, "Ejecutá autenticar_google.py"))

# ── 4. Conectividad ─────────────────────────────────────────
print("\n⏳ Verificando conectividad...")

# MongoDB
try:
    from pymongo import MongoClient
    mongo_uri = os.getenv("MONGODB_URI", "")
    if mongo_uri:
        c = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        c.server_info()
        checks.append(("Conexión MongoDB", True))
    else:
        checks.append(("Conexión MongoDB", False, "MONGODB_URI no configurado"))
except Exception as e:
    checks.append(("Conexión MongoDB", False, str(e)[:60]))

# Redis
try:
    import redis
    redis_url = os.getenv("REDIS_URL") or f"redis://:{os.getenv('REDIS_PASSWORD','')}@{os.getenv('REDIS_HOST','localhost')}:{os.getenv('REDIS_PORT',6379)}"
    r = redis.from_url(redis_url, socket_timeout=3)
    r.ping()
    checks.append(("Conexión Redis", True))
except Exception as e:
    checks.append(("Conexión Redis", False, str(e)[:60]))

# Backend Railway
try:
    import urllib.request
    app_url = os.getenv("APP_URL", "")
    if app_url:
        urllib.request.urlopen(f"{app_url}/health", timeout=5)
        checks.append(("Backend Railway /health", True))
    else:
        checks.append(("Backend Railway /health", False, "APP_URL no configurado"))
except Exception as e:
    checks.append(("Backend Railway /health", False, str(e)[:60]))

# ── Mostrar resultados ───────────────────────────────────────
print("\n📋 CHECKLIST COMPLETO:")
print("="*60)

passed = 0
warnings = []

for item in checks:
    check = item[0]
    status = item[1]
    nota = item[2] if len(item) > 2 else ""

    emoji = "✅" if status else "❌"
    print(f"{emoji} {check}")
    if nota and not status:
        print(f"   💡 {nota}")
    if status:
        passed += 1
    else:
        warnings.append(check)

total = len(checks)
print(f"\n{'='*60}")
print(f"📊 Resultado: {passed}/{total} checks pasados")

if passed == total:
    print("\n🚀 ¡Todo listo para producción!")
else:
    print(f"\n⚠️  {total - passed} items pendientes:")
    for w in warnings:
        print(f"   • {w}")
    print("\nCorregí los items marcados con ❌ antes de deployar")