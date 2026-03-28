"""
Script para crear el Plan de Suscripción en MercadoPago
Ejecutá esto UNA SOLA VEZ para crear el plan.
Guardá el `plan_id` que te devuelve — va al .env como MERCADOPAGO_PLAN_ID
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN")

if not ACCESS_TOKEN:
    print("❌ No encontré MERCADOPAGO_ACCESS_TOKEN en .env")
    exit(1)

url = "https://api.mercadopago.com/preapproval_plan"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

payload = {
    "reason": "TurnosBot - Suscripción mensual",
    "auto_recurring": {
        "frequency": 1,
        "frequency_type": "months",
        "transaction_amount": 24500,
        "currency_id": "ARS",
        "free_trial": {
            "frequency": 7,
            "frequency_type": "days",
        },
    },
    "payment_methods_allowed": {
        "payment_types": [{"id": "credit_card"}, {"id": "debit_card"}],
    },
    "back_url": "https://turnosbot-landing.vercel.app/gracias?plan=argentina",
}

response = requests.post(url, json=payload, headers=headers)

if response.status_code == 201:
    data = response.json()
    plan_id = data["id"]
    print("✅ Plan creado exitosamente!")
    print(f"\n👉 Guardá esto en tu .env y en Railway:")
    print(f"MERCADOPAGO_PLAN_ID={plan_id}")
    print(f"\nURL del plan: {data.get('init_point', 'N/A')}")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.json())