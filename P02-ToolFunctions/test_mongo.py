import argparse
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError


BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "Calificaciones")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "Calificaciones")


def build_client() -> MongoClient:
    return MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        retryWrites=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba de humo para la colección de calificaciones.")
    parser.add_argument("--student", help="Nombre del alumno a consultar de forma opcional.")
    args = parser.parse_args()

    if not MONGODB_URI:
        print("Falta MONGODB_URI en ToolFunctions/.env")
        return 1

    try:
        client = build_client()
        print("Conectando a MongoDB...")
        print(client.admin.command("ping"))

        db = client[MONGODB_DB]
        collection = db[MONGODB_COLLECTION]

        total_docs = collection.count_documents({})
        print(f"Base: {MONGODB_DB}.{MONGODB_COLLECTION}")
        print(f"Documentos totales: {total_docs}")

        sample = collection.find_one({}, {"_id": 0, "student_name": 1, "subject": 1, "grade": 1})
        print("Documento de ejemplo:")
        print(sample)

        distinct_students = sorted(
            value for value in collection.distinct("student_name") if isinstance(value, str) and value.strip()
        )
        distinct_subjects = sorted(
            value for value in collection.distinct("subject") if isinstance(value, str) and value.strip()
        )
        print(f"Alumnos detectados: {', '.join(distinct_students) if distinct_students else 'ninguno'}")
        print(f"Materias detectadas: {', '.join(distinct_subjects) if distinct_subjects else 'ninguna'}")

        if args.student:
            docs = list(
                collection.find(
                    {"student_name": {"$regex": f"^{args.student}$", "$options": "i"}},
                    {"_id": 0, "student_name": 1, "subject": 1, "grade": 1},
                )
            )
            print(f"Registros encontrados para {args.student}: {len(docs)}")
            for doc in docs:
                print(doc)

        return 0
    except PyMongoError as exc:
        print(f"Error de MongoDB: {exc}")
        return 2
    except Exception as exc:
        print(f"Error inesperado: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
