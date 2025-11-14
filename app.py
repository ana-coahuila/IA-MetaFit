from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import random
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

# ======================================
# 🔥 CONEXIÓN A MONGO RAILWAY (FINAL)
# ======================================
mongo_url = os.getenv("MONGO_URL")

if not mongo_url:
    raise Exception("❌ ERROR: No existe la variable MONGO_URL en Railway")

try:
    client = MongoClient(mongo_url)
    db = client.get_default_database()  # Railway asigna la DB automáticamente

    users_col = db["users"]
    user_events_col = db["user_events"]

    print("✅ Conectado exitosamente a MongoDB Railway")

except Exception as e:
    print("❌ Error conectando a MongoDB:", e)
    db = None


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
# 🔥 ENDPOINT TEST
# ======================================

@app.route("/")
def home():
    return jsonify({
        "message": "IA Flask funcionando en Railway",
        "mongo_connected": db is not None
    })


@app.route("/test-db")
def test_db():
    try:
        data = list(users_col.find({}, {"_id": 0}))
        return jsonify({"ok": True, "users": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ======================================
# 🔥 ENDPOINT PRINCIPAL /adapt
# ======================================

@app.route("/adapt", methods=["POST"])
def adapt_plan():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON inválido"}), 400

        user_id = data.get("userId")
        event_type = data.get("eventType", "").lower()
        day = data.get("day", "").lower()
        plan = data.get("plan")

        if not user_id or not plan:
            return jsonify({"error": "Datos incompletos"}), 400

        if event_type not in EVENT_IMPACT:
            return jsonify({"error": "Evento inválido"}), 400

        try:
            ObjectId(user_id)
        except:
            return jsonify({"error": "ID inválido"}), 400

        event = EVENT_IMPACT[event_type]
        calorias = event["calorias"]

        model = train_model()
        compensar = int(round(model.predict([[calorias]])[0])) if model else event["compensar_dias"]

        week_days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        idx = week_days.index(day) if day in week_days else 0

        updated = plan.copy()

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
            "message": f"Evento procesado ({event_type})",
            "updatedPlan": updated
        })

    except Exception as e:
        print("❌ ERROR adapt:", e)
        return jsonify({"error": str(e)}), 500


# ======================================
# 🔥 RUN
# ======================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Servidor listo en puerto {port}")
    app.run(host="0.0.0.0", port=port)
