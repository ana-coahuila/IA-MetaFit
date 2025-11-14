from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import random
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

# ======================================
# CONEXIÓN A MONGO RAILWAY
# ======================================
mongo_url = os.getenv("MONGO_URL")
db_name = os.getenv("MONGO_DB", "test")

if not mongo_url:
    raise Exception("❌ ERROR: No existe la variable MONGO_URL en Railway")

try:
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    client.server_info()  # Test conexión

    users_col = db["users"]
    user_events_col = db["user_events"]

    print("✅ Conectado exitosamente a MongoDB Railway")

except Exception as e:
    print("❌ Error conectando a MongoDB:", e)
    db = None
    users_col = None
    user_events_col = None


# ======================================
# DATOS BASE
# ======================================

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


# ======================================
# 🔥 MODELO ML
# ======================================

def train_model():
    if db is None:
        return None

    try:
        events = list(user_events_col.find({}))
        if len(events) < 3:
            return None

        X, y = [], []
        for e in events:
            tipo = e.get("event")
            if tipo in EVENT_IMPACT:
                X.append([EVENT_IMPACT[tipo]["calorias"]])
                y.append(e.get("adjusted_days", EVENT_IMPACT[tipo]["compensar_dias"]))

        if len(X) < 3:
            return None

        model = LinearRegression()
        model.fit(X, y)
        return model

    except Exception as e:
        print("❌ Error entrenando modelo:", e)
        return None


# ======================================
# ROUTES
# ======================================

@app.route("/")
def home():
    return jsonify({
        "message": "IA Flask funcionando correctamente",
        "mongo_connected": db is not None
    })


@app.route("/adapt", methods=["POST"])
def adapt_plan():
    try:
        if db is None:
            return jsonify({"error": "DB no conectada"}), 500

        data = request.get_json()
        user_id = data.get("userId")
        event_type = data.get("eventType", "").lower()
        day = data.get("day", "").lower()
        plan = data.get("plan")

        if not user_id or not plan or event_type not in EVENT_IMPACT:
            return jsonify({"error": "Datos incompletos"}), 400

        event = EVENT_IMPACT[event_type]
        calorias = event["calorias"]

        model = train_model()
        compensar = int(round(model.predict([[calorias]])[0])) if model else event["compensar_dias"]

        week_days = ["monday", "tuesday", "wednesday", "thursday",
                     "friday", "saturday", "sunday"]

        if day not in week_days:
            return jsonify({"error": "Día inválido"}), 400

        idx = week_days.index(day)
        updated = plan

        for i in range(1, compensar + 1):
            d = week_days[(idx + i) % 7]

            tipo = event["tipo"]
            if "exceso" in tipo:
                meals = COMPENSATION_MEALS["ligero"]
            elif "deficit" in tipo:
                meals = COMPENSATION_MEALS["proteico"]
            else:
                meals = COMPENSATION_MEALS["detox"]

            updated[d] = random.choices(meals, k=3)

        user_events_col.insert_one({
            "userId": user_id,
            "event": event_type,
            "day": day,
            "adjusted_days": compensar
        })

        return jsonify({
            "message": "Plan ajustado con éxito",
            "updatedPlan": updated
        })

    except Exception as e:
        print("❌ ERROR /adapt:", e)
        return jsonify({"error": str(e)}), 500


# ======================================
# RUN
# ======================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))  # Railway asigna PORT automático
    print(f"🚀 Servidor corriendo en puerto {port}")
    app.run(host="0.0.0.0", port=port)
