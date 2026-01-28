from pymongo import MongoClient
import os

MONGO_URI = os.getenv("mongodb+srv://lucasbenavides710_db_user:5RwceXIRNWPNuShD@cluster0.jbgzzss.mongodb.net/?appName=Cluster0")

client = MongoClient(MONGO_URI)
db = client["peluqueria_bot"]

print("Conectado a MongoDB")

db.test.insert_one({"status": "ok"})
print("Insert OK")

doc = db.test.find_one({"status": "ok"})
print("Find OK:", doc)