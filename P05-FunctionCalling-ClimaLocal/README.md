# Function Calling con Llama 3.1 y clima

Mini proyecto educativo en consola para aprender el ciclo completo de una tool:

1. el usuario pregunta por el clima,
2. Llama 3.1 decide si llama `get_weather`,
3. tu código ejecuta la función real,
4. el resultado vuelve al modelo,
5. el modelo redacta la respuesta final en español.

## Por qué esta versión es la más simple

- Usa `Llama 3.1` local en Ollama como único modelo.
- No hay frontend ni web.
- Usa Open-Meteo porque es gratis y no requiere API key.
- El código está separado en solo tres piezas claras: consola, tool y esquema.

## Estructura

```text
function-calling-clima-local/
  main.py
  weather_tool.py
  tool_schema.py
  requirements.txt
  .env.example
  README.md
```

## Requisitos

- Python 3.9+
- Ollama instalado y ejecutándose
- Modelo `llama3.1:latest` descargado en Ollama

## Instalación

```bash
cd "Mestría DC/UsoDeAgentesInteligentes/function-calling-clima-local"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Si quieres guardar configuración local, copia el archivo de ejemplo:

```bash
cp .env.example .env
```

## Ejecución

```bash
python3 main.py
```

Ejemplo:

```text
Tu> ¿Cómo está el clima en Monterrey?
Asistente> En Monterrey, Nuevo León, México está cielo despejado. Temperatura 27.5°C.
```

## Cómo funciona el tool calling aquí

- `tool_schema.py` define `get_weather` con JSON Schema.
- `main.py` manda tu pregunta a Ollama junto con la lista de tools.
- Llama 3.1 decide si necesita `get_weather`.
- Si la necesita, Ollama devuelve un `tool_call` con argumentos como `city`.
- `main.py` llama `weather_tool.get_weather(city)`.
- La herramienta consulta primero geocoding y luego el clima actual en Open-Meteo.
- El resultado se manda de vuelta a Ollama como mensaje de tipo `tool`.
- El mismo modelo redacta la respuesta final en español.

## Decisión técnica

Se eligió Open-Meteo porque ofrece geocoding y clima gratis, sin API key, y eso mantiene el proyecto corto y fácil de aprender.

Se eligió llamar a la API local de Ollama directamente con HTTP porque evita dependencias innecesarias y deja el flujo muy visible.

## Errores básicos cubiertos

- ciudad no encontrada,
- falla de red o API,
- formato JSON inesperado,
- Ollama no disponible,
- argumentos inválidos de la tool.

## Nota

Si cambias el nombre del modelo en `.env`, asegúrate de usar uno que soporte tools en Ollama. En este proyecto se deja `llama3.1:latest` como valor por defecto.
