from __future__ import annotations

"""Cliente de terminal conectado a Ollama y al servidor MCP.

Este archivo muestra el flujo completo:
1. el usuario escribe una pregunta,
2. Llama 3.1 decide si necesita una tool,
3. el cliente ejecuta la tool en el servidor MCP,
4. la respuesta vuelve al modelo,
5. el modelo redacta la respuesta final en español.
"""

import asyncio
import json
from typing import Any

import httpx
from mcp import Client, types

from common import (
    MCP_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_TOOLS,
    OLLAMA_URL,
    SHOW_TRACE,
)


MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = """
Eres un asistente educativo de una biblioteca local.

Hablas siempre en espanol, con tono claro y breve.

Reglas:
- Usa las tools cuando el usuario quiera listar, agregar, prestar o devolver libros.
- No inventes datos. Si falta un dato importante, pide aclaracion.
- Si el usuario pide algo fuera de la biblioteca, explica que este proyecto solo cubre libros.
- Si hay ambiguedad en un titulo, pide un dato mas preciso.

Objetivo:
- Mostrar de forma didactica como Llama 3.1 usa un servidor MCP.
""".strip()


def trace(message: str) -> None:
    """Imprime mensajes de apoyo para que se vea el flujo del proyecto."""

    if SHOW_TRACE:
        print(message)


def _extract_text_from_content(content: Any) -> str:
    """Convierte el contenido del modelo en texto simple."""

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part).strip()
    return ""


async def request_ollama_chat(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Hace una llamada directa a la API local de Ollama."""

    url = f"{OLLAMA_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "tools": OLLAMA_TOOLS,
        "stream": False,
        "options": {
            "temperature": 0.2,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"No se pudo comunicar con Ollama en {url}: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError("Ollama respondio con un formato no JSON.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Ollama devolvio una estructura inesperada.")

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


def _summarize_tool_result(result: Any, tool_name: str) -> dict[str, Any]:
    """Convierte el resultado MCP en un JSON simple para el modelo."""

    structured = getattr(result, "structured_content", None)
    content_blocks = getattr(result, "content", []) or []
    text_parts: list[str] = []

    for block in content_blocks:
        if isinstance(block, types.TextContent):
            text_parts.append(block.text)
        else:
            text_parts.append(str(block))

    if structured is None and text_parts:
        first_text = text_parts[0].strip()
        if first_text:
            try:
                structured = json.loads(first_text)
            except json.JSONDecodeError:
                structured = None

    return {
        "tool_name": tool_name,
        "is_error": bool(getattr(result, "is_error", False)),
        "structured_content": structured,
        "text": "\n".join(part for part in text_parts if part).strip(),
    }


async def run_tool_call(client: Client, tool_call: dict[str, Any]) -> dict[str, Any]:
    """Ejecuta la tool pedida por el modelo a traves del servidor MCP."""

    function_data = tool_call.get("function", {})
    if not isinstance(function_data, dict):
        return {
            "status": "error",
            "error_type": "invalid_tool_call",
            "message": "La tool solicitada llego con un formato invalido.",
        }

    tool_name = function_data.get("name")
    raw_arguments = function_data.get("arguments", {})

    if not isinstance(tool_name, str) or not tool_name.strip():
        return {
            "status": "error",
            "error_type": "invalid_tool_name",
            "message": "La tool solicitada no tiene un nombre valido.",
        }

    arguments = normalize_tool_arguments(raw_arguments)
    trace(f"[mcp] ejecutando {tool_name} con argumentos: {arguments}")

    try:
        result = await client.call_tool(tool_name, arguments=arguments)
    except Exception as exc:
        return {
            "status": "error",
            "error_type": "mcp_call_failed",
            "message": f"No pude ejecutar la tool '{tool_name}'.",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "result": _summarize_tool_result(result, tool_name),
    }


def extract_final_text(message: dict[str, Any]) -> str:
    """Obtiene el texto final del asistente si ya no pidio herramientas."""

    return _extract_text_from_content(message.get("content", ""))


async def run_agent_turn(client: Client, user_text: str) -> str:
    """Ejecuta un turno completo: usuario -> modelo -> MCP -> modelo."""

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        trace(f"\n[modelo] ronda {round_number}: pensando si necesita una tool...")
        response = await request_ollama_chat(messages)

        assistant_message = response.get("message")
        if not isinstance(assistant_message, dict):
            raise RuntimeError("Ollama no devolvio un mensaje de asistente valido.")

        # Guardamos la respuesta del modelo antes de ejecutar tools.
        messages.append(assistant_message)

        tool_calls = assistant_message.get("tool_calls") or []
        if not tool_calls:
            final_text = extract_final_text(assistant_message)
            if not final_text:
                raise RuntimeError("El modelo respondio sin texto final.")
            return final_text

        if not isinstance(tool_calls, list):
            raise RuntimeError("La lista de tool calls tiene un formato inesperado.")

        trace("[modelo] el asistente pidio una o mas tools MCP.")

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue

            function_data = tool_call.get("function", {})
            function_name = (
                function_data.get("name", "desconocida")
                if isinstance(function_data, dict)
                else "desconocida"
            )

            tool_result = await run_tool_call(client, tool_call)
            trace(f"[mcp] resultado de {function_name}: {tool_result.get('status', 'sin estado')}")

            # El modelo recibe la respuesta de la tool como mensaje de tipo tool.
            messages.append(
                {
                    "role": "tool",
                    "tool_name": function_name,
                    "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                }
            )

    raise RuntimeError("El modelo pidio demasiadas rondas de herramientas.")


def print_intro() -> None:
    """Muestra instrucciones simples al arrancar el cliente."""

    print("Proyecto educativo: MCP con biblioteca y Llama 3.1 local")
    print(f"Servidor MCP: {MCP_BASE_URL}")
    print("Escribe una frase como:")
    print("  lista los libros disponibles")
    print("  presta El principito a Maria")
    print("  agrega un libro llamado El nombre del viento de Patrick Rothfuss")
    print("Escribe 'salir' para terminar.")


async def main() -> None:
    """Punto de entrada principal del cliente de terminal."""

    print_intro()

    try:
        async with Client(MCP_BASE_URL) as client:
            tools = await client.list_tools()
            trace("[mcp] tools disponibles: " + ", ".join(tool.name for tool in tools.tools))

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
                    answer = await run_agent_turn(client, user_text)
                except Exception as exc:
                    print(f"Asistente> No pude completar la consulta: {exc}")
                    continue

                print(f"Asistente> {answer}")
    except Exception as exc:
        print(f"No pude conectar con el MCP en {MCP_BASE_URL}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
