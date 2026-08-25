from __future__ import annotations

"""Funciones y modelos compartidos para la biblioteca.

La idea de este archivo es concentrar todo lo que no depende de FastAPI ni
del servidor MCP:

* configuracion del proyecto,
* modelos de datos,
* lectura y escritura del JSON local,
* logica de negocio de la biblioteca,
* definicion de tools para Ollama.

Asi mantenemos `api.py`, `mcp_server.py` y `chat_terminal.py` cortos y faciles
de leer.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Literal, Optional
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _resolve_data_file() -> Path:
    """Devuelve la ruta absoluta del JSON de libros."""

    raw_value = os.getenv("DATA_FILE", str(BASE_DIR / "data" / "libros.json"))
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate
    return (BASE_DIR / candidate).resolve()


API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8001"))
MCP_BASE_URL = os.getenv("MCP_BASE_URL", f"http://{MCP_HOST}:{MCP_PORT}/mcp")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
SHOW_TRACE = os.getenv("SHOW_TRACE", "1") != "0"

DATA_FILE = _resolve_data_file()
DATA_LOCK = Lock()


def _utc_now_iso() -> str:
    """Genera un timestamp ISO en UTC para prestamos y auditoria simple."""

    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any) -> str:
    """Normaliza un valor a texto simple sin espacios sobrantes."""

    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _clean_optional_text(value: Any) -> Optional[str]:
    """Normaliza un texto opcional y regresa None si queda vacio."""

    text = _clean_text(value)
    return text or None


def _normalize_text(value: Any) -> str:
    """Convierte texto a una forma estable para comparar sin importar mayusculas."""

    return _clean_text(value).lower()


def _clone_default_state() -> dict[str, Any]:
    """Crea una copia nueva del estado base de la biblioteca."""

    return json.loads(json.dumps(DEFAULT_LIBRARY_STATE, ensure_ascii=False))


DEFAULT_LIBRARY_STATE: dict[str, Any] = {
    "books": [
        {
            "id": "libro-001",
            "titulo": "Cien anos de soledad",
            "autor": "Gabriel Garcia Marquez",
            "anio_publicacion": 1967,
            "genero": "novela",
            "sinopsis": "Un recorrido por la historia de la familia Buendia en Macondo.",
            "estado": "disponible",
            "prestado_a": None,
            "prestado_en": None,
            "creado_en": "2026-07-28T00:00:00Z",
        },
        {
            "id": "libro-002",
            "titulo": "Clean Code",
            "autor": "Robert C. Martin",
            "anio_publicacion": 2008,
            "genero": "tecnologia",
            "sinopsis": "Principios practicos para escribir codigo mas legible.",
            "estado": "disponible",
            "prestado_a": None,
            "prestado_en": None,
            "creado_en": "2026-07-28T00:00:00Z",
        },
        {
            "id": "libro-003",
            "titulo": "El principito",
            "autor": "Antoine de Saint-Exupery",
            "anio_publicacion": 1943,
            "genero": "fabula",
            "sinopsis": "Una historia corta sobre amistad, infancia y sentido de la vida.",
            "estado": "prestado",
            "prestado_a": "Maria",
            "prestado_en": "2026-07-27T18:30:00Z",
            "creado_en": "2026-07-28T00:00:00Z",
        },
        {
            "id": "libro-004",
            "titulo": "Don Quijote de la Mancha",
            "autor": "Miguel de Cervantes",
            "anio_publicacion": 1605,
            "genero": "clasico",
            "sinopsis": "La historia del caballero que confunde molinos con gigantes.",
            "estado": "disponible",
            "prestado_a": None,
            "prestado_en": None,
            "creado_en": "2026-07-28T00:00:00Z",
        },
        {
            "id": "libro-005",
            "titulo": "La sombra del viento",
            "autor": "Carlos Ruiz Zafon",
            "anio_publicacion": 2001,
            "genero": "misterio",
            "sinopsis": "Una novela sobre libros, memoria y secretos de Barcelona.",
            "estado": "disponible",
            "prestado_a": None,
            "prestado_en": None,
            "creado_en": "2026-07-28T00:00:00Z",
        },
    ]
}


class LibroCreate(BaseModel):
    """Datos necesarios para registrar un libro nuevo."""

    titulo: str = Field(min_length=1, description="Titulo del libro.")
    autor: str = Field(min_length=1, description="Autor principal del libro.")
    anio_publicacion: Optional[int] = Field(default=None, ge=0, le=3000)
    genero: Optional[str] = Field(default=None, description="Genero o categoria.")
    sinopsis: Optional[str] = Field(default=None, description="Descripcion corta.")


class LibroMovimiento(BaseModel):
    """Datos para prestar o devolver un libro."""

    libro_id: Optional[str] = Field(default=None, description="Identificador del libro.")
    titulo: Optional[str] = Field(default=None, description="Titulo del libro.")
    prestado_a: Optional[str] = Field(default=None, description="Persona que recibe el libro.")


class LibroSalida(BaseModel):
    """Formato publico que expone la API y que ve el cliente MCP."""

    id: str
    titulo: str
    autor: str
    anio_publicacion: Optional[int] = None
    genero: Optional[str] = None
    sinopsis: Optional[str] = None
    estado: Literal["disponible", "prestado"]
    prestado_a: Optional[str] = None
    prestado_en: Optional[str] = None
    creado_en: Optional[str] = None


def ensure_data_file() -> None:
    """Crea el archivo JSON si todavia no existe."""

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        save_library_state(_clone_default_state())


def load_library_state() -> dict[str, Any]:
    """Carga el estado completo de la biblioteca desde disco."""

    ensure_data_file()
    with DATA_LOCK:
        with DATA_FILE.open("r", encoding="utf-8") as handle:
            state = json.load(handle)

    if not isinstance(state, dict):
        raise ValueError("El archivo de datos debe contener un objeto JSON.")
    books = state.get("books")
    if not isinstance(books, list):
        raise ValueError("El archivo de datos debe incluir una lista llamada 'books'.")
    return state


def save_library_state(state: dict[str, Any]) -> None:
    """Guarda el estado completo en disco de forma atomica."""

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = DATA_FILE.with_suffix(DATA_FILE.suffix + ".tmp")
    payload = json.dumps(state, indent=2, ensure_ascii=False, sort_keys=False)

    with DATA_LOCK:
        with tmp_file.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
        tmp_file.replace(DATA_FILE)


def get_books_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrae la lista de libros desde el estado cargado."""

    books = state.get("books", [])
    if not isinstance(books, list):
        raise ValueError("La llave 'books' debe ser una lista.")
    return books


