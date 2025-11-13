from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import random
import numpy as np
from sklearn.linear_model import LinearRegression
import os

app = Flask(__name__)

# Configuración MongoDB
MONGO_URI = os.environ.get("MONGO_URL")

try:
    if MONGO_URI:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client["fitness_db"]
        print("✅ MongoDB conectado")
    else:
        print("⚠️ MONGO_URL no definida")
        client = None
        db = None
except Exception as e:
    print(f"❌ Error MongoDB: {e}")
    client = None
    db = None

EVENT_IMPACT = {
    "fiesta": {"calorias": 600, "compensar_dias": 3, "tipo": "exceso"},
    "viaje": {"calorias": 400, "compensar_dias": 2, "tipo": "exceso"},
    "enfermedad": {"calorias": -300, "compensar_dias": 2, "tipo": "deficit"},
    "estrés": {"calorias": 200, "compensar_dias": 1, "tipo": "exceso_leve"},
    "día_libre": {"calorias": 300, "compensar_dias": 2, "tipo": "exceso"},
}

COMPENSATION_MEALS = {
    "ligero": [
        {"name": "ensalada de pollo", "calories": 150},
        {"name": "sopa de verduras", "calories": 100},
        {"name": "atún con pepino", "calories": 120},
        {"name": "pollo al vapor", "calories": 180}
    ],
    "proteico": [
        {"name": "omelette de claras", "calories": 200},
        {"name": "pollo a la plancha", "calories": 220},
        {"name": "batido de proteína", "calories": 250},
        {"name": "tofu con vegetales", "calories": 180}
    ],
    "detox": [
        {"name": "ensalada verde", "calories": 90},
        {"name": "jugos naturales", "calories": 80},
        {"name": "sopa de lentejas", "calories": 120},
        {"name": "puré de calabaza", "calories": 110}
    ]
}

def train_model():
    if db is None:
        return None
        
    events = list(db.user_events.find({}))
    if len(events) < 3:
        return None
    X, y = [], []
    for e in events:
        tipo_evento = e.get("event", "")
        if tipo_evento in EVENT_IMPACT:
            calorias = EVENT_IMPACT[tipo_evento]["calorias"]
            compensar = e.get("adjusted_days", EVENT_IMPACT[tipo_evento]["compensar_dias"])
            X.append([calorias])
            y.append(compensar)
    if len(X) < 3:
        return None
    model = LinearRegression()
    model.fit(X, y)
    return model

@app.route('/')
def home():
    return jsonify({
        "message": "Fitness API funcionando en Railway!",
        "status": "active",
        "mongo_connected": db is not None
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "mongo_connected": db is not None})

@app.route('/adapt', methods=['POST'])
def adapt_plan():
    if db is None:
        return jsonify({"error": "Base de datos no disponible"}), 500
        
    data = request.get_json()
    if not data:
        return jsonify({"error": "Falta el cuerpo JSON"}), 400

    user_id = data.get("userId")
    event_type = data.get("eventType", "").lower()
    day = data.get("day", "").lower()
    plan = data.get("plan")

    if not user_id or not plan:
        return jsonify({"error": "Faltan campos obligatorios: userId y plan"}), 400
    if event_type not in EVENT_IMPACT:
        return jsonify({"error": f"Evento '{event_type}' no reconocido"}), 400

    # ✅ CORREGIDO: No buscar usuario en MongoDB, solo usar el ID para registrar el evento
    try:
        # Solo verificar que el ID tenga formato válido, pero no buscar el usuario
        if not ObjectId.is_valid(user_id):
            return jsonify({"error": f"ID de usuario '{user_id}' no válido"}), 400
    except:
        return jsonify({"error": f"ID de usuario '{user_id}' no válido"}), 400

    event = EVENT_IMPACT[event_type]
    tipo = event["tipo"]
    calorias_evento = event["calorias"]

    model = train_model()
    compensar_dias = int(round(model.predict([[calorias_evento]])[0])) if model else event["compensar_dias"]

    week_days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    event_index = week_days.index(day) if day in week_days else 0

    updated_plan = plan.copy()
    for i in range(1, compensar_dias + 1):
        idx = (event_index + i) % len(week_days)
        day_to_adjust = week_days[idx]
        if day_to_adjust in updated_plan:
            new_meals = random.choices(
                COMPENSATION_MEALS["ligero"] if "exceso" in tipo else
                COMPENSATION_MEALS["proteico"] if "deficit" in tipo else
                COMPENSATION_MEALS["detox"],
                k=3
            )
            updated_plan[day_to_adjust] = new_meals

    # Registrar el evento sin verificar si el usuario existe
    db.user_events.insert_one({
        "userId": user_id,
        "event": event_type,
        "day": day,
        "adjusted_days": compensar_dias
    })

    return jsonify({
        "message": f"Plan ajustado automáticamente por evento '{event_type}' (predicción ML: {compensar_dias} días)",
        "updatedPlan": updated_plan
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Servidor iniciado en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False)