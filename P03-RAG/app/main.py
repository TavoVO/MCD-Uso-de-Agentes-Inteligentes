from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import BASE_DIR, EMBEDDING_MODEL, LLM_MODEL, OLLAMA_URL, TOP_K, UPLOAD_DIR
from .db import Base, SessionLocal, engine, ensure_vector_extension, session_scope
from .models import Document, Upload
from .schemas import (
    ChatRequest,
    ChatResponse,
    DeleteUploadResponse,
    HealthResponse,
    SourceChunk,
    UploadCreateResponse,
    UploadResponse,
)
from .services.ollama_service import OllamaError, check_ollama
from .services.rag_service import answer_question, get_completed_upload, index_pdf_upload, mark_upload_failed

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG PDF Local",
    description="Proyecto escolar para aprender Retrieval-Augmented Generation con PDF + PostgreSQL + Ollama.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")


def ensure_storage_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def init_database() -> None:
    """
    En un proyecto escolar queremos que el código explique el flujo,
    no que dependa de demasiadas herramientas externas.
    Por eso intentamos crear la extensión y las tablas al arrancar.
    """
    try:
        ensure_vector_extension()
    except Exception as exc:
        logger.warning("No se pudo crear la extensión vector automáticamente: %s", exc)

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.error("No se pudieron crear las tablas de la base de datos: %s", exc)
        # Dejamos que la app siga levantando para que /health pueda reportar el problema.


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_upload(upload: Upload) -> UploadResponse:
    return UploadResponse.model_validate(upload)


def safe_filename(original_name: str) -> str:
    name = original_name.strip().replace(" ", "_")
    name = "".join(char for char in name if char.isalnum() or char in {"_", "-", "."})
    return name or "upload.pdf"


def save_upload_file(upload_file: UploadFile) -> tuple[str, str, int]:
    """
    Guardamos el PDF en disco solo para poder procesarlo en background.
    El conocimiento persistente real queda en PostgreSQL.
    """
    original_name = upload_file.filename or "documento.pdf"
    stored_name = f"{uuid4().hex}_{safe_filename(original_name)}"
    stored_path = UPLOAD_DIR / stored_name

    file_size = 0
    with stored_path.open("wb") as buffer:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            file_size += len(chunk)
            buffer.write(chunk)

    if file_size == 0:
        stored_path.unlink(missing_ok=True)
        raise ValueError("El archivo PDF está vacío.")

    return original_name, stored_name, file_size


def process_upload_job(upload_id: int, stored_path: str) -> None:
    """
    El trabajo de indexación corre en segundo plano para que la UI pueda mostrar estado.
    """
    pdf_path = Path(stored_path)
    with session_scope() as session:
        upload = session.get(Upload, upload_id)
        if upload is None:
            return

        try:
            index_pdf_upload(session, upload, pdf_path)
        except Exception as exc:
            session.rollback()
            with session_scope() as failed_session:
                failed_upload = failed_session.get(Upload, upload_id)
                if failed_upload is not None:
                    mark_upload_failed(failed_session, failed_upload, str(exc))
            logger.exception("Falló el procesamiento del PDF upload_id=%s", upload_id)


@app.on_event("startup")
def on_startup() -> None:
    ensure_storage_dirs()
    init_database()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_status = "ok"
    ollama_status = check_ollama()

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    ollama_text = "ok" if ollama_status.get("available") else f"error: {ollama_status.get('error', 'desconocido')}"
    return HealthResponse(
        status="ok" if db_status == "ok" and ollama_status.get("available") else "degraded",
        database=db_status,
        ollama=ollama_text,
        llm_model=LLM_MODEL,
        embedding_model=EMBEDDING_MODEL,
    )


@app.post("/api/uploads", response_model=UploadCreateResponse)
def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadCreateResponse:
    if file.content_type not in {"application/pdf", "application/x-pdf"} and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF.")

    try:
        original_name, stored_name, file_size = save_upload_file(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    upload = Upload(
        original_filename=original_name,
        stored_filename=stored_name,
        stored_path=str(UPLOAD_DIR / stored_name),
        file_size=file_size,
        status="processing",
    )
    try:
        db.add(upload)
        db.commit()
        db.refresh(upload)
    except SQLAlchemyError as exc:
        db.rollback()
        Path(UPLOAD_DIR / stored_name).unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=f"No se pudo guardar el upload en PostgreSQL: {exc}") from exc

    background_tasks.add_task(process_upload_job, upload.id, upload.stored_path)

    return UploadCreateResponse(
        upload_id=upload.id,
        status=upload.status,
        message="El PDF se recibió correctamente y ya está siendo procesado.",
    )


@app.get("/api/uploads/{upload_id}", response_model=UploadResponse)
def get_upload(upload_id: int, db: Session = Depends(get_db)) -> UploadResponse:
    try:
        upload = db.get(Upload, upload_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Error de base de datos: {exc}") from exc
    if upload is None:
        raise HTTPException(status_code=404, detail="No existe ese upload.")
    return serialize_upload(upload)


@app.delete("/api/uploads/{upload_id}", response_model=DeleteUploadResponse)
def delete_upload(upload_id: int, db: Session = Depends(get_db)) -> DeleteUploadResponse:
    """
    Borramos el upload y sus chunks para que el usuario pueda empezar de cero.
    Esto es útil después de un fallo, pero también sirve como botón de limpieza general.
    """
    try:
        upload = db.get(Upload, upload_id)
        if upload is None:
            raise HTTPException(status_code=404, detail="No existe ese upload.")

        stored_path = Path(upload.stored_path)
        db.delete(upload)
        db.commit()
        stored_path.unlink(missing_ok=True)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"No se pudo eliminar el upload: {exc}") from exc

    return DeleteUploadResponse(
        upload_id=upload_id,
        message="El estado anterior fue eliminado. Ya puedes subir un PDF nuevo.",
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    try:
        upload = get_completed_upload(db, request.upload_id)
        payload = answer_question(db, upload.id, request.question, top_k=request.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Error de base de datos: {exc}") from exc

    sources = [SourceChunk(**source) for source in payload["sources"]]
    return ChatResponse(
        answer=str(payload["answer"]),
        upload_id=upload.id,
        model=LLM_MODEL,
        sources=sources,
    )


@app.get("/api/uploads/{upload_id}/documents")
def list_documents(upload_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    upload = db.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="No existe ese upload.")

    stmt = select(Document).where(Document.upload_id == upload_id).order_by(Document.page_number, Document.chunk_index)
    docs = db.execute(stmt).scalars().all()
    return {
        "upload_id": upload_id,
        "count": len(docs),
        "documents": [
            {
                "id": doc.id,
                "page_number": doc.page_number,
                "chunk_index": doc.chunk_index,
                "chunk_text": doc.chunk_text,
            }
            for doc in docs
        ],
    }
