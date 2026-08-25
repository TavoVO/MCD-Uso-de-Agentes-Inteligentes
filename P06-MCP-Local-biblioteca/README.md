# Biblioteca MCP con Llama 3.1 Local

Este proyecto es una demo educativa para entender el flujo completo de MCP de forma simple:

`usuario -> Llama 3.1 -> MCP -> API REST -> JSON local -> respuesta`

La idea es aprender sin ruido extra:

- no hay frontend,
- no hay base de datos remota,
- no hay servicios externos,
- todo corre en local,
- y el codigo trae comentarios para que se entienda paso por paso.

## Que ejemplo usa

Usamos una **biblioteca de libros** porque es facil de visualizar:

- listar libros,
- agregar un libro,
- prestar un libro,
- devolver un libro.

Eso permite ver muy bien como un LLM local decide cuando usar tools.

## Estructura

```text
biblioteca-mcp-llama-local/
  api.py
  mcp_server.py
  chat_terminal.py
  common.py
  requirements.txt
  .env.example
  data/
    libros.json
```

## Requisitos

- Python 3.10+
- Ollama instalado y ejecutandose
- Modelo `llama3.1` descargado en Ollama

## Instalacion

```bash
cd "Mestría DC/UsoDeAgentesInteligentes/biblioteca-mcp-llama-local"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Si ya tienes Ollama funcionando, confirma que el modelo exista:

```bash
ollama pull llama3.1
```

## Como correrlo

Abre tres terminales.

### Opcion simple: arrancar todo con un solo comando

```bash
bash run_all.sh
```

Este script:

- inicia la API REST,
- inicia el servidor MCP,
- y abre el chat de terminal con `llama3.1`.

Cuando cierres el chat, el script intenta apagar los procesos de fondo.

### Terminal 1: API REST

```bash
source .venv/bin/activate
python3 api.py
```

### Terminal 2: Servidor MCP

```bash
source .venv/bin/activate
python3 mcp_server.py
```

### Terminal 3: Cliente con Llama 3.1

```bash
source .venv/bin/activate
python3 chat_terminal.py
```

## Endpoints

### API REST

- `GET /health`
- `GET /api/libros`
- `POST /api/libros`
- `POST /api/libros/prestar`
- `POST /api/libros/devolver`

### MCP

- base: `http://127.0.0.1:8001/mcp`
- tools:
  - `listar_libros`
  - `agregar_libro`
  - `prestar_libro`
  - `devolver_libro`

## Ejemplos con curl

### Ver salud

```bash
curl http://127.0.0.1:8000/health
```

### Listar libros

```bash
curl http://127.0.0.1:8000/api/libros
```

### Filtrar por autor

```bash
curl "http://127.0.0.1:8000/api/libros?autor=Garcia"
```

### Agregar libro

```bash
curl -X POST http://127.0.0.1:8000/api/libros \
  -H "Content-Type: application/json" \
  -d '{
    "titulo": "El nombre del viento",
    "autor": "Patrick Rothfuss",
    "anio_publicacion": 2007,
    "genero": "fantasia",
    "sinopsis": "La historia de Kvothe y su paso por la universidad."
  }'
```

### Prestar libro

```bash
curl -X POST http://127.0.0.1:8000/api/libros/prestar \
  -H "Content-Type: application/json" \
  -d '{
    "titulo": "El principito",
    "prestado_a": "Ana"
  }'
```

### Devolver libro

```bash
curl -X POST http://127.0.0.1:8000/api/libros/devolver \
  -H "Content-Type: application/json" \
  -d '{
    "titulo": "El principito"
  }'
```

## Como funciona el flujo

1. El usuario escribe algo en la terminal.
2. `chat_terminal.py` manda el texto a `llama3.1` usando la API local de Ollama.
3. El modelo decide si necesita una tool.
4. Si necesita una tool, el cliente abre una sesion MCP contra `mcp_server.py`.
5. El servidor MCP llama a la API REST.
6. La API REST lee y modifica el JSON local.
7. El resultado vuelve al modelo.
8. El modelo redacta la respuesta final en espanol.

## Lectura guiada del codigo

### `common.py`

Este es el archivo mas importante para leer primero.

- define las rutas y variables de entorno,
- crea los modelos Pydantic,
- carga y guarda el archivo `data/libros.json`,
- implementa la logica de biblioteca,
- define las tools que el cliente le pasa a Ollama.

Las funciones claves son:

- `load_library_state()`
- `save_library_state()`
- `list_books()`
- `add_book()`
- `loan_book()`
- `return_book()`

### `api.py`

Este archivo expone HTTP y casi no tiene logica propia.

- `GET /health` comprueba que el archivo JSON exista y se pueda leer.
- `GET /api/libros` lista libros.
- `POST /api/libros` agrega un libro.
- `POST /api/libros/prestar` presta un libro.
- `POST /api/libros/devolver` devuelve un libro.

### `mcp_server.py`

Este archivo crea el servidor MCP.

- cada tool MCP llama a la API REST,
- la API es quien toca el JSON,
- asi se ve claramente la separacion entre MCP y REST.

### `chat_terminal.py`

Este archivo conecta tres piezas:

- terminal,
- Ollama local,
- servidor MCP.

Cuando el modelo pide una tool, el cliente:

- detecta el nombre de la tool,
- normaliza sus argumentos,
- llama a MCP con `ClientSession`,
- y devuelve el resultado al modelo.

## Variables de entorno

Las variables mas utiles son:

- `API_PORT`
- `MCP_PORT`
- `OLLAMA_URL`
- `OLLAMA_MODEL`
- `DATA_FILE`
- `SHOW_TRACE`

## Notas de diseno

- Elegi `biblioteca` porque es mas clara para explicar MCP que el clima.
- Use JSON local para que no dependas de una base externa.
- El cliente usa `llama3.1` local para que todo quede en tu maquina.
- El codigo incluye comentarios y docstrings para que sea facil de estudiar.
