import json
import os
import re
import unicodedata
from typing import Any, Optional

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for
from openai import OpenAI
from pymongo import MongoClient
from pymongo.collation import Collation
from pymongo.errors import ConfigurationError, PyMongoError


BASE_DIR = os.path.dirname(__file__)
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "Calificaciones")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "Calificaciones")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or os.urandom(24)
CHAT_HISTORY_LIMIT = int(os.getenv("CHAT_HISTORY_LIMIT", "20"))
MAX_TOOL_CALL_ROUNDS = int(os.getenv("MAX_TOOL_CALL_ROUNDS", "5"))
EXIT_KEYWORDS = {
    "exit",
    "salir",
    "cerrar",
    "terminar",
    "fin",
    "bye",
    "bye bye",
    "adios",
    "adiós",
    "quit",
    "stop",
}
RESTART_KEYWORDS = {
    "reiniciar",
    "reinicia",
    "reiniciar chat",
    "reinicia chat",
    "reiniciar conversacion",
    "reiniciar conversación",
    "reset",
    "restart",
    "volver a empezar",
}

if not OPENAI_API_KEY:
    raise ValueError("No se encontró OPENAI_API_KEY en ToolFunctions/.env")

if not MONGODB_URI:
    raise ValueError("No se encontró MONGODB_URI en ToolFunctions/.env")


client = OpenAI(api_key=OPENAI_API_KEY)
MONGO_COLLATION = Collation(locale="es", strength=1)

mongo_client: Optional[MongoClient] = None
db = None
collection = None
mongo_init_error: Optional[str] = None

try:
    mongo_client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        retryWrites=True,
    )
    db = mongo_client[MONGODB_DB]
    collection = db[MONGODB_COLLECTION]
except (PyMongoError, ConfigurationError) as exc:
    mongo_init_error = str(exc)


app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config["JSON_AS_ASCII"] = False


SYSTEM_PROMPT = (
    "Eres un asistente en español para consultar y administrar calificaciones en MongoDB. "
    "La base de datos es la única fuente de verdad. "
    "Usa herramientas cuando necesites leer o modificar datos. "
    "Nunca inventes calificaciones, alumnos o materias. "
    "Si falta información, pide solo el dato faltante. "
    "Si el usuario pregunta por la calificación de un alumno sin especificar materia, "
    "pregunta si quiere una materia concreta o el promedio de todas las materias. "
    "Si el usuario pide borrar un alumno o una materia, pide confirmación explícita antes de ejecutar el cambio. "
    "Responde de forma breve, clara y útil."
)


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_text(text: str) -> str:
    return strip_accents(text).lower().strip()


