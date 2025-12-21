
"""
Script para correr el bot localmente con ngrok
Uso: python run_local.py
"""

import os
import sys
import subprocess
import time
import json
from pathlib import Path

def verificar_dependencias():
    """Verifica que todas las dependencias estén instaladas"""
    print("🔍 Verificando dependencias...")
    
    dependencias = {
        'flask': 'Flask',
        'twilio': 'twilio',
        'google.auth': 'google-auth',
        'dotenv': 'python-dotenv',
        'pytz': 'pytz'
    }
    
    faltantes = []
    for modulo, paquete in dependencias.items():
        try:
            __import__(modulo)
            print(f"  ✅ {paquete}")
        except ImportError:
            faltantes.append(paquete)
            print(f"  ❌ {paquete} - NO INSTALADO")
    
    if faltantes:
        print(f"\n⚠️  Instala las dependencias faltantes:")
        print(f"   pip install {' '.join(faltantes)}")
        return False
    
    return True

def verificar_ngrok():
    """Verifica si ngrok está instalado"""
    print("\n🔍 Verificando ngrok...")
    
    try:
        result = subprocess.run(['ngrok', 'version'], 
                              capture_output=True, 
                              text=True)
        if result.returncode == 0:
            print(f"  ✅ ngrok instalado: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    print("  ❌ ngrok NO encontrado")
    print("\n📥 Instala ngrok:")
    print("   1. Ve a: https://ngrok.com/download")
    print("   2. Descarga para tu sistema operativo")
    print("   3. Extrae y mueve ngrok a tu PATH")
    print("\n   O en Linux/Mac:")
    print("   brew install ngrok")
    print("\n   O en Windows con Chocolatey:")
    print("   choco install ngrok")
    
    return False

def verificar_archivos():
    """Verifica que existan los archivos necesarios"""
    print("\n🔍 Verificando archivos...")
    
    archivos_requeridos = {
        '.env': 'Archivo de configuración',
        'peluqueria_bot_prueba.py': 'Bot principal',
        'clientes.json': 'Base de datos de clientes',
        'tokens/master_token.json': 'Token de Google Calendar'
    }
    
    faltantes = []
    for archivo, descripcion in archivos_requeridos.items():
        if os.path.exists(archivo):
            print(f"  ✅ {archivo}")
        else:
            faltantes.append(f"{archivo} ({descripcion})")
            print(f"  ❌ {archivo}")
    
    if faltantes:
        print("\n⚠️  Archivos faltantes:")
        for archivo in faltantes:
            print(f"   - {archivo}")
        return False
    
    return True

def crear_cliente_desarrollo():
    """Crea un cliente de desarrollo en clientes.json"""
    print("\n🔧 Configurando cliente de desarrollo...")
    
    try:
        with open('clientes.json', 'r', encoding='utf-8') as f:
            clientes = json.load(f)
    except:
        clientes = {}
    
    # Verificar si ya existe cliente de desarrollo
    if 'dev_local' in clientes:
        print("  ✅ Cliente 'dev_local' ya existe")
        return True
    
    # Crear cliente de desarrollo
    clientes['dev_local'] = {
        "nombre": "🧪 Desarrollo Local",
        "numero_twilio": "+14155238886",  # Sandbox de Twilio
        "calendar_id": clientes.get('cliente_001', {}).get('calendar_id', ''),
        "token_file": "tokens/master_token.json",
        "owner_email": "dev@local.test",
        "servicios": [
            {"nombre": "Test Corte", "duracion": 30, "precio": 10000},
            {"nombre": "Test Barba", "duracion": 20, "precio": 5000}
        ],
        "peluqueros": [
            {
                "id": "test_peluquero",
                "nombre": "Test Peluquero",
                "telefono": "+5491100000000",
                "especialidades": ["Test Corte", "Test Barba"],
                "dias_trabajo": ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"],
                "horarios": {
                    "lunes": ["09:00", "18:00"],
                    "martes": ["09:00", "18:00"],
                    "miercoles": ["09:00", "18:00"],
                    "jueves": ["09:00", "18:00"],
                    "viernes": ["09:00", "18:00"],
                    "sabado": ["09:00", "14:00"]
                }
            }
        ]
    }
    
    # Guardar
    with open('clientes.json', 'w', encoding='utf-8') as f:
        json.dump(clientes, f, indent=2, ensure_ascii=False)
    
    print("  ✅ Cliente 'dev_local' creado")
    return True

def iniciar_ngrok(puerto=3000):
    """Inicia ngrok en segundo plano"""
    print(f"\n🌐 Iniciando ngrok en puerto {puerto}...")
    
    try:
        # Matar procesos ngrok existentes
        subprocess.run(['pkill', '-f', 'ngrok'], 
                      stderr=subprocess.DEVNULL)
        time.sleep(1)
    except:
        pass
    
    # Iniciar ngrok
    proceso = subprocess.Popen(
        ['ngrok', 'http', str(puerto)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    print("  ⏳ Esperando que ngrok inicie...")
    time.sleep(3)
    
    # Obtener URL pública
    try:
        import requests
        response = requests.get('http://localhost:4040/api/tunnels')
        tunnels = response.json()['tunnels']
        
        if tunnels:
            url_publica = tunnels[0]['public_url']
            print(f"  ✅ ngrok iniciado")
            print(f"  🔗 URL pública: {url_publica}")
            return url_publica, proceso
    except Exception as e:
        print(f"  ⚠️  Error obteniendo URL de ngrok: {e}")
    
    return None, proceso

def configurar_webhook_twilio(url_ngrok):
    """Muestra instrucciones para configurar webhook en Twilio"""
    webhook_url = f"{url_ngrok}/webhook"
    
    print("\n" + "="*60)
    print("📱 CONFIGURACIÓN DE TWILIO")
    print("="*60)
    print("\n1. Ve a tu Sandbox de Twilio:")
    print("   https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn")
    print("\n2. Configura el webhook:")
    print(f"   URL: {webhook_url}")
    print("   Método: HTTP POST")
    print("\n3. Guarda los cambios")
    print("\n4. Envía un WhatsApp a tu sandbox con el código de join")
    print("="*60)

def iniciar_bot(puerto=3000):
    """Inicia el bot en modo desarrollo"""
    print(f"\n🤖 Iniciando bot en puerto {puerto}...")
    
    # Configurar variable de entorno para desarrollo
    os.environ['FLASK_ENV'] = 'development'
    os.environ['FLASK_DEBUG'] = '1'
    
    # Importar y ejecutar el bot
    try:
        import peluqueria_bot_prueba
        peluqueria_bot_prueba.app.run(
            host='0.0.0.0',
            port=puerto,
            debug=True,
            use_reloader=True
        )
    except KeyboardInterrupt:
        print("\n\n👋 Bot detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error iniciando bot: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("="*60)
    print("🚀 INICIANDO BOT EN MODO DESARROLLO LOCAL")
    print("="*60)
    
    # Verificaciones
    if not verificar_dependencias():
        print("\n❌ Instala las dependencias faltantes y vuelve a ejecutar")
        sys.exit(1)
    
    if not verificar_archivos():
        print("\n❌ Asegúrate de tener todos los archivos necesarios")
        sys.exit(1)
    
    if not verificar_ngrok():
        print("\n❌ Instala ngrok y vuelve a ejecutar")
        sys.exit(1)
    
    # Crear cliente de desarrollo
    crear_cliente_desarrollo()
    
    # Preguntar puerto
    puerto = input("\n🔌 Puerto a usar (Enter para 3000): ").strip()
    puerto = int(puerto) if puerto else 3000
    
    # Iniciar ngrok
    url_ngrok, proceso_ngrok = iniciar_ngrok(puerto)
    
    if not url_ngrok:
        print("\n⚠️  No se pudo obtener la URL de ngrok")
        print("   El bot se iniciará de todas formas en localhost")
    else:
        configurar_webhook_twilio(url_ngrok)
    
    # Esperar confirmación
    input("\n⏸️  Presiona ENTER cuando hayas configurado Twilio...")
    
    # Iniciar bot
    try:
        iniciar_bot(puerto)
    finally:
        # Limpiar
        if proceso_ngrok:
            print("\n🛑 Deteniendo ngrok...")
            proceso_ngrok.terminate()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Script detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()