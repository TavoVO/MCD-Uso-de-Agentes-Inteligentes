# CalificacionesAPI

API REST + servidor MCP para consultar y crear calificaciones en MongoDB Atlas.

## Estructura

```text
CalificacionesAPI/
  api.py
  mcp_server.py
  chat_terminal.py
  common.py
  requirements.txt
  .env
  .env.example
```

## Requisitos

- Python 3.10+
- Acceso a MongoDB Atlas
- Variables de entorno en `.env`

## Instalacion

```bash
cd "Mestría DC/CalificacionesAPI"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecucion

```bash
python api.py
```

API disponible en:

- REST: `http://127.0.0.1:8000/api/calificaciones`
- Health: `http://127.0.0.1:8000/health`

MCP disponible en:

- `http://127.0.0.1:8001/mcp`

Para correr ambos:

```bash
python api.py
python mcp_server.py
```

## Endpoints

### GET /api/calificaciones

Filtros soportados:

- `alumno`
- `materia`
- `periodo`

Ejemplo:

```bash
curl "http://127.0.0.1:8000/api/calificaciones?alumno=Pedro"
```

### POST /api/calificaciones

Ejemplo:

```bash
curl -X POST "http://127.0.0.1:8000/api/calificaciones" \
  -H "Content-Type: application/json" \
  -d '{
    "alumno": "Pedro",
    "materia": "Matematicas",
    "calificacion": 9.5,
    "periodo": "2026-1"
  }'
```

## Pruebas en terminal

### Cliente de terminal con LLM

```bash
python chat_terminal.py
```

Opcionalmente puedes definir:

- `OPENAI_MODEL=gpt-4o-mini`
- `MCP_PORT=8001`
- `MCP_BASE_URL=http://127.0.0.1:8001/mcp`

Este cliente toma tu texto, lo convierte a una accion simple con el LLM y llama al MCP.
Ejemplos:

- `consulta las calificaciones de Pedro`
- `registra 9.5 en Matematicas para Maria`

## Notas

- La API usa la base existente `Calificaciones` para evitar el conflicto de nombres en Atlas.
- El servidor MCP llama internamente a los endpoints REST del mismo proyecto.
- `OPENAI_API_KEY` se carga desde `.env` para usar el chat de terminal con OpenAI.
