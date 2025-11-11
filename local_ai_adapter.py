from flask import Flask, request, jsonify
from pymongo import MongoClient
import random

app = Flask(__name__)

# 🔌 Conexión a MongoDB
MONGO_URI = "mongodb://localhost:27017"
client = MongoClient(MONGO_URI)
db = client["fitness_db"]

# 💾 Base de conocimiento de eventos
EVENT_IMPACT = {
    "fiesta": {"calorias": 600, "compensar_dias": 3, "tipo": "exceso"},
    "viaje": {"calorias": 400, "compensar_dias": 2, "tipo": "exceso"},
    "enfermedad": {"calorias": -300, "compensar_dias": 2, "tipo": "deficit"},
    "estrés": {"calorias": 200, "compensar_dias": 1, "tipo": "exceso_leve"},
    "día_libre": {"calorias": 300, "compensar_dias": 2, "tipo": "exceso"},
}

# 🍽️ Comidas como objetos (Mongo requiere objetos, no strings)
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

@app.route('/adapt', methods=['POST'])
def adapt_plan():
    data = request.get_json()
    user_id = data.get("userId")
    event_type = data.get("eventType", "").lower()
    day = data.get("day", "").lower()
    plan = data.get("plan")

    if event_type not in EVENT_IMPACT:
        return jsonify({"error": f"Evento '{event_type}' no reconocido"}), 400

    event = EVENT_IMPACT[event_type]
    compensar_dias = event["compensar_dias"]
    tipo = event["tipo"]

    week_days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    event_index = week_days.index(day) if day in week_days else 0

    updated_plan = plan.copy()

    for i in range(1, compensar_dias + 1):
        idx = (event_index + i) % len(week_days)
        day_to_adjust = week_days[idx]

        if "exceso" in tipo:
            updated_plan[day_to_adjust] = random.choices(COMPENSATION_MEALS["ligero"], k=3)
        elif "deficit" in tipo:
            updated_plan[day_to_adjust] = random.choices(COMPENSATION_MEALS["proteico"], k=3)
        else:
            updated_plan[day_to_adjust] = random.choices(COMPENSATION_MEALS["detox"], k=3)

    # Guardar evento
    db.user_events.insert_one({
        "userId": user_id,
        "event": event_type,
        "day": day,
        "adjusted_days": compensar_dias
    })

    return jsonify({
        "message": f"Plan ajustado automáticamente por evento '{event_type}'",
        "updatedPlan": updated_plan
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
