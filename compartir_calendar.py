# Script: compartir_calendario.py
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json

def compartir_calendario_con_cliente(cliente_key):
    """Comparte el calendario con el dueño del negocio"""
    
    # Leer config
    with open('clientes.json', 'r', encoding='utf-8') as f:
        clientes = json.load(f)
    
    config = clientes[cliente_key]
    calendar_id = config['calendar_id']
    email_dueno = config.get('owner_email')
    token_file = config['token_file']
    
    if not email_dueno:
        print(f"❌ Cliente {cliente_key} no tiene email configurado")
        return False
    
    # Conectar a Google Calendar
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    
    # Regla de ACL (Access Control List)
    rule = {
        'scope': {
            'type': 'user',
            'value': email_dueno,
        },
        'role': 'writer'  # 'owner', 'writer', 'reader'
    }
    
    try:
        created_rule = service.acl().insert(
            calendarId=calendar_id,
            body=rule
        ).execute()
        
        print(f"✅ Calendario compartido con {email_dueno}")
        print(f"   Permisos: {rule['role']}")
        print(f"   Rule ID: {created_rule['id']}")
        return True
        
    except Exception as e:
        if '409' in str(e):
            print(f"⚠️  El calendario ya está compartido con {email_dueno}")
            return True
        else:
            print(f"❌ Error: {e}")
            return False

# Uso
compartir_calendario_con_cliente('cliente_001')