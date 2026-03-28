"""
Script para agregar nuevos clientes al bot SaaS
VERSIÓN CORREGIDA - Enero 2026
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
        print(f"💾 Backup creado: {backup}")
        return backup
    return None

def agregar_cliente():
    print("🎯 AGREGAR NUEVO CLIENTE AL BOT SAAS")
    print("="*50)
    
    # Buscar clientes.json en varios lugares
    posibles_rutas = [
        "clientes.json",
        "config/clientes.json",
        "../clientes.json"
    ]
    
    archivo_clientes = None
    for ruta in posibles_rutas:
        if os.path.exists(ruta):
            archivo_clientes = ruta
            break
    
    if not archivo_clientes:
        print("❌ ERROR: No se encontró clientes.json")
        print("   Buscado en:", ", ".join(posibles_rutas))
        print("   Crea el archivo primero o ejecuta desde el directorio correcto")
        return
    
    print(f"✅ Usando: {archivo_clientes}")
    
    # Leer archivo actual
    try:
        with open(archivo_clientes, "r", encoding="utf-8") as f:
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
    
    # Número de Twilio
    numero_twilio = input("Número de Twilio (ej: +14155238886): ").strip()
    while not numero_twilio.startswith('+'):
        print("⚠️ El número debe empezar con + (ej: +14155238886)")
        numero_twilio = input("Número de Twilio: ").strip()
    
    # Email con validación
    while True:
        email_cliente = input("Email del cliente (opcional, Enter para omitir): ").strip()
        if not email_cliente or validar_email(email_cliente):
            break
        print("❌ Formato de email inválido")
    
    # Timezone
    print("\n🌍 Timezone (Enter para default 'America/Argentina/Buenos_Aires'): ")
    timezone = input("Timezone: ").strip() or "America/Argentina/Buenos_Aires"
    
    # Moneda
    print("\n💰 Moneda (Enter para default 'ARS'): ")
    moneda = input("Moneda: ").strip().upper() or "ARS"
    
    # Preguntar por servicios personalizados
    print("\n¿Deseas usar servicios por defecto? (s/n): ", end="")
    usar_default = input().strip().lower()
    
    if usar_default == 's':
        servicios = [
            {"nombre": "Corte clásico", "precio": 15000, "duracion": 30},
            {"nombre": "Corte moderno", "precio": 18000, "duracion": 45},
            {"nombre": "Barba y bigote", "precio": 5000, "duracion": 20},
            {"nombre": "Tintura", "precio": 20000, "duracion": 60}
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
                precio = int(input("  Precio (números sin puntos): ").strip())
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
    
    # Preguntar por peluqueros
    print("\n👥 ¿Quieres agregar peluqueros? (s/n): ", end="")
    agregar_peluqueros = input().strip().lower()
    
    peluqueros = []
    if agregar_peluqueros == 's':
        print("\nAgrega peluqueros (deja el nombre vacío para terminar):")
        
        while True:
            nombre_peluquero = input("\n  Nombre del peluquero: ").strip()
            if not nombre_peluquero:
                break
            
            id_peluquero = nombre_peluquero.lower().replace(" ", "_")
            
            # Pedir teléfono del peluquero
            print(f"\n  Teléfono de {nombre_peluquero}:")
            print("  Formato: +5491123456789 (con código de país)")
            print("  Déjalo vacío si no quiere recibir notificaciones")
            telefono_peluquero = input("  Teléfono: ").strip()
            
            # Especialidades
            print(f"\n  Especialidades de {nombre_peluquero}:")
            print("  Servicios disponibles:")
            for i, serv in enumerate(servicios):
                print(f"    {i+1}. {serv['nombre']}")
            
            especialidades = []
            print("\n  Ingresa los números separados por coma (ej: 1,2,3):")
            especialidades_input = input("  Especialidades: ").strip()
            
            try:
                indices = [int(x.strip()) - 1 for x in especialidades_input.split(",")]
                for idx in indices:
                    if 0 <= idx < len(servicios):
                        especialidades.append(servicios[idx]["nombre"])
            except:
                print("  ⚠️  Formato inválido, se agregará sin especialidades")
            
            # Días de trabajo
            print("\n  Días de trabajo:")
            print("  1=Lun, 2=Mar, 3=Mié, 4=Jue, 5=Vie, 6=Sáb")
            dias_input = input("  Ingresa números separados por coma (ej: 1,2,3,4,5): ").strip()
            
            dias_map = {
                "1": "lunes", "2": "martes", "3": "miercoles",
                "4": "jueves", "5": "viernes", "6": "sabado"
            }
            
            dias_trabajo = []
            horarios = {}
            
            try:
                for d in dias_input.split(","):
                    d = d.strip()
                    if d in dias_map:
                        dia_nombre = dias_map[d]
                        dias_trabajo.append(dia_nombre)
                        
                        # Horarios para este día
                        print(f"\n  Horario para {dia_nombre.capitalize()}:")
                        hora_inicio = input("    Hora inicio (ej: 09:00): ").strip()
                        hora_fin = input("    Hora fin (ej: 18:00): ").strip()
                        horarios[dia_nombre] = [hora_inicio, hora_fin]
            except:
                print("  ⚠️  Error en horarios")
            
            # Crear peluquero
            peluquero = {
                "id": id_peluquero,
                "nombre": nombre_peluquero,
                "telefono": telefono_peluquero,
                "activo": True,  # Por defecto activo
                "mensaje_no_disponible": None,
                "fecha_regreso": None,
                "especialidades": especialidades,
                "dias_trabajo": dias_trabajo,
                "horarios": horarios
            }
            
            peluqueros.append(peluquero)
            print(f"  ✅ '{nombre_peluquero}' agregado")
    
    # Crear estructura del cliente
    nuevo_cliente = {
        "nombre": nombre,
        "numero_twilio": numero_twilio,
        "calendar_id": calendar_id,
        "token_file": f"tokens/{key}_token.json",
        "timezone": timezone,
        "idioma": "es",
        "moneda": moneda,
        "requiere_pago": False,  # Por defecto sin pagos
        "servicios": servicios,
        "peluqueros": peluqueros
    }
    
    # Agregar campos opcionales
    if email_cliente:
        nuevo_cliente["owner_email"] = email_cliente
    
    # Asignar al diccionario principal
    clientes[key] = nuevo_cliente
    
    # Mostrar resumen y confirmar
    print("\n" + "="*50)
    print("📋 RESUMEN DEL NUEVO CLIENTE:")
    print("="*50)
    print(f"ID: {key}")
    print(f"Nombre: {nombre}")
    print(f"Calendar ID: {calendar_id}")
    print(f"Número Twilio: {numero_twilio}")
    print(f"Email: {email_cliente or '(no especificado)'}")
    print(f"Timezone: {timezone}")
    print(f"Moneda: {moneda}")
    print(f"Servicios: {len(servicios)}")
    for serv in servicios:
        print(f"  - {serv['nombre']}: ${serv['precio']:,} ({serv['duracion']} min)")
    print(f"Peluqueros: {len(peluqueros)}")
    for p in peluqueros:
        print(f"  - {p['nombre']} ({len(p['especialidades'])} especialidades)")
    print("="*50)
    print("\n¿Confirmar y guardar? (s/n): ", end="")
    
    if input().strip().lower() != 's':
        print("❌ Operación cancelada")
        return
    
    # Hacer backup
    hacer_backup(archivo_clientes)
    
    # Guardar (CORREGIDO - sin sobrescribir)
    try:
        with open(archivo_clientes, "w", encoding="utf-8") as f:
            json.dump(clientes, f, indent=2, ensure_ascii=False)
        
        print("\n✅ Cliente agregado exitosamente!")
    except Exception as e:
        print(f"❌ ERROR al guardar: {e}")
        return
    
    # Próximos pasos
    print("\n📋 PRÓXIMOS PASOS:")
    print("1. Compra un número de Twilio:")
    print("   https://console.twilio.com/us1/develop/phone-numbers/manage/search")
    print(f"   - Asegúrate de habilitar WhatsApp")
    print(f"   - Configura el webhook: https://tu-dominio.railway.app/api/webhook")

    print("\n2. Crea un calendario en Google Calendar:")
    print(f"   'Turnos - {nombre}'")

    print("\n3. Configura el Calendar ID:")
    print(f"   - Verifica que sea: {calendar_id}")

    print("\n4. Comparte el calendario:")
    if email_cliente:
        print(f"   - Con: {email_cliente}")

    print("\n💰 MODELO DE COBRO SaaS:")
    print(f"   Cobra al cliente: USD $80-100/mes")
    print(f"   Costos por cliente:")
    print(f"   - Número Twilio: ~USD $1-2/mes")
    print(f"   - Mensajes: ~USD $1-3/mes")
    print(f"   - Google Calendar: GRATIS")
    print(f"   Tu ganancia: ~USD $75-96/mes por cliente")
    print(f"\n📊 Con 10 clientes: ~USD $750-960/mes de ganancia")
    print(f"📊 Con 50 clientes: ~USD $3,750-4,800/mes de ganancia")

if __name__ == "__main__":
    try:
        agregar_cliente()
    except KeyboardInterrupt:
        print("\n\n❌ Operación cancelada por el usuario")
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}")
        import traceback
        traceback.print_exc()