from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Credenciales y ruta del MCP para el chat de terminal.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", f"http://127.0.0.1:{os.getenv('MCP_PORT', '8001')}/mcp")

if not OPENAI_API_KEY:
    raise ValueError("No se encontro OPENAI_API_KEY en .env")


client = OpenAI(api_key=OPENAI_API_KEY)

# Instruccion simple: convertir texto libre en una intencion estructurada.
SYSTEM_PROMPT = (
    "Convierte el mensaje del usuario en JSON valido y sin texto adicional. "
    "Usa exactamente estas claves: action, alumno, materia, calificacion, fecha, periodo. "
    "action debe ser uno de: consultar, registrar, salir, ayuda. "
    "Si falta un dato, usa null. "
    "No inventes valores."
)


@dataclass
class Intent:
    action: str
    alumno: Optional[str] = None
    materia: Optional[str] = None
    calificacion: Optional[float] = None
    fecha: Optional[str] = None
    periodo: Optional[str] = None


def parse_intent(raw_text: str) -> Intent:
    """Convierte el JSON del modelo en una estructura facil de usar."""
    # Convierte el JSON del modelo en una estructura facil de usar.
    payload = json.loads(raw_text)
    return Intent(
        action=str(payload.get("action", "")).strip().lower(),
        alumno=payload.get("alumno"),
        materia=payload.get("materia"),
        calificacion=payload.get("calificacion"),
        fecha=payload.get("fecha"),
        periodo=payload.get("periodo"),
    )


def interpret_message(user_text: str) -> Intent:
    """Pide al LLM que traduzca el texto del usuario a una intencion simple."""
    # El LLM solo clasifica la intencion; el script decide qué herramienta ejecutar.
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        temperature=0,
    )
    raw_text = response.output_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json", "", 1).strip()
    return parse_intent(raw_text)


def extract_tool_payload(tool_result: Any) -> Dict[str, Any]:
    """Normaliza la respuesta MCP para convertirla en un diccionario."""
    # Normaliza la respuesta MCP para poder imprimirla en terminal.
    if hasattr(tool_result, "structuredContent") and tool_result.structuredContent:
        return dict(tool_result.structuredContent)

    content = getattr(tool_result, "content", None)
    if content:
        text_parts = []
        for part in content:
            text = getattr(part, "text", None)
            if text:
                text_parts.append(text)
        if text_parts:
            try:
                return json.loads("".join(text_parts))
            except json.JSONDecodeError:
                return {"status": "error", "message": "".join(text_parts)}

    if isinstance(tool_result, dict):
        return tool_result

    return {"status": "error", "message": "Respuesta MCP no reconocida"}


def format_query_result(payload: Dict[str, Any]) -> str:
    """Formatea la salida de consulta para que se lea bien en consola."""
    # Formatea una respuesta de consulta en texto legible.
    if payload.get("status") != "ok":
        return payload.get("message", "No se pudo consultar la informacion.")

    items = payload.get("items", [])
    if not items:
        filters = payload.get("filters", {})
        alumno = filters.get("alumno") or "sin filtro"
        return f"No se encontraron calificaciones para {alumno}."

    lines = []
    first_filter = payload.get("filters", {}).get("alumno")
    if first_filter:
        lines.append(f"Calificaciones de {first_filter}:")
    else:
        lines.append("Calificaciones encontradas:")

    for item in items:
        alumno = item.get("alumno", "N/A")
        materia = item.get("materia", "N/A")
        calificacion = item.get("calificacion", "N/A")
        fecha = item.get("fecha", "N/A")
        periodo = item.get("periodo", "N/A")
        lines.append(f"- {alumno} | {materia} | {calificacion} | {fecha} | {periodo}")

    return "\n".join(lines)


def format_create_result(payload: Dict[str, Any]) -> str:
    """Formatea la confirmacion de una insercion."""
    # Formatea la confirmacion de guardado.
    if payload.get("status") != "ok":
        return payload.get("message", "No se pudo registrar la calificacion.")

    item = payload.get("item", {})
    alumno = item.get("alumno", "N/A")
    materia = item.get("materia", "N/A")
    calificacion = item.get("calificacion", "N/A")
    return f"Calificacion registrada: {alumno} - {materia} - {calificacion}"


async def call_mcp_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Abre una sesion MCP y ejecuta un tool con argumentos JSON."""
    # Abre una sesion MCP, llama el tool y devuelve JSON puro.
    async with streamable_http_client(MCP_BASE_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments=arguments)
            return extract_tool_payload(result)


async def run_chat() -> None:
    """Ejecuta el bucle interactivo del chat en terminal."""
    # Bucle interactivo principal del chat en terminal.
    print("CalificacionesAPI en terminal")
    print("Escribe algo como:")
    print("- consulta las calificaciones de Pedro")
    print("- registra 9.5 en Matematicas para Maria")
    print("Escribe 'salir' para terminar.")

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
            intent = interpret_message(user_text)
        except Exception as exc:
            print(f"Asistente> No pude interpretar el mensaje: {exc}")
            continue

        if intent.action == "salir":
            print("Asistente> Hasta luego.")
            break

        if intent.action == "ayuda":
            print("Asistente> Puedo consultar o registrar calificaciones. Ejemplo: consulta las calificaciones de Pedro")
            continue

        if intent.action == "consultar":
            # Solo enviamos al MCP los filtros que el usuario sí proporciono.
            arguments = {k: v for k, v in {
                "alumno": intent.alumno,
                "materia": intent.materia,
                "periodo": intent.periodo,
            }.items() if v not in (None, "")}
            try:
                payload = await call_mcp_tool("consultar_calificaciones", arguments)
                print(f"Asistente> {format_query_result(payload)}")
            except Exception as exc:
                print(f"Asistente> No fue posible consultar las calificaciones: {exc}")
            continue

        if intent.action == "registrar":
            required = {
                "alumno": intent.alumno,
                "materia": intent.materia,
                "calificacion": intent.calificacion,
            }
            missing = [key for key, value in required.items() if value in (None, "")]
            if missing:
                # Si faltan datos, no llamamos al MCP.
                print(f"Asistente> Faltan datos para registrar la calificacion: {', '.join(missing)}")
                continue

            arguments = {
                "alumno": intent.alumno,
                "materia": intent.materia,
                "calificacion": intent.calificacion,
            }
            if intent.fecha:
                arguments["fecha"] = intent.fecha
            if intent.periodo:
                arguments["periodo"] = intent.periodo

            try:
                payload = await call_mcp_tool("asignar_calificacion", arguments)
                print(f"Asistente> {format_create_result(payload)}")
            except Exception as exc:
                print(f"Asistente> No fue posible registrar la calificacion: {exc}")
            continue

        print("Asistente> No entendí la instruccion. Escribe ayuda, consulta o registra.")


def main() -> None:
    """Punto de entrada del chat de terminal."""
    # Ejecuta el chat desde terminal.
    asyncio.run(run_chat())


if __name__ == "__main__":
    main()
