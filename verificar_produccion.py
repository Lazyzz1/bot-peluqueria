
"""
Verifica que todo esté listo para producción
Uso: python verificar_produccion.py
"""

import os
import json

print("🔍 VERIFICACIÓN PRE-PRODUCCIÓN")
print("="*60)

checks = []

# 1. Archivo .env
if os.path.exists('.env'):
    with open('.env', 'r') as f:
        env_content = f.read()
        has_sid = 'TWILIO_ACCOUNT_SID' in env_content
        has_token = 'TWILIO_AUTH_TOKEN' in env_content
        has_number = 'TWILIO_WHATSAPP_NUMBER' in env_content
        
        checks.append(("Variables Twilio", has_sid and has_token and has_number))
else:
    checks.append(("Archivo .env", False))

# 2. clientes.json
if os.path.exists('clientes.json'):
    with open('clientes.json', 'r') as f:
        clientes = json.load(f)
        checks.append(("clientes.json válido", len(clientes) > 0))
else:
    checks.append(("clientes.json", False))

# 3. Tokens
token_ok = os.path.exists('tokens') and len(os.listdir('tokens')) > 0
checks.append(("Tokens de Google", token_ok))

# 4. requirements.txt
checks.append(("requirements.txt", os.path.exists('requirements.txt')))

# 5. Procfile
checks.append(("Procfile", os.path.exists('Procfile')))

# 6. .gitignore
checks.append((".gitignore", os.path.exists('.gitignore')))

# Mostrar resultados
print("\n📋 CHECKLIST:")
for check, status in checks:
    emoji = "✅" if status else "❌"
    print(f"{emoji} {check}")

# Resumen
total = len(checks)
passed = sum(1 for _, status in checks if status)

print(f"\n📊 Resultado: {passed}/{total} checks pasados")

if passed == total:
    print("\n🚀 ¡Listo para producción!")
else:
    print("\n⚠️ Completa los items faltantes antes de deployar")