def is_exit_command(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in EXIT_KEYWORDS


def is_restart_command(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in RESTART_KEYWORDS


def clean_fragment(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip().strip("¿?!.:,;")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def clean_student_name(value: Optional[str]) -> Optional[str]:
    cleaned = clean_fragment(value)
    if not cleaned:
        return None
    cleaned = re.sub(
        r"^(de|del|de la|de el|el|la|alumno|alumna|estudiante|llamado|llamada)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return clean_fragment(cleaned)


def clean_subject_name(value: Optional[str]) -> Optional[str]:
    cleaned = clean_fragment(value)
    if not cleaned:
        return None
    cleaned = re.sub(
        r"^(de|del|en|la materia de|materia de)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return clean_fragment(cleaned)


def parse_grade_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = clean_fragment(str(value))
    if not cleaned:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", cleaned)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def get_mongo_status() -> tuple[bool, str]:
    if mongo_client is None:
        return False, f"No se pudo inicializar MongoDB: {mongo_init_error or 'configuración inválida'}"
    try:
        mongo_client.admin.command("ping")
        return True, f"MongoDB conectado a {MONGODB_DB}.{MONGODB_COLLECTION}"
    except PyMongoError as exc:
        return False, f"No se pudo conectar a MongoDB: {exc}"


def ensure_collection_available() -> None:
    if collection is None:
        raise RuntimeError(mongo_init_error or "MongoDB no está disponible")
    ok, status = get_mongo_status()
    if not ok:
        raise RuntimeError(status)


def project_fields() -> dict[str, int]:
    return {"_id": 0, "student_name": 1, "subject": 1, "grade": 1}


def all_records() -> list[dict[str, Any]]:
    ensure_collection_available()
    return list(collection.find({}, project_fields(), collation=MONGO_COLLATION))


def find_student_docs(student_name: str) -> list[dict[str, Any]]:
    ensure_collection_available()
    query = {"student_name": student_name}
    docs = list(collection.find(query, project_fields(), collation=MONGO_COLLATION))
    if docs:
        return docs

    target = normalize_text(student_name)
    return [
        doc
        for doc in all_records()
        if normalize_text(str(doc.get("student_name", ""))) == target
    ]


def find_subject_doc(student_name: str, subject: str) -> Optional[dict[str, Any]]:
    ensure_collection_available()
    doc = collection.find_one(
        {"student_name": student_name, "subject": subject},
        project_fields(),
        collation=MONGO_COLLATION,
    )
    if doc is not None:
        return doc

    target_student = normalize_text(student_name)
    target_subject = normalize_text(subject)
    for item in find_student_docs(student_name):
        if normalize_text(str(item.get("student_name", ""))) != target_student:
            continue
        if normalize_text(str(item.get("subject", ""))) == target_subject:
            return item
    return None


def unique_display_values(records: list[dict[str, Any]], field: str) -> list[str]:
    seen: dict[str, str] = {}
    for record in records:
        value = record.get(field)
        if not value:
            continue
        cleaned = clean_fragment(str(value))
        if not cleaned:
            continue
        normalized = normalize_text(cleaned)
        if normalized not in seen:
            seen[normalized] = cleaned
    return [seen[key] for key in sorted(seen.keys())]


def list_students() -> list[str]:
    return unique_display_values(all_records(), "student_name")


def list_subjects() -> list[str]:
    return unique_display_values(all_records(), "subject")


def subjects_for_student(student_name: str) -> list[str]:
    return unique_display_values(find_student_docs(student_name), "subject")


def average_from_grades(grades: list[float]) -> float:
    return round(sum(grades) / len(grades), 2)


def student_average(student_name: str) -> dict[str, Any]:
    docs = find_student_docs(student_name)
    if not docs:
        return {"status": "error", "message": f"No se encontraron calificaciones para {student_name}."}

    grades = [float(doc["grade"]) for doc in docs if isinstance(doc.get("grade"), (int, float))]
    if not grades:
        return {"status": "error", "message": f"No se encontraron calificaciones válidas para {student_name}."}

    subjects = subjects_for_student(student_name)
    avg = average_from_grades(grades)
    display_name = docs[0].get("student_name") or student_name
    return {
        "status": "ok",
        "student_name": display_name,
        "average": avg,
        "subjects": subjects,
        "message": (
            f"El promedio de {display_name} es {avg:.2f}. "
            f"Materias registradas: {', '.join(subjects) if subjects else 'sin materias registradas'}."
        ),
    }


def general_average() -> dict[str, Any]:
    docs = all_records()
    grades = [float(doc["grade"]) for doc in docs if isinstance(doc.get("grade"), (int, float))]
    if not grades:
        return {"status": "error", "message": "No hay calificaciones válidas registradas para calcular el promedio general."}

    avg = average_from_grades(grades)
    students = list_students()
    return {
        "status": "ok",
        "average": avg,
        "students": students,
        "message": (
            f"El promedio general de toda la colección es {avg:.2f}. "
            f"Alumnos detectados: {', '.join(students) if students else 'sin alumnos registrados'}."
        ),
    }


def subject_grade(student_name: str, subject: str) -> dict[str, Any]:
    doc = find_subject_doc(student_name, subject)
    if doc is None:
        available = subjects_for_student(student_name)
        suggestion = f" Materias disponibles: {', '.join(available)}." if available else ""
        return {
            "status": "error",
            "message": f"No se encontró la calificación de {student_name} en {subject}.{suggestion}",
        }

    return {
        "status": "ok",
        "student_name": doc.get("student_name"),
        "subject": doc.get("subject"),
        "grade": doc.get("grade"),
        "message": f"La calificación de {doc.get('student_name')} en {doc.get('subject')} es {doc.get('grade')}.",
    }


def student_grade_list(student_name: str) -> dict[str, Any]:
    docs = find_student_docs(student_name)
    if not docs:
        return {"status": "error", "message": f"No se encontraron calificaciones para {student_name}."}

    parts = [f"{doc.get('subject', 'Sin materia')}: {doc.get('grade')}" for doc in docs]
    grades = [float(doc["grade"]) for doc in docs if isinstance(doc.get("grade"), (int, float))]
    avg_text = f" Promedio: {average_from_grades(grades):.2f}." if grades else ""
    return {
        "status": "ok",
        "message": f"Calificaciones de {docs[0].get('student_name') or student_name}: " + "; ".join(parts) + avg_text,
    }


def student_report(student_name: str) -> dict[str, Any]:
    docs = find_student_docs(student_name)
    if not docs:
        return {"status": "error", "message": f"No se encontraron registros para {student_name}."}

    subjects = subjects_for_student(student_name)
    grades = [float(doc["grade"]) for doc in docs if isinstance(doc.get("grade"), (int, float))]
    avg_text = f" Promedio: {average_from_grades(grades):.2f}." if grades else ""
    return {
        "status": "ok",
        "message": (
            f"{docs[0].get('student_name')}: materias {', '.join(subjects) if subjects else 'sin materias registradas'}."
            f"{avg_text}"
        ),
    }


def summary_all_students() -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for doc in all_records():
        key = normalize_text(str(doc.get("student_name", "")))
        if not key:
            continue
        if key not in grouped:
            grouped[key] = {"student_name": doc.get("student_name"), "docs": []}
        grouped[key]["docs"].append(doc)

    if not grouped:
        return {"status": "error", "message": "No hay alumnos registrados."}

    lines = []
    for key in sorted(grouped.keys()):
        student_name = grouped[key]["student_name"] or key.title()
        docs = grouped[key]["docs"]
        subjects = unique_display_values(docs, "subject")
        grades = [float(doc["grade"]) for doc in docs if isinstance(doc.get("grade"), (int, float))]
        avg_text = f"{average_from_grades(grades):.2f}" if grades else "N/A"
        lines.append(
            f"{student_name} | Materias: {', '.join(subjects) if subjects else 'sin materias'} | Promedio: {avg_text}"
        )

    return {"status": "ok", "message": "Lista de alumnos con materias y promedios: " + " || ".join(lines)}


def perform_upsert_grade(student_name: str, subject: str, grade: float) -> dict[str, Any]:
    ensure_collection_available()
    student_name = clean_student_name(student_name) or student_name
    subject = clean_subject_name(subject) or subject
    result = collection.update_one(
        {"student_name": student_name, "subject": subject},
        {"$set": {"student_name": student_name, "subject": subject, "grade": grade}},
        upsert=True,
        collation=MONGO_COLLATION,
    )
    return {
        "status": "ok",
        "message": (
            f"Registro guardado: {student_name} - {subject} = {grade}. "
            f"{'Se actualizó un registro existente.' if result.matched_count else 'Se creó un nuevo registro.'}"
        ),
    }


def perform_set_grade_for_all_subjects(student_name: str, grade: float) -> dict[str, Any]:
    subjects = list_subjects()
    if not subjects:
        return {"status": "error", "message": "No hay materias registradas para aplicar una calificación global."}

    for subject in subjects:
        perform_upsert_grade(student_name, subject, grade)

    return {
        "status": "ok",
        "message": f"Se guardó a {student_name} con calificación {grade} en todas las materias registradas.",
    }


def perform_rename_student(old_name: str, new_name: str) -> dict[str, Any]:
    ensure_collection_available()
    old_name = clean_student_name(old_name) or old_name
    new_name = clean_student_name(new_name) or new_name
    result = collection.update_many(
        {"student_name": old_name},
        {"$set": {"student_name": new_name}},
        collation=MONGO_COLLATION,
    )
    if result.matched_count == 0:
        return {"status": "error", "message": f"No se encontró al alumno {old_name} para renombrarlo."}
    return {"status": "ok", "message": f"Se renombró a {old_name} como {new_name} en {result.modified_count} registros."}


def perform_rename_subject(student_name: str, old_subject: str, new_subject: str) -> dict[str, Any]:
    ensure_collection_available()
    student_name = clean_student_name(student_name) or student_name
    old_subject = clean_subject_name(old_subject) or old_subject
    new_subject = clean_subject_name(new_subject) or new_subject
    result = collection.update_many(
        {"student_name": student_name, "subject": old_subject},
        {"$set": {"subject": new_subject}},
        collation=MONGO_COLLATION,
    )
    if result.matched_count == 0:
        return {"status": "error", "message": f"No se encontró la materia {old_subject} de {student_name} para renombrarla."}
    return {"status": "ok", "message": f"Se renombró la materia {old_subject} de {student_name} a {new_subject}."}


def perform_delete_student(student_name: str) -> dict[str, Any]:
    ensure_collection_available()
    student_name = clean_student_name(student_name) or student_name
    result = collection.delete_many({"student_name": student_name}, collation=MONGO_COLLATION)
    if result.deleted_count == 0:
        return {"status": "error", "message": f"No se encontró al alumno {student_name} para eliminar."}
    return {"status": "ok", "message": f"Se eliminó a {student_name} y {result.deleted_count} registros relacionados."}


def perform_delete_subject(student_name: str, subject: str) -> dict[str, Any]:
    ensure_collection_available()
    student_name = clean_student_name(student_name) or student_name
    subject = clean_subject_name(subject) or subject
    result = collection.delete_many(
        {"student_name": student_name, "subject": subject},
        collation=MONGO_COLLATION,
    )
    if result.deleted_count == 0:
        return {"status": "error", "message": f"No se encontró la materia {subject} de {student_name} para eliminar."}
    return {"status": "ok", "message": f"Se eliminó la materia {subject} de {student_name}."}


def list_students_with_subjects_and_averages() -> dict[str, Any]:
    return summary_all_students()


def affirmative_response(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in {
        "si",
        "sí",
        "s",
        "ok",
        "okay",
        "vale",
        "adelante",
        "confirmo",
        "confirmar",
        "claro",
        "hazlo",
        "de acuerdo",
    }


def negative_response(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in {
        "no",
        "nop",
        "cancelar",
        "cancela",
        "mejor no",
        "no gracias",
    }


def get_messages() -> list[dict[str, str]]:
    messages = session.get("messages")
    if not isinstance(messages, list):
        messages = []
    return messages


def save_messages(messages: list[dict[str, str]]) -> None:
    session["messages"] = messages[-CHAT_HISTORY_LIMIT:]


def reset_chat_state() -> None:
    session.pop("messages", None)
    clear_pending_action()


def start_fresh_conversation() -> list[dict[str, str]]:
    reset_chat_state()
    greeting = [
        {
            "role": "assistant",
            "content": "Conversación reiniciada. Escribe hola para comenzar otra vez.",
        }
    ]
    save_messages(greeting)
    return greeting


def get_pending_action() -> Optional[dict[str, Any]]:
    pending = session.get("pending_action")
    return pending if isinstance(pending, dict) else None


def clear_pending_action() -> None:
    session.pop("pending_action", None)


def store_pending_action(action: dict[str, Any]) -> None:
    session["pending_action"] = action


def chat_history_for_openai(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    relevant = messages[-CHAT_HISTORY_LIMIT:]
    return [{"role": msg["role"], "content": msg["content"]} for msg in relevant if msg.get("role") in {"user", "assistant"}]


def tool_schema(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": parameters,
        "strict": True,
    }


OPENAI_TOOLS = [
    tool_schema(
        "ping_mongo",
        "Verifica si MongoDB responde y devuelve el estado actual de conexión.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
    tool_schema(
        "list_students",
        "Lista los alumnos registrados en la colección.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
    tool_schema(
        "list_subjects",
        "Lista todas las materias registradas en la colección.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
    tool_schema(
        "list_subjects_for_student",
        "Lista las materias registradas para un alumno específico.",
        {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre del alumno.",
                }
            },
            "required": ["student_name"],
            "additionalProperties": False,
        },
    ),
    tool_schema(
        "get_student_average",
        "Calcula el promedio de todas las materias de un alumno.",
        {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre del alumno.",
                }
            },
            "required": ["student_name"],
            "additionalProperties": False,
        },
    ),
    tool_schema(
        "get_general_average",
        "Calcula el promedio general de todos los registros.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
    tool_schema(
        "get_student_report",
        "Devuelve un reporte con materias y promedio de un alumno.",
        {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre del alumno.",
                }
            },
            "required": ["student_name"],
            "additionalProperties": False,
        },
    ),
    tool_schema(
        "get_subject_grade",
        "Busca la calificación de un alumno en una materia específica.",
        {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre del alumno.",
                },
                "subject": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre de la materia.",
                },
            },
            "required": ["student_name", "subject"],
            "additionalProperties": False,
        },
    ),
    tool_schema(
        "list_students_with_subjects_and_averages",
        "Devuelve la lista de alumnos con sus materias y promedios.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
    tool_schema(
        "upsert_grade",
        "Agrega o actualiza la calificación de un alumno en una materia.",
        {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre del alumno.",
                },
                "subject": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre de la materia.",
                },
                "grade": {
                    "type": "number",
                    "description": "Calificación numérica.",
                },
            },
            "required": ["student_name", "subject", "grade"],
            "additionalProperties": False,
        },
    ),
    tool_schema(
        "set_grade_for_all_subjects",
        "Guarda la misma calificación en todas las materias registradas de un alumno.",
        {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre del alumno.",
                },
                "grade": {
                    "type": "number",
                    "description": "Calificación numérica.",
                },
            },
            "required": ["student_name", "grade"],
            "additionalProperties": False,
        },
    ),
    tool_schema(
        "rename_student",
        "Renombra a un alumno en todos sus registros.",
        {
            "type": "object",
            "properties": {
                "old_student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre actual del alumno.",
                },
                "new_student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nuevo nombre del alumno.",
                },
            },
            "required": ["old_student_name", "new_student_name"],
            "additionalProperties": False,
        },
    ),
    tool_schema(
        "rename_subject",
        "Renombra una materia de un alumno en todos sus registros.",
        {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre del alumno.",
                },
                "old_subject": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre actual de la materia.",
                },
                "new_subject": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nuevo nombre de la materia.",
                },
            },
            "required": ["student_name", "old_subject", "new_subject"],
            "additionalProperties": False,
        },
    ),
    tool_schema(
        "delete_student",
        "Elimina a un alumno y todas sus calificaciones solo después de confirmación explícita.",
        {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre del alumno.",
                }
            },
            "required": ["student_name"],
            "additionalProperties": False,
        },
    ),
    tool_schema(
        "delete_subject",
        "Elimina una materia de un alumno solo después de confirmación explícita.",
        {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre del alumno.",
                },
                "subject": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Nombre de la materia.",
                },
            },
            "required": ["student_name", "subject"],
            "additionalProperties": False,
        },
    ),
]


