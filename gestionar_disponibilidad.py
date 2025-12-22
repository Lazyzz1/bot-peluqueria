# gestionar_disponibilidad.py
import json
from datetime import datetime

def listar_peluqueros(cliente_key):
    """Lista todos los peluqueros y su estado"""
    with open('clientes.json', 'r', encoding='utf-8') as f:
        clientes = json.load(f)
    
    config = clientes[cliente_key]
    peluqueros = config.get('peluqueros', [])
    
    print(f"\n👥 Peluqueros de {config['nombre']}:")
    print("="*60)
    
    for i, p in enumerate(peluqueros, 1):
        nombre = p['nombre']
        activo = p.get('activo', True)
        estado = "✅ ACTIVO" if activo else "❌ NO DISPONIBLE"
        
        print(f"\n{i}. {nombre} - {estado}")
        
        if not activo:
            mensaje = p.get('mensaje_no_disponible', 'Sin mensaje')
            fecha_regreso = p.get('fecha_regreso', 'Sin fecha')
            print(f"   Motivo: {mensaje}")
            print(f"   Regreso: {fecha_regreso}")

def cambiar_disponibilidad(cliente_key):
    """Cambia la disponibilidad de un peluquero"""
    with open('clientes.json', 'r', encoding='utf-8') as f:
        clientes = json.load(f)
    
    config = clientes[cliente_key]
    peluqueros = config['peluqueros']
    
    listar_peluqueros(cliente_key)
    
    print("\n" + "="*60)
    opcion = int(input("¿Qué peluquero quieres modificar? (número): ")) - 1
    
    if opcion < 0 or opcion >= len(peluqueros):
        print("❌ Opción inválida")
        return
    
    peluquero = peluqueros[opcion]
    print(f"\n📝 Modificando: {peluquero['nombre']}")
    
    print("\n1. Marcar como NO disponible (vacaciones/ausente)")
    print("2. Marcar como DISPONIBLE (vuelve)")
    accion = input("\nElegí acción (1 o 2): ").strip()
    
    if accion == "1":
        # Poner no disponible
        peluquero['activo'] = False
        
        mensaje = input("Mensaje para clientes (ej: De vacaciones hasta 15/01): ").strip()
        if mensaje:
            peluquero['mensaje_no_disponible'] = mensaje
        
        fecha = input("Fecha de regreso (ej: 2025-01-15) [opcional]: ").strip()
        if fecha:
            peluquero['fecha_regreso'] = fecha
        
        print(f"\n✅ {peluquero['nombre']} marcado como NO DISPONIBLE")
        print(f"   Los clientes NO podrán reservar con él/ella")
        
    elif accion == "2":
        # Poner disponible
        peluquero['activo'] = True
        peluquero['mensaje_no_disponible'] = None
        peluquero['fecha_regreso'] = None
        
        print(f"\n✅ {peluquero['nombre']} marcado como DISPONIBLE")
        print(f"   Los clientes YA pueden reservar turnos")
    
    # Guardar
    clientes[cliente_key] = config
    with open('clientes.json', 'w', encoding='utf-8') as f:
        json.dump(clientes, f, indent=2, ensure_ascii=False)
    
    print("\n💾 Cambios guardados")
    print("🔄 Sube los cambios a Railway:")
    print("   git add clientes.json")
    print("   git commit -m 'Actualizar disponibilidad peluqueros'")
    print("   git push origin main")

if __name__ == "__main__":
    print("🎛️  GESTIÓN DE DISPONIBILIDAD")
    print("="*60)
    
    # Listar clientes
    with open('clientes.json', 'r', encoding='utf-8') as f:
        clientes = json.load(f)
    
    print("\n📋 Clientes:")
    for i, (key, config) in enumerate(clientes.items(), 1):
        print(f"{i}. {config['nombre']} ({key})")
    
    cliente_num = int(input("\nElegí cliente (número): ")) - 1
    cliente_key = list(clientes.keys())[cliente_num]
    
    cambiar_disponibilidad(cliente_key)