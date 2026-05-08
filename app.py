import requests
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

from models import ChatMessage, User, db


N8N_WEBHOOK_URL = "http://localhost:5678/webhook/forgefit"
AGENTS = {
    "0": "Macro Analyzer",
    "1": "Workout Architect",
    "2": "Recipe Recommender",
    "3": "Daily Accountability Coach",
    "4": "Weekly Success Manager",
}
AGENT_REQUEST_TYPE = {
    "0": "macro_calc",
    "1": "workout_plan",
    "2": "recipe_recommend",
    "3": "daily_accountability",
    "4": "weekly_review",
}

app = Flask(__name__)
app.config["SECRET_KEY"] = "forgefit-dev-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///forgefit.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if len(username) < 3:
            flash("Username must be at least 3 characters.", "danger")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("register.html")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")
        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
            return render_template("register.html")

        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Account created successfully. Complete onboarding to personalize your plan.", "success")
        return redirect(url_for("onboarding"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Welcome back.", "success")
            if user.has_onboarded:
                return redirect(url_for("dashboard"))
            return redirect(url_for("onboarding"))

        flash("Invalid credentials.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    if request.method == "POST":
        try:
            current_user.age = int(request.form.get("age", "0"))
            current_user.height_cm = float(request.form.get("height_cm", "0"))
            current_user.weight_kg = float(request.form.get("weight_kg", "0"))
        except ValueError:
            flash("Please enter valid numbers for age, height, and weight.", "danger")
            return render_template("onboarding.html")

        current_user.gender = (request.form.get("gender") or "").strip()
        current_user.activity_level = (request.form.get("activity_level") or "").strip()

        if (
            current_user.age <= 0
            or current_user.height_cm <= 0
            or current_user.weight_kg <= 0
            or not current_user.gender
            or not current_user.activity_level
        ):
            flash("Please complete all onboarding fields correctly.", "danger")
            return render_template("onboarding.html")

        db.session.commit()
        flash("Profile saved. Your ForgeFit dashboard is ready.", "success")
        return redirect(url_for("dashboard"))

    return render_template("onboarding.html")


@app.route("/dashboard")
@login_required
def dashboard():
    if not current_user.has_onboarded:
        return redirect(url_for("onboarding"))
    recent_messages = (
        ChatMessage.query.filter_by(user_id=current_user.id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(8)
        .all()
    )
    return render_template("dashboard.html", agents=AGENTS, recent_messages=recent_messages)


@app.route("/chat")
@login_required
def chat():
    if not current_user.has_onboarded:
        return redirect(url_for("onboarding"))
    recent_messages = (
        ChatMessage.query.filter_by(user_id=current_user.id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(12)
        .all()
    )
    return render_template("chat.html", agents=AGENTS, recent_messages=recent_messages)


@app.route("/api/chat/history", methods=["GET"])
@login_required
def chat_history():
    agent_id = request.args.get("agent_id", "0")
    if agent_id not in AGENTS:
        return jsonify({"error": "Invalid agent id."}), 400

    messages = (
        ChatMessage.query.filter_by(user_id=current_user.id, agent_id=agent_id)
        .order_by(ChatMessage.timestamp.asc())
        .limit(50)
        .all()
    )

    return jsonify(
        {
            "messages": [
                {
                    "id": message.id,
                    "user_message": message.user_message,
                    "ai_response": message.ai_response,
                    "timestamp": message.timestamp.isoformat(),
                }
                for message in messages
            ]
        }
    )


@app.route("/api/chat/history/reset", methods=["POST"])
@login_required
def reset_chat_history():
    data = request.get_json(silent=True) or {}
    agent_id = str(data.get("agent_id", "")).strip()
    if agent_id not in AGENTS:
        return jsonify({"error": "Invalid agent id."}), 400

    ChatMessage.query.filter_by(user_id=current_user.id, agent_id=agent_id).delete()
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/chat/history/<int:message_id>", methods=["DELETE"])
@login_required
def delete_chat_message(message_id):
    message = ChatMessage.query.filter_by(id=message_id, user_id=current_user.id).first()
    if message is None:
        return jsonify({"error": "Message not found."}), 404

    db.session.delete(message)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    if not current_user.has_onboarded:
        return jsonify({"error": "Please complete onboarding first."}), 400

    data = request.get_json(silent=True) or {}
    agent_id = str(data.get("agent_id", "")).strip()
    user_message = (data.get("message") or "").strip()

    if agent_id not in AGENTS:
        return jsonify({"error": "Invalid agent selection."}), 400
    if not user_message:
        return jsonify({"error": "Message is required."}), 400

    recent_context = (
        ChatMessage.query.filter_by(user_id=current_user.id, agent_id=agent_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(6)
        .all()
    )
    recent_context.reverse()

    # Gemini requires role "model" (not "assistant") and a "parts" array.
    chat_history_gemini = []
    for item in recent_context:
        chat_history_gemini.append({"role": "user", "parts": [{"text": item.user_message}]})
        chat_history_gemini.append({"role": "model", "parts": [{"text": item.ai_response}]})

    # Build a rich system prompt so every agent has full user context.
    system_prompt = (
        f"You are ForgeFit's {AGENTS[agent_id]}, a specialized fitness AI assistant.\n"
        f"Always respond in the context of this agent's role and the user's profile below.\n\n"
        f"USER PROFILE:\n"
        f"- Name: {current_user.username}\n"
        f"- Age: {current_user.age} years\n"
        f"- Gender: {current_user.gender}\n"
        f"- Height: {current_user.height_cm} cm\n"
        f"- Weight: {current_user.weight_kg} kg\n"
        f"- Activity Level: {current_user.activity_level}\n\n"
        f"Use this profile to personalise every response. "
        f"If the conversation history is present, maintain continuity with it."
    )

    payload = {
        "type": agent_id,
        "request_type": AGENT_REQUEST_TYPE[agent_id],
        "agent_name": AGENTS[agent_id],
        "user_prompt": user_message,
        "system_prompt": system_prompt,
        "weight": str(current_user.weight_kg),
        "age": str(current_user.age),
        "height": str(current_user.height_cm),
        "gender": current_user.gender,
        "activity_level": current_user.activity_level,
        "username": current_user.username,
        "chat_history": chat_history_gemini,
    }

    try:
        n8n_response = requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        n8n_response.raise_for_status()
        ai_text = n8n_response.text
    except requests.RequestException as exc:
        return jsonify({"error": f"Webhook request failed: {exc}"}), 502

    message = ChatMessage(
        user_id=current_user.id,
        agent_id=agent_id,
        user_message=user_message,
        ai_response=ai_text,
    )
    db.session.add(message)
    db.session.commit()

    return jsonify({"response": ai_text})


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)