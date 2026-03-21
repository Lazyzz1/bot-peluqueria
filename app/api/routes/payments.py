"""
Rutas de Pagos - Blueprint Flask
Recibe el formulario de contratación, guarda el cliente en MongoDB
y devuelve el link de pago.
"""

from flask import Blueprint, request, jsonify
from datetime import datetime

# Usa directamente clientes_collection de tu database.py existente
from app.core.database import clientes_collection
from app.services.payment_service import payment_service

payments_routes_bp = Blueprint("payments_routes", __name__)


@payments_routes_bp.route("/payments/checkout", methods=["POST"])
def crear_checkout():
    """
    Flujo:
    1. Recibe datos del formulario de contratación (ContratarModal.tsx)
    2. Guarda el cliente en MongoDB con estado 'pendiente'
    3. Genera link de pago (MercadoPago o LemonSqueezy según el plan)
    4. Devuelve el link al frontend
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No se recibieron datos"}), 400

        # Validar campos obligatorios
        campos_requeridos = [
            "nombre", "apellido", "email", "telefono",
            "nombre_negocio", "ubicacion", "horarios",
            "servicios", "cantidad_peluqueros", "peluqueros", "plan"
        ]
        for campo in campos_requeridos:
            if not data.get(campo):
                return jsonify({"error": f"Falta el campo: {campo}"}), 400

        if data["plan"] not in ["argentina", "internacional"]:
            return jsonify({"error": "Plan inválido"}), 400

        # Guardar cliente en MongoDB
        cliente_doc = {
            "nombre":              data["nombre"],
            "apellido":            data["apellido"],
            "email":               data["email"],
            "telefono":            data["telefono"],
            "nombre_negocio":      data["nombre_negocio"],
            "ubicacion":           data["ubicacion"],
            "horarios":            data["horarios"],
            "servicios":           data["servicios"],
            "cantidad_peluqueros": int(data["cantidad_peluqueros"]),
            "peluqueros":          data["peluqueros"],  # [{"nombre": str, "telefono": str}]
            "plan":                data["plan"],
            "estado_pago":         "pendiente",
            "bot_configurado":     False,
            "creado_en":           datetime.utcnow(),
            "actualizado_en":      datetime.utcnow(),
        }

        result = clientes_collection.insert_one(cliente_doc)
        cliente_id = str(result.inserted_id)

        # Generar link de pago con tu payment_service
        pago = payment_service.crear_pago_onboarding(
            cliente_id=cliente_id,
            email=data["email"],
            nombre=f"{data['nombre']} {data['apellido']}",
            nombre_negocio=data["nombre_negocio"],
            plan=data["plan"],
        )

        if not pago:
            return jsonify({"error": "No se pudo generar el link de pago. Revisá las variables de entorno."}), 500

        payment_url = pago["url"]

        # Actualizar cliente con el link de pago
        from bson import ObjectId
        clientes_collection.update_one(
            {"_id": ObjectId(cliente_id)},
            {"$set": {
                "payment_url":    payment_url,
                "payment_id":     pago.get("preference_id") or pago.get("checkout_id"),
                "actualizado_en": datetime.utcnow(),
            }},
        )

        print(f"✅ Cliente guardado y link generado: {cliente_id} - {data['nombre_negocio']}")

        return jsonify({
            "id":          cliente_id,
            "payment_url": payment_url,
            "mensaje":     "Datos guardados. Completá el pago para reservar tu lugar.",
        }), 201

    except Exception as e:
        print(f"❌ Error en crear_checkout: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500