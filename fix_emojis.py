# fix_emojis.py
import re

def fix_emoji_numbers(codigo):
    """
    Reemplaza {i+1}️⃣ por formatear_item_lista(i, ...)
    """
    # Patrón para encontrar: f"{i+1}️⃣ {algo}"
    patron = r'f"{i\+1}️⃣\s+([^"]+)"'
    
    def reemplazo(match):
        contenido = match.group(1)
        return f'formatear_item_lista(i, f"{contenido}")'
    
    return re.sub(patron, reemplazo, codigo)

# Leer archivo
with open('peluqueria_bot_prueba.py', 'r', encoding='utf-8') as f:
    codigo = f.read()

# Aplicar fix
codigo_fijo = fix_emoji_numbers(codigo)

# Guardar
with open('peluqueria_bot_prueba_fixed.py', 'w', encoding='utf-8') as f:
    f.write(codigo_fijo)

print("✅ Archivo fijo generado: peluqueria_bot_prueba_fixed.py")
print("   Revisa los cambios y reemplaza el original si está bien")


## 🎨 Ejemplo visual del antes/después

### ANTES (con el bug):
"""
Horarios disponibles:

1️⃣ 09:00
2️⃣ 09:30
3️⃣ 10:00
...
9️⃣ 13:00
️0 13:30  ← BUG
️1 14:00  ← BUG
️2 14:30  ← BUG
```

### DESPUÉS (corregido):
```
Horarios disponibles:

1️⃣ 09:00
2️⃣ 09:30
3️⃣ 10:00
...
9️⃣ 13:00
*10.* 13:30  ← Corregido
*11.* 14:00  ← Corregido
*12.* 14:30  ← Corregido
"""