def build_filters_summary(
    titulo: Optional[str] = None,
    autor: Optional[str] = None,
    genero: Optional[str] = None,
    estado: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """Devuelve un resumen limpio de los filtros usados."""

    return {
        "titulo": _clean_optional_text(titulo),
        "autor": _clean_optional_text(autor),
        "genero": _clean_optional_text(genero),
        "estado": _clean_optional_text(estado),
    }


def _matches_text_filter(source: Any, requested: Optional[str]) -> bool:
    """Comprueba si un texto coincide con un filtro opcional."""

    if not requested:
        return True
    source_text = _normalize_text(source)
    requested_text = _normalize_text(requested)
    return requested_text in source_text


def _serialize_book(document: dict[str, Any]) -> LibroSalida:
    """Convierte un documento interno en un modelo publico."""

    return LibroSalida(
        id=str(document.get("id") or ""),
        titulo=_clean_text(document.get("titulo")),
        autor=_clean_text(document.get("autor")),
        anio_publicacion=document.get("anio_publicacion"),
        genero=_clean_optional_text(document.get("genero")),
        sinopsis=_clean_optional_text(document.get("sinopsis")),
        estado=document.get("estado", "disponible"),
        prestado_a=_clean_optional_text(document.get("prestado_a")),
        prestado_en=_clean_optional_text(document.get("prestado_en")),
        creado_en=_clean_optional_text(document.get("creado_en")),
    )


def _generate_book_id() -> str:
    """Crea un identificador corto y facil de leer para cada libro nuevo."""

    return f"libro-{uuid4().hex[:8]}"


def _resolve_book_index(
    books: list[dict[str, Any]],
    *,
    libro_id: Optional[str] = None,
    titulo: Optional[str] = None,
) -> int:
    """Encuentra un libro por id o por titulo.

    El orden de busqueda es:
    1. id exacto,
    2. titulo exacto sin importar mayusculas,
    3. titulo parcial si solo hay una coincidencia.
    """

    cleaned_id = _clean_optional_text(libro_id)
    cleaned_title = _clean_optional_text(titulo)

    if cleaned_id:
        for index, book in enumerate(books):
            if _normalize_text(book.get("id")) == _normalize_text(cleaned_id):
                return index

    if cleaned_title:
        exact_matches = [
            index
            for index, book in enumerate(books)
            if _normalize_text(book.get("titulo")) == _normalize_text(cleaned_title)
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            raise ValueError(
                f"El titulo '{cleaned_title}' coincide con varios libros. Usa el id para elegir uno."
            )

        partial_matches = [
            index
            for index, book in enumerate(books)
            if _normalize_text(cleaned_title) in _normalize_text(book.get("titulo"))
        ]
        if len(partial_matches) == 1:
            return partial_matches[0]
        if len(partial_matches) > 1:
            candidates = ", ".join(_clean_text(books[index].get("titulo")) for index in partial_matches)
            raise ValueError(
                f"El titulo '{cleaned_title}' es ambiguo. Coincide con: {candidates}."
            )

    raise ValueError("No encontre un libro con ese id o titulo.")


def list_books(
    titulo: Optional[str] = None,
    autor: Optional[str] = None,
    genero: Optional[str] = None,
    estado: Optional[str] = None,
) -> list[LibroSalida]:
    """Devuelve los libros aplicando filtros opcionales."""

    state = load_library_state()
    books = get_books_from_state(state)
    filters = build_filters_summary(titulo=titulo, autor=autor, genero=genero, estado=estado)

    results: list[LibroSalida] = []
    for document in books:
        if filters["titulo"] and not _matches_text_filter(document.get("titulo"), filters["titulo"]):
            continue
        if filters["autor"] and not _matches_text_filter(document.get("autor"), filters["autor"]):
            continue
        if filters["genero"] and not _matches_text_filter(document.get("genero"), filters["genero"]):
            continue
        if filters["estado"] and _normalize_text(document.get("estado")) != _normalize_text(filters["estado"]):
            continue
        results.append(_serialize_book(document))

    return results


def add_book(payload: LibroCreate) -> LibroSalida:
    """Agrega un libro nuevo al JSON local."""

    state = load_library_state()
    books = get_books_from_state(state)
    normalized_title = _normalize_text(payload.titulo)

    for document in books:
        if _normalize_text(document.get("titulo")) == normalized_title:
            raise ValueError(f"Ya existe un libro con el titulo '{payload.titulo}'.")

    document = {
        "id": _generate_book_id(),
        "titulo": _clean_text(payload.titulo),
        "autor": _clean_text(payload.autor),
        "anio_publicacion": payload.anio_publicacion,
        "genero": _clean_optional_text(payload.genero),
        "sinopsis": _clean_optional_text(payload.sinopsis),
        "estado": "disponible",
        "prestado_a": None,
        "prestado_en": None,
        "creado_en": _utc_now_iso(),
    }
    books.append(document)
    save_library_state(state)
    return _serialize_book(document)


def loan_book(payload: LibroMovimiento) -> LibroSalida:
    """Marca un libro como prestado."""

    state = load_library_state()
    books = get_books_from_state(state)
    index = _resolve_book_index(books, libro_id=payload.libro_id, titulo=payload.titulo)
    document = books[index]

    if _normalize_text(document.get("estado")) == "prestado":
        current_borrower = _clean_optional_text(document.get("prestado_a")) or "otra persona"
        raise ValueError(f"El libro '{document.get('titulo')}' ya esta prestado a {current_borrower}.")

    borrower = _clean_optional_text(payload.prestado_a)
    document["estado"] = "prestado"
    document["prestado_a"] = borrower or "Sin especificar"
    document["prestado_en"] = _utc_now_iso()
    save_library_state(state)
    return _serialize_book(document)


def return_book(payload: LibroMovimiento) -> LibroSalida:
    """Marca un libro como disponible otra vez."""

    state = load_library_state()
    books = get_books_from_state(state)
    index = _resolve_book_index(books, libro_id=payload.libro_id, titulo=payload.titulo)
    document = books[index]

    if _normalize_text(document.get("estado")) != "prestado":
        raise ValueError(f"El libro '{document.get('titulo')}' ya estaba disponible.")

    document["estado"] = "disponible"
    document["prestado_a"] = None
    document["prestado_en"] = None
    save_library_state(state)
    return _serialize_book(document)


OLLAMA_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "listar_libros",
            "description": (
                "Lista los libros de la biblioteca. "
                "Usa esta tool cuando el usuario quiera ver libros, buscar por titulo, autor, genero o estado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Texto para buscar en el titulo."},
                    "autor": {"type": "string", "description": "Texto para buscar en el autor."},
                    "genero": {"type": "string", "description": "Genero o categoria."},
                    "estado": {
                        "type": "string",
                        "description": "Estado del libro: disponible o prestado.",
                        "enum": ["disponible", "prestado"],
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agregar_libro",
            "description": "Agrega un libro nuevo a la biblioteca local.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Titulo del libro."},
                    "autor": {"type": "string", "description": "Autor principal."},
                    "anio_publicacion": {"type": "integer", "description": "Ano de publicacion."},
                    "genero": {"type": "string", "description": "Genero o categoria."},
                    "sinopsis": {"type": "string", "description": "Descripcion corta opcional."},
                },
                "required": ["titulo", "autor"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prestar_libro",
            "description": (
                "Marca un libro como prestado. "
                "Si el usuario dice que quiere sacar o prestar un libro, usa esta tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "libro_id": {"type": "string", "description": "Identificador del libro."},
                    "titulo": {"type": "string", "description": "Titulo del libro."},
                    "prestado_a": {
                        "type": "string",
                        "description": "Nombre de la persona a la que se presta el libro.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "devolver_libro",
            "description": "Marca un libro como disponible otra vez.",
            "parameters": {
                "type": "object",
                "properties": {
                    "libro_id": {"type": "string", "description": "Identificador del libro."},
                    "titulo": {"type": "string", "description": "Titulo del libro."},
                },
                "additionalProperties": False,
            },
        },
    },
]

