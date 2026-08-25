from __future__ import annotations

# Importamos json para manejar argumentos y respuestas.
import json
# Importamos os para leer variables de entorno simples.
import os
# Importamos asyncio para correr el chat async.
import asyncio
# Importamos Any para tipos flexibles.
from typing import Any

# Importamos httpx para hablar con la API local de Ollama.
import httpx

# Importamos el cliente MCP.
from mcp import ClientSession
# Importamos el transporte HTTP del MCP.
from mcp.client.streamable_http import streamable_http_client

# URL local de Ollama.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")

# Modelo local que usaremos para el chat.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# URL del servidor MCP.
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://127.0.0.1:8001/mcp")

# Número máximo de rondas tool calling.
MAX_TOOL_ROUNDS = 3

# Instrucciones del asistente.
SYSTEM_PROMPT = (
    "Eres un asistente de clima. "
    "Si el usuario pregunta por el clima actual de una ciudad, usa la tool consultar_clima. "
    "Responde en español, breve y claro. "
    "No inventes datos."
)

# Tool schema que verá Ollama.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_clima",
            "description": "Consulta el clima actual de una ciudad usando el servidor MCP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ciudad": {
                        "type": "string",
                        "description": "Nombre de la ciudad a consultar.",
                    }
                },
                "required": ["ciudad"],
                "additionalProperties": False,
            },
        },
    }
]


# Convierte argumentos de la tool a diccionario.
def normalizar_argumentos(raw_arguments: Any) -> dict[str, Any]:
    # Si ya es un diccionario, lo regresamos tal cual.
    if isinstance(raw_arguments, dict):
        return raw_arguments

    # Si viene como texto, intentamos leerlo como JSON.
    if isinstance(raw_arguments, str):
        text = raw_arguments.strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise RuntimeError("Los argumentos de la tool no son un objeto JSON.")

    # Para cualquier otro caso devolvemos vacío.
    return {}


# Llamada directa a Ollama.
def pedir_ollama(messages: list[dict[str, Any]]) -> dict[str, Any]:
    # Armamos la petición al endpoint /api/chat.
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "tools": TOOLS,
            "stream": False,
            "options": {"temperature": 0.2},
        },
        timeout=60.0,
    )
    # Si falla la conexión, dejamos que explote con un mensaje claro.
    response.raise_for_status()
    # Convertimos la respuesta a JSON.
    data = response.json()
    # Aseguramos que sea un objeto.
    if not isinstance(data, dict):
        raise RuntimeError("Ollama devolvió una respuesta inesperada.")
    # Regresamos el JSON validado.
    return data


# Extrae texto plano de la respuesta del MCP.
def extraer_texto_mcp(result: Any) -> dict[str, Any]:
    # Si el MCP ya devolvió contenido estructurado, lo usamos.
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured

    # Si no, intentamos convertir el contenido a texto.
    content = getattr(result, "content", []) or []
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
        else:
            parts.append(str(block))

    # Si el texto parece JSON, lo parseamos.
    raw_text = "\n".join(parts).strip()
    if raw_text:
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Como último recurso devolvemos el texto.
    return {"text": raw_text}


# Ejecuta la tool consultando al MCP.
async def llamar_tool_mcp(nombre: str, argumentos: dict[str, Any]) -> dict[str, Any]:
    # Abrimos la sesión MCP por HTTP.
    async with streamable_http_client(MCP_BASE_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            # Inicializamos la sesión.
            await session.initialize()
            # Ejecutamos la tool real en el servidor MCP.
            result = await session.call_tool(nombre, arguments=argumentos)
            # Convertimos el resultado a JSON simple.
            return extraer_texto_mcp(result)


# Hace una vuelta completa del chat.
async def correr_turno(user_text: str) -> str:
    # Historial con sistema y mensaje del usuario.
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    # Permitimos varias rondas por si el modelo necesita más de una tool.
    for _ in range(MAX_TOOL_ROUNDS):
        # Pedimos una respuesta a Ollama.
        response = pedir_ollama(messages)
        # Leemos el mensaje del asistente.
        assistant_message = response.get("message")
        # Si no viene un diccionario, algo salió mal.
        if not isinstance(assistant_message, dict):
            raise RuntimeError("Ollama no devolvió un mensaje válido.")

        # Guardamos la respuesta del asistente en el historial.
        messages.append(assistant_message)

        # Leemos si pidió tools.
        tool_calls = assistant_message.get("tool_calls") or []
        # Si no pidió tools, devolvemos el texto final.
        if not tool_calls:
            return str(assistant_message.get("content", "")).strip()

        # Recorremos cada tool call.
        for tool_call in tool_calls:
            # Ignoramos entradas raras.
            if not isinstance(tool_call, dict):
                continue

            # Leemos la función solicitada.
            function_data = tool_call.get("function", {})
            if not isinstance(function_data, dict):
                continue

            # Tomamos el nombre de la tool.
            tool_name = str(function_data.get("name", "")).strip()
            # Convertimos los argumentos al formato correcto.
            arguments = normalizar_argumentos(function_data.get("arguments", {}))
            # Ejecutamos la tool en el MCP.
            result = await llamar_tool_mcp(tool_name, arguments)

            # Mandamos el resultado de vuelta a Ollama.
            messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    # Si llegamos aquí, el modelo pidió demasiadas rondas.
    raise RuntimeError("Ollama pidió demasiadas rondas de herramientas.")


# Texto de entrada del programa.
def print_intro() -> None:
    # Indicaciones simples para el usuario.
    print("MCP de clima con Ollama 3.1")
    print("Prueba con:")
    print("  ¿Cómo está el clima en Monterrey?")
    print("  ¿Qué clima hay en Guadalajara?")
    print("Escribe 'salir' para terminar.")


# Punto de entrada async.
async def main() -> None:
    # Mostramos instrucciones.
    print_intro()

    # Bucle interactivo.
    while True:
        # Leemos lo que escribe el usuario.
        try:
            user_text = input("\nTu> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo.")
            break

        # Saltamos líneas vacías.
        if not user_text:
            continue

        # Comando para salir.
        if user_text.lower() in {"salir", "exit", "quit"}:
            print("Saliendo.")
            break

        # Ejecutamos el flujo completo.
        try:
            answer = await correr_turno(user_text)
        except Exception as exc:
            print(f"Asistente> No pude completar la consulta: {exc}")
            continue

        # Mostramos la respuesta final.
        print(f"Asistente> {answer}")


# Ejecutamos el programa.
if __name__ == "__main__":
    asyncio.run(main())
