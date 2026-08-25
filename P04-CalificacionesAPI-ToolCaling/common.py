from __future__ import annotations

import os
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.collation import Collation
from pymongo.errors import ConfigurationError, PyMongoError


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Variables de entorno compartidas por la API, el MCP y el chat de terminal.
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "Calificaciones")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "calificaciones")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")
MCP_PORT = int(os.getenv("MCP_PORT", "8001"))
MCP_BASE_URL = os.getenv("MCP_BASE_URL", f"http://{API_HOST}:{MCP_PORT}/mcp")

MONGO_COLLATION = Collation(locale="es", strength=1)

# Modelo de entrada para crear una calificacion.
class CalificacionCreate(BaseModel):
    alumno: str = Field(min_length=1)
    materia: str = Field(min_length=1)
    calificacion: float = Field(ge=0, le=10)
    fecha: Optional[date] = None
    periodo: Optional[str] = None


# Modelo de salida que usamos para responder en JSON limpio desde la API.
class CalificacionOut(BaseModel):
    id: Optional[str] = None
    alumno: str
    materia: str
    calificacion: float
    fecha: Optional[str] = None
    periodo: Optional[str] = None


def normalize_text(value: Any) -> str:
    """Normaliza texto para comparar nombres y filtros de forma consistente."""
    # Normaliza para comparar nombres aunque vengan con mayusculas o espacios extra.
    return " ".join(str(value or "").strip().lower().split())


def clean_text(value: Optional[str]) -> Optional[str]:
    """Limpia espacios extra en un texto opcional."""
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def to_iso_string(value: Any) -> Optional[str]:
    """Convierte fechas o textos a una cadena ISO simple si aplica."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return clean_text(str(value))


def to_public(document: dict[str, Any]) -> CalificacionOut:
    """Convierte un documento de Mongo al modelo de salida de la API."""
    # Convierte un documento de Mongo al formato que exponemos por la API.
    return CalificacionOut(
        id=str(document.get("_id")) if document.get("_id") else None,
        alumno=str(document.get("student_name") or ""),
        materia=str(document.get("subject") or ""),
        calificacion=float(document.get("grade") or 0),
        fecha=to_iso_string(document.get("fecha")),
        periodo=to_iso_string(document.get("periodo")),
    )


def build_filters_summary(
    alumno: Optional[str] = None,
    materia: Optional[str] = None,
    periodo: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """Arma un resumen limpio de los filtros recibidos en la consulta."""
    return {
        "alumno": clean_text(alumno),
        "materia": clean_text(materia),
        "periodo": clean_text(periodo),
    }


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    """Crea y reutiliza el cliente de MongoDB."""
    if not MONGODB_URI:
        raise ValueError("MONGODB_URI no esta configurado")
    return MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        retryWrites=True,
    )


def get_collection():
    """Devuelve la coleccion de calificaciones."""
    # Reutiliza el mismo cliente para no abrir una conexion nueva en cada request.
    return get_client()[MONGODB_DB][MONGODB_COLLECTION]


def ping_mongo() -> None:
    """Verifica que MongoDB responda con un ping simple."""
    # Health check simple contra el servidor de Mongo.
    get_client().admin.command("ping")


def is_mongo_error(error: Exception) -> bool:
    """Detecta si una excepcion viene de PyMongo o de la configuracion de Mongo."""
    return isinstance(error, (PyMongoError, ConfigurationError))


def list_calificaciones(
    alumno: Optional[str] = None,
    materia: Optional[str] = None,
    periodo: Optional[str] = None,
) -> list[CalificacionOut]:
    """Consulta calificaciones y aplica filtros opcionales por alumno, materia o periodo."""
    ping_mongo()
    filters = build_filters_summary(alumno, materia, periodo)
    # Pedimos solo los campos que realmente nos interesan para la respuesta.
    projection = {
        "_id": 1,
        "student_name": 1,
        "subject": 1,
        "grade": 1,
        "fecha": 1,
        "periodo": 1,
    }
    docs = list(get_collection().find({}, projection, collation=MONGO_COLLATION))
    items = []
    for doc in docs:
        # Filtra del lado de Python para mantener el comportamiento simple y legible.
        if filters["alumno"] and normalize_text(doc.get("student_name")) != normalize_text(filters["alumno"]):
            continue
        if filters["materia"] and normalize_text(doc.get("subject")) != normalize_text(filters["materia"]):
            continue
        if filters["periodo"] and normalize_text(doc.get("periodo")) != normalize_text(filters["periodo"]):
            continue
        items.append(to_public(doc))
    return items


def create_calificacion(payload: CalificacionCreate) -> CalificacionOut:
    """Inserta una nueva calificacion en MongoDB y devuelve el registro creado."""
    ping_mongo()
    # Guardamos el documento en el esquema real de la coleccion existente.
    doc = {
        "student_name": clean_text(payload.alumno),
        "subject": clean_text(payload.materia),
        "grade": float(payload.calificacion),
        "fecha": (payload.fecha or date.today()).isoformat(),
        "periodo": clean_text(payload.periodo),
    }
    result = get_collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    return to_public(doc)
