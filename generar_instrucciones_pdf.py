# generar_instrucciones_pdf.py
import json
import qrcode
from io import BytesIO

def generar_qr_whatsapp(numero_bot):
    """Genera QR que abre WhatsApp con el bot"""
    # Formato: https://wa.me/12624767007
    url = f"https://wa.me/{numero_bot.replace('+', '')}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    return img

def generar_instrucciones_cliente(cliente_key):
    """Genera instrucciones visuales para el cliente"""
    
    with open('clientes.json', 'r', encoding='utf-8') as f:
        clientes = json.load(f)
    
    config = clientes[cliente_key]
    numero_bot = config.get('numero_twilio', '+12624767007')
    
    # Generar QR
    qr_img = generar_qr_whatsapp(numero_bot)
    qr_img.save(f'qr_{cliente_key}.png')
    
    print(f"✅ QR generado: qr_{cliente_key}.png")
    print(f"   Los peluqueros pueden escanear para abrir WhatsApp")


generar_instrucciones_cliente('cliente_001')