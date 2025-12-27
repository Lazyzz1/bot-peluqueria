from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Mensajes de hoy
from datetime import datetime, timedelta

hoy = datetime.now().date()
mensajes = client.messages.list(
    date_sent_after=hoy,
    limit=1000
)

total = len(mensajes)
costo_estimado = total * 0.005

print(f"📊 Mensajes hoy: {total}")
print(f"💰 Costo estimado: ${costo_estimado:.2f} USD")