def response_item_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def extract_function_calls(response: Any) -> list[dict[str, Any]]:
    calls = []
    for item in getattr(response, "output", []) or []:
        item_type = response_item_value(item, "type")
        if item_type != "function_call":
            continue
        calls.append(
            {
                "name": response_item_value(item, "name"),
                "call_id": response_item_value(item, "call_id"),
                "arguments": response_item_value(item, "arguments") or "{}",
            }
        )
    return calls


def parse_tool_arguments(arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def tool_result_payload(status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"status": status, "message": message}
    payload.update(extra)
    return payload


def handle_delete_confirmation_request(action_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if action_type == "delete_student":
        student_name = clean_student_name(data.get("student_name"))
        if not student_name:
            return tool_result_payload("error", "Falta el nombre del alumno para eliminarlo.")
        store_pending_action({"type": "delete_student", "student_name": student_name})
        return tool_result_payload(
            "confirmation_required",
            f"¿Confirmas que quieres eliminar a {student_name} y todas sus calificaciones? Responde 'sí' para continuar.",
            pending_action={"type": "delete_student", "student_name": student_name},
        )

    if action_type == "delete_subject":
        student_name = clean_student_name(data.get("student_name"))
        subject = clean_subject_name(data.get("subject"))
        if not student_name or not subject:
            return tool_result_payload("error", "Faltan el alumno o la materia para eliminar el registro.")
        store_pending_action({"type": "delete_subject", "student_name": student_name, "subject": subject})
        return tool_result_payload(
            "confirmation_required",
            f"¿Confirmas que quieres eliminar la materia {subject} de {student_name}? Responde 'sí' para continuar.",
            pending_action={"type": "delete_subject", "student_name": student_name, "subject": subject},
        )

    return tool_result_payload("error", "Acción destructiva no reconocida.")


def execute_tool_call(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "ping_mongo":
        ok, status = get_mongo_status()
        return tool_result_payload("ok" if ok else "error", status)

    if tool_name == "list_students":
        names = list_students()
        return tool_result_payload(
            "ok",
            "Alumnos registrados: " + (", ".join(names) if names else "No hay alumnos registrados."),
            students=names,
        )

    if tool_name == "list_subjects":
        subjects = list_subjects()
        return tool_result_payload(
            "ok",
            "Materias registradas: " + (", ".join(subjects) if subjects else "No hay materias registradas."),
            subjects=subjects,
        )

    if tool_name == "list_subjects_for_student":
        student_name = clean_student_name(args.get("student_name"))
        if not student_name:
            return tool_result_payload("error", "Falta el nombre del alumno para listar sus materias.")
        subjects = subjects_for_student(student_name)
        if not subjects:
            return tool_result_payload("error", f"No se encontraron materias registradas para {student_name}.")
        return tool_result_payload("ok", f"Materias de {student_name}: " + ", ".join(subjects), student_name=student_name, subjects=subjects)

    if tool_name == "get_student_average":
        student_name = clean_student_name(args.get("student_name"))
        if not student_name:
            return tool_result_payload("error", "Falta el nombre del alumno para calcular su promedio.")
        return student_average(student_name)

    if tool_name == "get_general_average":
        return general_average()

    if tool_name == "get_student_report":
        student_name = clean_student_name(args.get("student_name"))
        if not student_name:
            return tool_result_payload("error", "Falta el nombre del alumno para generar su reporte.")
        return student_report(student_name)

    if tool_name == "get_subject_grade":
        student_name = clean_student_name(args.get("student_name"))
        subject = clean_subject_name(args.get("subject"))
        if not student_name or not subject:
            return tool_result_payload("error", "Falta el alumno o la materia para consultar la calificación.")
        return subject_grade(student_name, subject)

    if tool_name == "list_students_with_subjects_and_averages":
        return list_students_with_subjects_and_averages()

    if tool_name == "upsert_grade":
        student_name = clean_student_name(args.get("student_name"))
        subject = clean_subject_name(args.get("subject"))
        grade = parse_grade_value(args.get("grade"))
        if not student_name or not subject or grade is None:
            return tool_result_payload("error", "Faltan el alumno, la materia o la calificación para guardar el registro.")
        return perform_upsert_grade(student_name, subject, grade)

    if tool_name == "set_grade_for_all_subjects":
        student_name = clean_student_name(args.get("student_name"))
        grade = parse_grade_value(args.get("grade"))
        if not student_name or grade is None:
            return tool_result_payload("error", "Faltan el alumno o la calificación para aplicar la nota a todas las materias.")
        return perform_set_grade_for_all_subjects(student_name, grade)

    if tool_name == "rename_student":
        old_name = clean_student_name(args.get("old_student_name"))
        new_name = clean_student_name(args.get("new_student_name"))
        if not old_name or not new_name:
            return tool_result_payload("error", "Faltan el nombre actual o el nuevo nombre del alumno.")
        return perform_rename_student(old_name, new_name)

    if tool_name == "rename_subject":
        student_name = clean_student_name(args.get("student_name"))
        old_subject = clean_subject_name(args.get("old_subject"))
        new_subject = clean_subject_name(args.get("new_subject"))
        if not student_name or not old_subject or not new_subject:
            return tool_result_payload("error", "Faltan el alumno, la materia actual o la nueva materia.")
        return perform_rename_subject(student_name, old_subject, new_subject)

    if tool_name == "delete_student":
        return handle_delete_confirmation_request("delete_student", args)

    if tool_name == "delete_subject":
        return handle_delete_confirmation_request("delete_subject", args)

    return tool_result_payload("error", f"Herramienta no reconocida: {tool_name}")


def create_openai_response(input_items: list[dict[str, Any]]) -> Any:
    return client.responses.create(
        model=OPENAI_MODEL,
        instructions=SYSTEM_PROMPT,
        input=input_items,
        tools=OPENAI_TOOLS,
        tool_choice="auto",
        temperature=0.2,
        max_output_tokens=400,
    )


def extract_final_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text).strip()

    pieces: list[str] = []
    for item in getattr(response, "output", []) or []:
        if response_item_value(item, "type") == "message":
            content = response_item_value(item, "content")
            if isinstance(content, str):
                pieces.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                        pieces.append(str(part.get("text", "")))
    return " ".join(piece.strip() for piece in pieces if piece.strip())


def run_function_calling_turn(user_message: str, history: list[dict[str, str]]) -> tuple[str, Optional[dict[str, Any]], Any]:
    conversation = chat_history_for_openai(history)
    conversation.append({"role": "user", "content": user_message})

    response = create_openai_response(conversation)
    last_response = response

    tool_rounds = 0
    while True:
        if tool_rounds >= MAX_TOOL_CALL_ROUNDS:
            return "No pude completar la consulta porque el modelo pidió demasiadas herramientas.", None, last_response
        tool_rounds += 1

        calls = extract_function_calls(response)
        if not calls:
            final_text = extract_final_text(response) or "No pude generar una respuesta clara."
            break

        tool_outputs = []
        confirmation_message = None
        confirmation_payload = None
        saw_valid_tool_output = False

        for call in calls:
            tool_name = call.get("name")
            call_id = call.get("call_id")
            args = parse_tool_arguments(call.get("arguments", "{}"))
            if not tool_name or not call_id:
                continue

            try:
                result = execute_tool_call(tool_name, args)
            except Exception as exc:
                result = tool_result_payload("error", f"Falló la herramienta {tool_name}: {exc}")

            if result.get("status") == "confirmation_required":
                confirmation_message = result["message"]
                confirmation_payload = result.get("pending_action")
                break

            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )
            saw_valid_tool_output = True

        if confirmation_message:
            return confirmation_message, confirmation_payload, response

        if not saw_valid_tool_output:
            return "No pude ejecutar ninguna herramienta válida para esta petición.", None, response

        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_output_tokens=400,
        )
        last_response = response
    return final_text, None, response


