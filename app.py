from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import random
from sklearn.linear_model import LinearRegression
import os

app = Flask(__name__)

# ============================================
# 🔥 CONFIGURACIÓN MONGODB RAILWAY
# ============================================

MONGO_URI = os.getenv("MONGO_URL")
MONGO_DB = os.getenv("MONGO_DB", "production")
PORT = int(os.getenv("PORT", 8000))

if not MONGO_URI:
    raise ValueError("❌ ERROR: Debes definir MONGO_URL en Railway")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[MONGO_DB]

    # forzar prueba de conexión
    client.server_info()

    users_col = db["users"]
    user_events_col = db["user_events"]

    print("✅ Conectado correctamente a MongoDB de Railway")

except Exception as e:
    print(f"❌ ERROR CRÍTICO MongoDB: {e}")
    db = None
    users_col = None
    user_events_col = None


# ============================================
# CONSTANTES
# ============================================

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


# ============================================
# MODELO ML
# ============================================

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


# ============================================
# RUTA TEST
# ============================================

@app.route("/")
def home():
    return jsonify({
        "message": "IA Flask funcionando en Railway",
        "mongo_connected": db is not None
    })


# ============================================
# ADAPTAR PLAN
# ============================================

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
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        if event_type not in EVENT_IMPACT:
            return jsonify({"error": f"Evento '{event_type}' no reconocido"}), 400

        try:
            ObjectId(user_id)
        except:
            return jsonify({"error": "ID de usuario inválido"}), 400

        event = EVENT_IMPACT[event_type]
        calorias = event["calorias"]

        model = train_model()
        compensar = int(round(model.predict([[calorias]])[0])) if model else event["compensar_dias"]

        week_days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        idx = week_days.index(day) if day in week_days else 0

        updated = plan.copy()

        # generar nuevas comidas
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

        # guardar en bd
        if db:
            user_events_col.insert_one({
                "userId": user_id,
                "event": event_type,
                "day": day,
                "adjusted_days": compensar
            })

        return jsonify({
            "message": f"Plan ajustado por evento {event_type}",
            "updatedPlan": updated
        })

    except Exception as e:
        print("❌ ERROR adapt:", e)
        return jsonify({"error": str(e)}), 500


# ============================================
# INICIO APP
# ============================================

if __name__ == "__main__":
    print(f"🚀 IA Flask lista en puerto {PORT}")
    app.run(host="0.0.0.0", port=PORT)
