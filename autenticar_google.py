from google_auth_oauthlib.flow import InstalledAppFlow
import sys
import os

SCOPES = ['https://www.googleapis.com/auth/calendar']

# Crear carpeta tokens si no existe
if not os.path.exists('tokens'):
    os.makedirs('tokens')

# Obtener peluquería desde argumentos
if len(sys.argv) > 1:
    peluqueria = sys.argv[1]
else:
    peluqueria = "sandbox"

# Archivo de salida
token_file = f'tokens/{peluqueria}_token.json'

print(f"🔐 Autenticando Google Calendar para: {peluqueria}")

# Autenticar
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=0)

# Guardar
with open(token_file, 'w') as token:
    token.write(creds.to_json())

print(f"✅ Token guardado en: {token_file}")
print(f"\nAhora puedes ejecutar el bot con: python peluqueria_bot_prueba.py")