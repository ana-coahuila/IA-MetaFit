from flask import Flask, request, jsonify
from flask_cors import CORS
import random
import numpy as np
from sklearn.linear_model import LinearRegression
import urllib.request
import json

app = Flask(__name__)
CORS(app)

# URL de tu API Node.js
NODE_API_URL = "http://localhost:5000/api"

# Impacto de eventos
EVENT_IMPACT = {
    "fiesta": {"calorias": 600, "compensar_dias": 3, "tipo": "exceso"},
    "viaje": {"calorias": 400, "compensar_dias": 2, "tipo": "exceso"},
    "enfermedad": {"calorias": -300, "compensar_dias": 2, "tipo": "deficit"},
    "estres": {"calorias": 200, "compensar_dias": 1, "tipo": "exceso_leve"},
    "dia_libre": {"calorias": 300, "compensar_dias": 2, "tipo": "exceso"},
}

# Almacenamiento en memoria
user_events_storage = {}

def train_model(user_id=None):
    events = []
    
    if user_id and user_id in user_events_storage:
        events = user_events_storage[user_id]
    else:
        for user_events in user_events_storage.values():
            events.extend(user_events)
    
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

def get_plans_from_db(bmi_category):
    """Obtener planes de la base de datos según la categoría BMI"""
    try:
        url = f"{NODE_API_URL}/plans/sample?bmiCategory={bmi_category}"
        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req)
        data = response.read().decode('utf-8')
        return json.loads(data)
    except Exception as e:
        print(f"Error obteniendo planes: {e}")
        return []

def get_meal_by_type(plans, meal_type):
    """Obtener una comida aleatoria del tipo específico"""
    if not plans:
        return None
    
    available_meals = []
    for plan in plans:
        if 'meals' in plan and meal_type in plan['meals']:
            available_meals.append(plan['meals'][meal_type])
    
    if available_meals:
        return random.choice(available_meals)
    return None

@app.route('/adapt', methods=['POST'])
def adapt_plan():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No se recibieron datos JSON"}), 400

        user_id = data.get("userId")
        event_type = data.get("eventType", "").lower()
        day = data.get("day", "").lower()
        plan_data = data.get("plan")

        if not user_id:
            return jsonify({"error": "Falta userId"}), 400
        if not plan_data:
            return jsonify({"error": "Falta plan"}), 400

        # Obtener información del usuario
        bmi_category = 'Normal'
        try:
            user_url = f"{NODE_API_URL}/users/{user_id}"
            user_req = urllib.request.Request(user_url)
            user_response = urllib.request.urlopen(user_req)
            user_data = json.loads(user_response.read().decode('utf-8'))
            bmi_category = user_data.get('bmiCategory', 'Normal')
        except:
            bmi_category = 'Normal'

        # Normalizar evento
        event_type = event_type.replace('é', 'e').replace('í', 'i').replace('á', 'a').replace('ó', 'o').replace('ú', 'u')
        
        if event_type not in EVENT_IMPACT:
            return jsonify({"error": f"Evento '{event_type}' no válido"}), 400

        event = EVENT_IMPACT[event_type]
        tipo = event["tipo"]
        calorias_evento = event["calorias"]

        # Predecir días a compensar
        model = train_model(user_id)
        compensar_dias = int(round(model.predict([[calorias_evento]])[0])) if model else event["compensar_dias"]

        week_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        
        # Encontrar índice del día
        event_index = week_days.index(day) if day in week_days else 0

        # Obtener planes de la base de datos
        plans = get_plans_from_db(bmi_category)
        
        # Actualizar plan - CORREGIDO: mantener los _id originales
        updated_plan = plan_data.copy()
        
        for i in range(1, compensar_dias + 1):
            idx = (event_index + i) % len(week_days)
            day_to_adjust = week_days[idx]

            if day_to_adjust in updated_plan:
                # Obtener nuevas comidas de la base de datos
                new_breakfast = get_meal_by_type(plans, "breakfast")
                new_lunch = get_meal_by_type(plans, "lunch")
                new_dinner = get_meal_by_type(plans, "dinner")
                
                # Si se encontraron comidas, actualizar el día MANTENIENDO LOS _ID ORIGINALES
                if new_breakfast and new_lunch and new_dinner:
                    # Mantener los _id originales del plan existente
                    original_meals = updated_plan[day_to_adjust]
                    
                    updated_plan[day_to_adjust] = [
                        {
                            "name": new_breakfast.get("name", "Desayuno"),
                            "calories": new_breakfast.get("calories", 0),
                            "category": new_breakfast.get("category", "Normal"),
                            "_id": original_meals[0]["_id"]  # ← MANTENER _ID ORIGINAL
                        },
                        {
                            "name": new_lunch.get("name", "Almuerzo"),
                            "calories": new_lunch.get("calories", 0),
                            "category": new_lunch.get("category", "Normal"),
                            "_id": original_meals[1]["_id"]  # ← MANTENER _ID ORIGINAL
                        },
                        {
                            "name": new_dinner.get("name", "Cena"),
                            "calories": new_dinner.get("calories", 0),
                            "category": new_dinner.get("category", "Normal"),
                            "_id": original_meals[2]["_id"]  # ← MANTENER _ID ORIGINAL
                        }
                    ]

        # Guardar evento
        if user_id not in user_events_storage:
            user_events_storage[user_id] = []
        
        user_events_storage[user_id].append({
            "userId": user_id,
            "event": event_type,
            "day": day,
            "adjusted_days": compensar_dias
        })

        return jsonify({
            "message": f"Plan ajustado por '{event_type}' ({compensar_dias} días)",
            "updatedPlan": updated_plan
        })

    except Exception as e:
        print(f"Error interno: {e}")
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

# Los demás endpoints permanecen igual...
@app.route('/events', methods=['GET'])
def get_events():
    user_id = request.args.get('userId')
    if not user_id:
        return jsonify({"error": "Falta userId"}), 400
    
    events = user_events_storage.get(user_id, [])
    return jsonify(events)

@app.route('/admin/reset_rules', methods=['POST'])
def reset_rules():
    data = request.get_json()
    user_id = data.get("userId") if data else None
    
    if user_id:
        if user_id in user_events_storage:
            user_events_storage[user_id] = []
            return jsonify({"message": f"Reglas reseteadas para usuario {user_id}"})
        else:
            return jsonify({"error": f"No hay eventos para {user_id}"}), 404
    else:
        user_events_storage.clear()
        return jsonify({"message": "Todas las reglas reseteadas"})

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "OK", "message": "IA Flask API funcionando"})

if __name__ == '__main__':
    print("✅ IA Flask API iniciada")
    print("📋 Usando planes de la base de datos")
    print("🚀 Servidor en http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000, debug=True)