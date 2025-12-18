#!/usr/bin/env python3
"""
Crea backup de archivos importantes
Uso: python backup.py
"""

import shutil
import os
from datetime import datetime

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = f"backup_{timestamp}"

os.makedirs(backup_dir, exist_ok=True)

archivos = [
    "clientes.json",
    "recordatorios_enviados.json",
    ".env"
]

print(f"💾 Creando backup en: {backup_dir}/")

for archivo in archivos:
    if os.path.exists(archivo):
        shutil.copy(archivo, backup_dir)
        print(f"  ✅ {archivo}")
    else:
        print(f"  ⏭️ {archivo} no existe")

# Backup de tokens
if os.path.exists("tokens"):
    shutil.copytree("tokens", f"{backup_dir}/tokens")
    print(f"  ✅ tokens/")

print(f"\n✅ Backup completado: {backup_dir}/")