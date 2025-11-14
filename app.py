from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import random
import numpy as np
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

# Conexión a MongoDB
MONGO_URI = os.getenv("MONGO_URL", "mongodb://localhost:27017")

client = MongoClient(MONGO_URI)
db = client["fitness_db"]

# Impacto de eventos
EVENT_IMPACT = {
    "fiesta": {"calorias": 600, "compensar_dias": 3, "tipo": "exceso"},
    "viaje": {"calorias": 400, "compensar_dias": 2, "tipo": "exceso"},
    "enfermedad": {"calorias": -300, "compensar_dias": 2, "tipo": "deficit"},
    "estrés": {"calorias": 200, "compensar_dias": 1, "tipo": "exceso_leve"},
    "día_libre": {"calorias": 300, "compensar_dias": 2, "tipo": "exceso"},
}

# Comidas de compensación
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

# Entrenar modelo simple
def train_model():
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

@app.route('/adapt', methods=['POST'])
@app.route('/api/plans/adapt', methods=['POST'])
def adapt_plan():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Falta el cuerpo JSON"}), 400

    user_id = data.get("userId")
    event_type = data.get("eventType", "").lower()
    day = data.get("day", "").lower()
    plan = data.get("plan")

    if not user_id or not plan:
        return jsonify({"error": "Faltan campos obligatorios (userId, plan)"}), 400
    if event_type not in EVENT_IMPACT:
        return jsonify({"error": f"Evento '{event_type}' no reconocido"}), 400

    # Buscar usuario
    try:
        user_data = db.users.find_one({"_id": ObjectId(user_id)})
    except:
        return jsonify({"error": f"ID de usuario '{user_id}' no válido"}), 400

    if not user_data:
        return jsonify({"error": f"Usuario con ID '{user_id}' no encontrado"}), 404

    event = EVENT_IMPACT[event_type]
    tipo = event["tipo"]
    calorias_evento = event["calorias"]

    # Predecir días a compensar
    model = train_model()
    compensar_dias = int(round(model.predict([[calorias_evento]])[0])) if model else event["compensar_dias"]

    week_days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    event_index = week_days.index(day) if day in week_days else 0

    # Actualizar solo los días necesarios
    updated_plan = plan.copy()
    for i in range(1, compensar_dias + 1):
        idx = (event_index + i) % len(week_days)
        day_to_adjust = week_days[idx]

        # Mantener _id original si existe
        if day_to_adjust in updated_plan:
            original_meals = updated_plan[day_to_adjust]
            new_meals = random.choices(
                COMPENSATION_MEALS["ligero"] if "exceso" in tipo else
                COMPENSATION_MEALS["proteico"] if "deficit" in tipo else
                COMPENSATION_MEALS["detox"],
                k=3
            )
            for j in range(3):
                original_meals[j]["name"] = new_meals[j]["name"]
                original_meals[j]["calories"] = new_meals[j]["calories"]
            updated_plan[day_to_adjust] = original_meals

    # Guardar evento
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

if __name__ == '__main__':
    print("✅ Conectado a MongoDB")
    app.run(host='0.0.0.0', port=8000, debug=True)