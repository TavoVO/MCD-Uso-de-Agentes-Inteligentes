"""
Definición de la tool que Llama 3.1 puede pedir en consola.

Este archivo está separado a propósito para que el esquema de la herramienta
sea fácil de leer y de explicar en clase.
"""

GET_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Consulta el clima actual de una ciudad usando geocoding y Open-Meteo. "
            "Úsala cuando el usuario pregunte por el clima, temperatura o condiciones actuales."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Nombre de la ciudad sobre la que quieres consultar el clima actual.",
                }
            },
            "required": ["city"],
            "additionalProperties": False,
        },
    },
}

# Lista de tools que se envía a Ollama.
TOOLS = [GET_WEATHER_TOOL]
