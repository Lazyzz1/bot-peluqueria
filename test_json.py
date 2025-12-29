import json

with open("clientes.json", "r", encoding="utf-8") as f:
    data = json.load(f)

victoria = data["cliente_001"]["peluqueros"][0]
jueves = victoria["horarios"]["jueves"]

print(f"Horarios jueves: {jueves}")
print(f"Tipo: {type(jueves)}")
print(f"Primer elemento: {jueves[0]}")
print(f"Tipo primer elemento: {type(jueves[0])}")
print(f"Longitud primer elemento: {len(jueves[0])}")