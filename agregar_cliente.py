#!/usr/bin/env python3
"""
Script para agregar nuevos clientes al bot SaaS
Uso: python agregar_cliente.py
"""

import json
import os

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
    
    # Solicitar datos
    print("\n📝 Ingresa los datos del nuevo cliente:")
    
    key = input("ID único (ej: peluqueria_sol): ").strip()
    
    if key in clientes:
        print(f"❌ ERROR: '{key}' ya existe!")
        return
    
    nombre = input("Nombre del negocio: ").strip()
    calendar_id = input("Calendar ID de Google: ").strip()
    email_cliente = input("Email del cliente (opcional): ").strip()
    
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
                break
            try:
                precio = int(input("  Precio (ARS): ").strip())
                duracion = int(input("  Duración (minutos): ").strip())
                servicios.append({
                    "nombre": nombre_servicio,
                    "precio": precio,
                    "duracion": duracion
                })
                print(f"  ✅ '{nombre_servicio}' agregado")
            except ValueError:
                print("  ⚠️ Precio y duración deben ser números")
    
    # Crear estructura
    clientes[key] = {
        "nombre": nombre,
        "calendar_id": calendar_id,
        "token_file": "tokens/master_token.json",  # ← Ajusta según tu configuración
        "servicios": servicios
    }
    
    if email_cliente:
        clientes[key]["owner_email"] = email_cliente
    
    # Guardar
    with open("clientes.json", "w", encoding="utf-8") as f:
        json.dump(clientes, f, indent=2, ensure_ascii=False)
    
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
    agregar_cliente()