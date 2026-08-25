import os

from dotenv import load_dotenv
from pymongo import MongoClient


BASE_DIR = os.path.dirname(__file__)
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "Calificaciones")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "Calificaciones")

if not MONGODB_URI:
    raise ValueError("No se encontró MONGODB_URI en ToolFunctions/.env")


client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, retryWrites=True)
db = client[MONGODB_DB]
collection = db[MONGODB_COLLECTION]

sample_data = [
    {"student_name": "Pedro", "subject": "Matematicas", "grade": 9.5},
    {"student_name": "Pedro", "subject": "Ingles", "grade": 8.0},
    {"student_name": "Pedro", "subject": "Programacion", "grade": 10.0},
    {"student_name": "Pedro", "subject": "Español", "grade": 9.0},
    {"student_name": "María", "subject": "Matematicas", "grade": 8.3},
    {"student_name": "María", "subject": "Ingles", "grade": 9.1},
    {"student_name": "María", "subject": "Programacion", "grade": 9.8},
    {"student_name": "María", "subject": "Español", "grade": 9.2},
]


def main() -> None:
    print(f"Sincronizando datos de ejemplo en {MONGODB_DB}.{MONGODB_COLLECTION} ...")
    upserts = 0
    for record in sample_data:
        result = collection.update_one(
            {"student_name": record["student_name"], "subject": record["subject"]},
            {"$set": record},
            upsert=True,
        )
        upserts += 1 if result.upserted_id is not None else 0
    total_docs = collection.count_documents({})
    print(f"Registros procesados: {len(sample_data)}")
    print(f"Insertados nuevos: {upserts}")
    print(f"Documentos totales ahora: {total_docs}")


if __name__ == "__main__":
    main()
