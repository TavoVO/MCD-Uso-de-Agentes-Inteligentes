# MCP de Clima Simple

Este ejemplo muestra el flujo mas claro posible:

1. el usuario pregunta por el clima,
2. Ollama 3.1 decide si usar la tool,
3. el cliente llama al MCP,
4. el MCP consulta Open-Meteo,
5. la respuesta vuelve a Ollama y se redacta en español.

## Que incluye

- `mcp_simple.py`: servidor MCP que envuelve la API real del clima.
- `chat_terminal.py`: cliente de terminal que habla con Ollama y con el MCP.

## Requisitos

- Python 3.10+
- Ollama instalado y corriendo
- modelo `llama3.1` descargado

## Instalacion

```bash
cd "Mestría DC/UsoDeAgentesInteligentes/mcp-simple"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama pull llama3.1
```

## Como correrlo

Abre dos terminales.

### Terminal 1

```bash
source .venv/bin/activate
python mcp_simple.py
```

El MCP queda en:

```text
http://127.0.0.1:8001/mcp
```

### Terminal 2

```bash
source .venv/bin/activate
python chat_terminal.py
```

## Que puedes preguntar

- `¿Cómo está el clima en Monterrey?`
- `¿Qué clima hay en Guadalajara?`
- `¿Está lloviendo en CDMX?`

## Idea importante

El MCP no le habla directo al usuario.

El usuario habla con Ollama, Ollama decide si necesita la tool, la tool consulta Open-Meteo y luego Ollama escribe la respuesta final.
