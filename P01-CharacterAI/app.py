import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, session, redirect, url_for
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if api_key is None:
    raise ValueError("No se encontró OPENAI_API_KEY en el archivo .env")

secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(24)

app = Flask(__name__)
app.secret_key = secret_key

PERSONAS = {
    "goku": {
        "label": "Goku",
        "subtitle": "Guerrero Saiyan",
        "description": "Un héroe apasionado que responde con entusiasmo, honor y metáforas de entrenamiento.",
        "prompt": "Eres Son Goku. Responde con energía, usando metáforas de entrenamiento y amistad para explicar conceptos de forma sencilla.",
        "voice_locale": "ja-JP"
    },
    "messi": {
        "label": "Messi",
        "subtitle": "Mago del fútbol",
        "description": "Un campeón humilde que comparte respuestas precisas, estratégicas y llenas de calma.",
        "prompt": "Eres Lionel Messi. Responde con calma, precisión y ejemplos inspirados en el fútbol y la estrategia.",
        "voice_locale": "es-AR"
    },
    "cr7": {
        "label": "CR7",
        "subtitle": "Competidor imparable",
        "description": "Un atleta motivador que habla de disciplina, rendimiento y mentalidad ganadora.",
        "prompt": "Eres Cristiano Ronaldo. Responde con confianza, enfoque en rendimiento y motivación de alto nivel.",
        "voice_locale": "en-GB"
    },
    "neymar": {
        "label": "Neymar",
        "subtitle": "Artista brasileño",
        "description": "Un creativo del juego que aporta humor, estilo y magia brasileña a cada respuesta.",
        "prompt": "Eres Neymar Jr. Responde con carisma, humor y referencias al fútbol brasileño y la creatividad.",
        "voice_locale": "pt-BR"
    }
}

client = OpenAI(api_key=api_key)

def crear_respuesta(messages):
    response = client.responses.create(
        model="gpt-4o-mini",
        input=messages,
        temperature=0.75,
        max_output_tokens=220,
        top_p=1.0,
    )
    return response.output_text, response

def iniciar_conversacion(persona_key):
    persona = PERSONAS.get(persona_key)
    if persona is None:
        persona_key = "messi"
        persona = PERSONAS[persona_key]

    session["persona_key"] = persona_key
    session["persona_label"] = persona["label"]
    session["persona_subtitle"] = persona["subtitle"]
    session["persona_description"] = persona["description"]
    session["messages"] = [
        {"role": "system", "content": persona["prompt"]}
    ]

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "select_persona":
            persona_key = request.form.get("persona")
            iniciar_conversacion(persona_key)
            return redirect(url_for("index"))

        if action == "send_message":
            if "messages" not in session:
                iniciar_conversacion("messi")

            user_message = request.form.get("user_message", "").strip()
            if user_message:
                messages = session["messages"]
                messages.append({"role": "user", "content": user_message})

                try:
                    assistant_text, response = crear_respuesta(messages)
                except Exception as error:
                    return render_template(
                        "index.html",
                        personas=PERSONAS,
                        error=str(error),
                        persona_label=session.get("persona_label", "Asistente"),
                        persona_subtitle=session.get("persona_subtitle", ""),
                        persona_description=session.get("persona_description", ""),
                        messages=messages,
                        selected_person=session.get("persona_key", "messi"),
                        last_model=session.get("last_model"),
                        last_tokens=session.get("last_tokens"),
                        last_time=session.get("last_time"),
                    )

                messages.append({"role": "assistant", "content": assistant_text})
                session["messages"] = messages
                session["last_model"] = response.model
                session["last_tokens"] = getattr(response.usage, "total_tokens", None)
                session["last_time"] = getattr(response, "response_ms", None)

            return redirect(url_for("index"))

    if "messages" not in session:
        iniciar_conversacion("messi")

    return render_template(
        "index.html",
        personas=PERSONAS,
        persona_label=session.get("persona_label", "Asistente"),
        persona_subtitle=session.get("persona_subtitle", ""),
        persona_description=session.get("persona_description", ""),
        messages=session.get("messages", []),
        selected_person=session.get("persona_key", "messi"),
        last_model=session.get("last_model"),
        last_tokens=session.get("last_tokens"),
        last_time=session.get("last_time"),
    )

@app.route("/reset", methods=["POST"])
def reset():
    persona_key = session.get("persona_key", "messi")
    iniciar_conversacion(persona_key)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
