"""Entrada principal del mini proyecto.

Este archivo muestra el flujo completo de function calling en consola:
1. El usuario escribe una pregunta.
2. Llama 3.1 decide si necesita la tool get_weather.
3. Si la necesita, el programa ejecuta la función real.
4. El resultado vuelve al modelo.
5. El modelo redacta la respuesta final en español.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from tool_schema import TOOLS
from weather_tool import get_weather


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Llama 3.1 es el único modelo del proyecto.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:latest")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
SHOW_TRACE = os.getenv("SHOW_TRACE", "1") != "0"
MAX_TOOL_ROUNDS = 4


SYSTEM_PROMPT = """
Eres un asistente educativo de clima.

Tu trabajo es responder en español, de forma breve, clara y natural.

Reglas:
- Si el usuario pregunta por el clima actual de una ciudad, usa la herramienta get_weather.
- No inventes datos del clima.
- Si la herramienta devuelve un error, explícalo con una frase sencilla.
- Si el usuario pide algo fuera de clima, aclara que este mini proyecto solo consulta el clima actual.

Objetivo:
- Mostrar un flujo real de function calling en consola.
""".strip()


def trace(message: str) -> None:
    """Imprime mensajes cortos de aprendizaje para que se vea el flujo."""

    if SHOW_TRACE:
        print(message)


def request_ollama_chat(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Hace una llamada directa a la API local de Ollama."""

    url = f"{OLLAMA_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "options": {
            "temperature": 0.2,
        },
    }

    try:
        response = httpx.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"No se pudo comunicar con Ollama en {url}: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError("Ollama respondió con un formato no JSON.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Ollama devolvió una estructura inesperada.")

    return data


def normalize_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    """Convierte los argumentos de una tool a un diccionario usable."""

    if isinstance(raw_arguments, dict):
        return raw_arguments

    if isinstance(raw_arguments, str):
        text = raw_arguments.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"No pude leer los argumentos de la tool: {text}") from exc
        if isinstance(parsed, dict):
            return parsed
        raise RuntimeError("Los argumentos de la tool no son un objeto JSON.")

    return {}


def run_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    """Ejecuta la tool que pidió el modelo y devuelve un JSON limpio."""

    function_data = tool_call.get("function", {})
    if not isinstance(function_data, dict):
        return {
            "status": "error",
            "error_type": "invalid_tool_call",
            "message": "La tool solicitada llegó con un formato inválido.",
        }

    tool_name = function_data.get("name")
    raw_arguments = function_data.get("arguments", {})

    if tool_name != "get_weather":
        return {
            "status": "error",
            "error_type": "unknown_tool",
            "message": f"La herramienta '{tool_name}' no existe en este proyecto.",
        }

    arguments = normalize_tool_arguments(raw_arguments)
    city = arguments.get("city", "")
    return get_weather(city)


def extract_final_text(message: dict[str, Any]) -> str:
    """Obtiene el texto final del asistente si ya no pidió herramientas."""

    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    return ""


def run_agent_turn(user_text: str) -> str:
    """Ejecuta un turno completo: usuario -> modelo -> tool -> modelo."""

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        trace(f"\n[modelo] ronda {round_number}: pensando si necesita una tool...")
        response = request_ollama_chat(messages)

        assistant_message = response.get("message")
        if not isinstance(assistant_message, dict):
            raise RuntimeError("Ollama no devolvió un mensaje de asistente válido.")

        # Guardamos la respuesta del modelo en el historial antes de ejecutar tools.
        messages.append(assistant_message)

        tool_calls = assistant_message.get("tool_calls") or []
        if not tool_calls:
            final_text = extract_final_text(assistant_message)
            if not final_text:
                raise RuntimeError("El modelo respondió sin texto final.")
            return final_text

        trace("[tool] el modelo pidió usar get_weather.")
        if not isinstance(tool_calls, list):
            raise RuntimeError("La lista de tool calls tiene un formato inesperado.")

        # Si el modelo pide herramientas, ejecutamos cada una y devolvemos su resultado.
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue

            function_data = tool_call.get("function", {})
            function_name = function_data.get("name", "desconocida") if isinstance(function_data, dict) else "desconocida"
            trace(f"[tool] ejecutando {function_name}...")
            result = run_tool_call(tool_call)
            trace(f"[tool] resultado: {result.get('status', 'sin estado')}")

            messages.append(
                {
                    "role": "tool",
                    "tool_name": function_name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    raise RuntimeError("El modelo pidió demasiadas rondas de herramientas.")


def print_intro() -> None:
    """Muestra instrucciones simples para que el proyecto se entienda al abrirlo."""

    print("Mini proyecto educativo: Function Calling con Llama 3.1 y clima")
    print("Escribe una pregunta como:")
    print("  ¿Cómo está el clima en Monterrey?")
    print("Escribe 'salir' para terminar.")


def main() -> None:
    """Punto de entrada de la aplicación de consola."""

    print_intro()

    while True:
        try:
            user_text = input("\nTu> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo.")
            break

        if not user_text:
            continue

        if user_text.lower() in {"salir", "exit", "quit"}:
            print("Saliendo.")
            break

        try:
            answer = run_agent_turn(user_text)
        except Exception as exc:
            print(f"Asistente> No pude completar la consulta: {exc}")
            continue

        print(f"Asistente> {answer}")


if __name__ == "__main__":
    main()