def execute_pending_confirmation(user_message: str) -> Optional[str]:
    pending = get_pending_action()
    if not pending:
        return None

    if affirmative_response(user_message):
        action_type = pending.get("type")
        if action_type == "delete_student":
            result = perform_delete_student(str(pending.get("student_name", "")))
        elif action_type == "delete_subject":
            result = perform_delete_subject(str(pending.get("student_name", "")), str(pending.get("subject", "")))
        else:
            clear_pending_action()
            return "No pude reconocer la acción pendiente. Intenta de nuevo."

        clear_pending_action()
        return result["message"]

    if negative_response(user_message):
        clear_pending_action()
        return "Operación cancelada."

    return None


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    messages = get_messages()

    if request.method == "POST":
        user_message = request.form.get("user_message", "").strip()
        if user_message:
            messages.append({"role": "user", "content": user_message})

            if is_exit_command(user_message):
                reset_chat_state()
                messages = [{"role": "assistant", "content": "Conversación cerrada. Escribe hola para comenzar otra vez."}]
                save_messages(messages)
                return redirect(url_for("index"))

            if is_restart_command(user_message):
                messages = start_fresh_conversation()
                save_messages(messages)
                return redirect(url_for("index"))

            pending_reply = execute_pending_confirmation(user_message)
            if pending_reply is not None:
                messages.append({"role": "assistant", "content": pending_reply})
                save_messages(messages)
                return redirect(url_for("index"))

            try:
                reply, pending_payload, _response = run_function_calling_turn(user_message, messages[:-1])
                if pending_payload:
                    store_pending_action(pending_payload)
                messages.append({"role": "assistant", "content": reply})
            except RuntimeError as exc:
                error = str(exc)
                if "MongoDB" in error or "Mongo" in error:
                    reply = f"No pude consultar MongoDB: {error}"
                else:
                    reply = f"No pude completar la operación: {error}"
                messages.append({"role": "assistant", "content": reply})
            except Exception as exc:
                error = str(exc)
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"No pude procesar la petición en este momento: {error}",
                    }
                )

            save_messages(messages)
            return redirect(url_for("index"))

    mongo_ok, mongo_status = get_mongo_status()
    capability_hint = (
        "Puedes preguntar por calificaciones, promedios, listas, agregar o modificar registros, "
        "renombrar alumnos o materias y borrar solo con confirmación. Ejemplos: "
        '"promedio de Pedro", "calificación de María en Inglés", '
        '"agrega materia Física a Juan con 9", "lista alumnos con materias y promedios".'
    )

    return render_template(
        "index.html",
        messages=messages,
        error=error,
        last_model=OPENAI_MODEL,
        last_tokens=None,
        last_time=None,
        db_status=mongo_status if mongo_ok else mongo_status,
        capability_hint=capability_hint,
        pending_action=get_pending_action(),
    )


@app.route("/reset", methods=["POST"])
def reset():
    start_fresh_conversation()
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=True, port=port)
