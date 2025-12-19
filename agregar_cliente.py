
"""
Script para agregar nuevos clientes al bot SaaS
Uso: python agregar_cliente.py
"""

import json
import os
import re
from datetime import datetime

def validar_calendar_id(calendar_id):
    """Valida formato básico de Calendar ID de Google"""
    # Formato: algo@group.calendar.google.com o email@gmail.com
    patron = r'^[a-zA-Z0-9._-]+@(group\.calendar\.google\.com|gmail\.com)$'
    return re.match(patron, calendar_id) is not None

def validar_email(email):
    """Valida formato básico de email"""
    if not email:
        return True  # Email opcional
    patron = r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(patron, email) is not None

def hacer_backup(archivo):
    """Crea backup del archivo antes de modificarlo"""
    if os.path.exists(archivo):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{archivo}.backup_{timestamp}"
        with open(archivo, 'r', encoding='utf-8') as f:
            contenido = f.read()
        with open(backup, 'w', encoding='utf-8') as f:
            f.write(contenido)
        return backup
    return None

def agregar_cliente():
    print("🎯 AGREGAR NUEVO CLIENTE AL BOT SAAS")
    print("="*50)
    
    # Verificar que existe clientes.json
    if not os.path.exists("clientes.json"):
        print("❌ ERROR: No se encontró clientes.json")
        print("   Crea el archivo primero o copia clientes.json.example")
        return
    
    # Leer archivo actual
    try:
        with open("clientes.json", "r", encoding="utf-8") as f:
            clientes = json.load(f)
    except json.JSONDecodeError:
        print("❌ ERROR: clientes.json está corrupto")
        return
    except Exception as e:
        print(f"❌ ERROR al leer archivo: {e}")
        return
    
    # Solicitar datos con validación
    print("\n📝 Ingresa los datos del nuevo cliente:")
    
    # Key con validación
    while True:
        key = input("ID único (ej: peluqueria_sol): ").strip()
        if not key:
            print("❌ El ID no puede estar vacío")
            continue
        if key in clientes:
            print(f"❌ ERROR: '{key}' ya existe!")
            continue
        if not re.match(r'^[a-z0-9_]+$', key):
            print("❌ Solo usa letras minúsculas, números y guiones bajos")
            continue
        break
    
    # Nombre con validación
    while True:
        nombre = input("Nombre del negocio: ").strip()
        if nombre:
            break
        print("❌ El nombre no puede estar vacío")
    
    # Calendar ID con validación
    while True:
        calendar_id = input("Calendar ID de Google: ").strip()
        if not calendar_id:
            print("❌ El Calendar ID no puede estar vacío")
            continue
        if not validar_calendar_id(calendar_id):
            print("⚠️  Formato inválido. Debe ser: algo@group.calendar.google.com")
            print("   ¿Continuar de todas formas? (s/n): ", end="")
            if input().strip().lower() == 's':
                break
            continue
        break
    
    # Email con validación
    while True:
        email_cliente = input("Email del cliente (opcional, Enter para omitir): ").strip()
        if not email_cliente or validar_email(email_cliente):
            break
        print("❌ Formato de email inválido")
    
    # Preguntar por servicios personalizados
    print("\n¿Deseas usar servicios por defecto? (s/n): ", end="")
    usar_default = input().strip().lower()
    
    if usar_default == 's':
        servicios = [
            {"nombre": "Corte clásico", "precio": 13000, "duracion": 30},
            {"nombre": "Barba y bigote", "precio": 3000, "duracion": 20},
            {"nombre": "Tintura", "precio": 12000, "duracion": 60}
        ]
    else:
        servicios = []
        print("\nAgrega servicios (deja el nombre vacío para terminar):")
        while True:
            nombre_servicio = input("  Nombre del servicio: ").strip()
            if not nombre_servicio:
                if not servicios:
                    print("  ⚠️  Debes agregar al menos un servicio")
                    continue
                break
            try:
                precio = int(input("  Precio (ARS): ").strip())
                duracion = int(input("  Duración (minutos): ").strip())
                
                if precio <= 0 or duracion <= 0:
                    print("  ❌ El precio y duración deben ser mayores a 0")
                    continue
                    
                servicios.append({
                    "nombre": nombre_servicio,
                    "precio": precio,
                    "duracion": duracion
                })
                print(f"  ✅ '{nombre_servicio}' agregado")
            except ValueError:
                print("  ⚠️  Precio y duración deben ser números")
    
    # Crear estructura
    nuevo_cliente = {
        "nombre": nombre,
        "calendar_id": calendar_id,
        "token_file": "tokens/master_token.json",
        "servicios": servicios
    }
    
    if email_cliente:
        nuevo_cliente["owner_email"] = email_cliente
    
    # Mostrar resumen y confirmar
    print("\n" + "="*50)
    print("📋 RESUMEN DEL NUEVO CLIENTE:")
    print("="*50)
    print(f"ID: {key}")
    print(f"Nombre: {nombre}")
    print(f"Calendar ID: {calendar_id}")
    print(f"Email: {email_cliente or '(no especificado)'}")
    print(f"Servicios: {len(servicios)}")
    for serv in servicios:
        print(f"  - {serv['nombre']}: ${serv['precio']} ({serv['duracion']} min)")
    print("="*50)
    print("\n¿Confirmar y guardar? (s/n): ", end="")
    
    if input().strip().lower() != 's':
        print("❌ Operación cancelada")
        return
    
    # Hacer backup
    backup_file = hacer_backup("clientes.json")
    if backup_file:
        print(f"💾 Backup creado: {backup_file}")
    
    # Guardar
    try:
        clientes[key] = nuevo_cliente
        with open("clientes.json", "w", encoding="utf-8") as f:
            json.dump(clientes, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ ERROR al guardar: {e}")
        if backup_file:
            print(f"   Puedes restaurar desde: {backup_file}")
        return
    
    print("\n✅ Cliente agregado exitosamente!")
    print("\n📋 PRÓXIMOS PASOS:")
    print("1. Crea un calendario en Google Calendar llamado:")
    print(f"   'Turnos - {nombre}'")
    print("\n2. Obtén el Calendar ID:")
    print("   - Ve a Configuración del calendario")
    print("   - Busca 'ID del calendario'")
    print(f"   - Verifica que sea: {calendar_id}")
    print("\n3. Comparte el calendario:")
    if email_cliente:
        print(f"   - Con: {email_cliente}")
        print("   - Permisos: 'Hacer cambios en eventos'")
    else:
        print("   - Con el email del cliente")
        print("   - Permisos: 'Hacer cambios en eventos'")
    print("\n4. Configura el número de WhatsApp:")
    print("   - El bot detecta automáticamente por el número Twilio")
    print("   - Asegúrate de tener un número Twilio asignado a este cliente")
    print("\n5. Reinicia el bot:")
    print("   python peluqueria_bot_prueba.py")
    print("\n💰 MODELO DE COBRO:")
    print(f"   Cobra al cliente: USD $60/mes")
    print(f"   Costos estimados:")
    print(f"   - Número Twilio: ~USD $1/mes")
    print(f"   - Mensajes: ~USD $1-3/mes (según uso)")
    print(f"   Tu ganancia: ~USD $56-58/mes por cliente")
    print("\n📊 Con 10 clientes: ~USD $560/mes de ganancia neta")

if __name__ == "__main__":
    try:
        agregar_cliente()
    except KeyboardInterrupt:
        print("\n\n❌ Operación cancelada por el usuario")
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}")