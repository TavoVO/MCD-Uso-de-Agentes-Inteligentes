# RAG PDF Local

Proyecto escolar para aprender RAG, con una arquitectura completa pero simple:

1. El usuario sube un PDF.
2. El texto se extrae y se divide en fragmentos.
3. Cada fragmento se convierte en embedding con Ollama.
4. Los embeddings se guardan en PostgreSQL con `pgvector`.
5. Cuando el usuario pregunta, el sistema busca los fragmentos más relevantes.
6. Esos fragmentos se agregan a un prompt y se envían a un LLM local.
7. La respuesta se muestra junto con las fuentes que se usaron.

## Tecnologías y rol de cada una

- `FastAPI`: backend sencillo, claro y fácil de explicar en clase.
- `PostgreSQL`: guarda de forma persistente el contenido procesado.
- `pgvector`: agrega soporte para almacenar embeddings y buscar por similitud.
- `SQLAlchemy`: mantiene el acceso a la base de datos ordenado y entendible.
- `Ollama`: corre modelos de IA localmente, sin APIs de pago.
- `llama3.1`: modelo local que genera la respuesta final.
- `nomic-embed-text`: modelo local para convertir texto en embeddings.
- `pypdf`: extrae el texto del PDF.
- `langchain-text-splitters`: divide el texto en chunks con overlap.
- HTML + CSS + JavaScript: interfaz simple para subir archivos, consultar y ver contexto.

## Qué es RAG

RAG significa `Retrieval-Augmented Generation`.

La idea es combinar dos etapas:

- `Retrieval`: buscar información relevante en una fuente externa.
- `Generation`: darle esa información a un LLM para que responda mejor.

En este proyecto, la fuente externa es el contenido del PDF cargado por el usuario. El sistema no intenta memorizar todo en el prompt; primero recupera los fragmentos relevantes desde PostgreSQL y después construye la respuesta con el LLM local.

## Arquitectura del proyecto

- `app/main.py`: aplicación FastAPI y endpoints.
- `app/models.py`: tablas de SQLAlchemy.
- `app/services/pdf_service.py`: extracción de texto y chunking.
- `app/services/ollama_service.py`: embeddings y generación con Ollama.
- `app/services/rag_service.py`: indexación, búsqueda y armado del prompt.
- `frontend/`: interfaz web estática.
- `schema.sql`: esquema de PostgreSQL con `pgvector`.

## Instalación en macOS

Este proyecto está pensado para macOS con PostgreSQL instalado de forma nativa, sin Docker.

### 1) Instalar PostgreSQL y pgvector

Con Homebrew:

```bash
xcode-select --install
brew update
brew install postgresql@17 pgvector
brew services start postgresql@17
```

Si prefieres verificar que quedó activo:

```bash
psql --version
brew services list
```

### 2) Crear la base de datos y aplicar el esquema

```bash
psql -d postgres -f schema.sql
```

Si tu usuario de PostgreSQL no es el actual, usa la opción `-U`.
Este script crea `rag_pdf_local` si todavía no existe y después conecta a esa base.

### 3) Instalar Ollama

Instala Ollama con el método oficial para macOS:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Después inicia el servicio de Ollama si no está corriendo:

```bash
ollama serve
```

En otra terminal, descarga los modelos:

```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

### 4) Preparar el backend

```bash
cd rag-pdf-local
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5) Correr la aplicación

```bash
uvicorn app.main:app --reload
```

Abre la app en:

```text
http://127.0.0.1:8000
```

## Flujo de uso

1. Abre la web.
2. Sube un PDF.
3. Espera a que termine el procesamiento.
4. Haz una pregunta sobre ese documento.
5. Revisa la respuesta y los fragmentos recuperados.

## Variables de entorno

El archivo `.env.example` incluye:

- `DATABASE_URL`
- `OLLAMA_URL`
- `LLM_MODEL`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSION`
- `CHUNK_SIZE`
- `CHUNK_OVERLAP`
- `TOP_K`
- `UPLOAD_DIR`
- `OLLAMA_TIMEOUT_SECONDS`

## Comandos útiles

Verificar Ollama:

```bash
curl http://localhost:11434/api/tags
```

Verificar PostgreSQL:

```bash
psql -d rag_pdf_local -c "SELECT version();"
```

Verificar pgvector:

```bash
psql -d rag_pdf_local -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

## Notas para explicar en clase

- No usamos Docker para que el proyecto muestre instalación nativa real.
- No usamos microservicios ni colas para mantener la arquitectura fácil de entender.
- Los embeddings se guardan en PostgreSQL para que la información quede persistente.
- El frontend enseña visualmente qué fragmentos fueron recuperados antes de responder.
