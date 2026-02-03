
"""
Verifica que la conexión con Google Calendar funcione
"""

import sys
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz

def test_calendar(peluqueria_key="sandbox"):
    with open("clientes.json", "r", encoding="utf-8") as f:
        clientes = json.load(f)
    
    if peluqueria_key not in clientes:
        print(f"❌ No existe '{peluqueria_key}' en clientes.json")
        return
    
    config = clientes[peluqueria_key]
    print(f"🔍 Probando: {config['nombre']}")
    print(f"📅 Calendar ID: {config['calendar_id']}")
    
    try:
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        creds = Credentials.from_authorized_user_file(config["token_file"], SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        
        # Buscar eventos de hoy
        tz = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.now(tz)
        
        eventos = service.events().list(
            calendarId=config["calendar_id"],
            timeMin=ahora.isoformat(),
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        print(f"\n✅ Conexión exitosa!")
        print(f"📊 Próximos {len(eventos.get('items', []))} eventos:")
        
        for event in eventos.get('items', []):
            start = event['start'].get('dateTime', event['start'].get('date'))
            print(f"  • {event.get('summary', 'Sin título')} - {start}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "sandbox"
    test_calendar(key)