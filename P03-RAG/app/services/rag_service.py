from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import EMBEDDING_MODEL, LLM_MODEL, TOP_K
from ..models import Document, Upload
from .ollama_service import embed_texts, generate_answer
from .pdf_service import extract_pages, split_pages_into_chunks

logger = logging.getLogger(__name__)


def index_pdf_upload(session: Session, upload: Upload, pdf_path: Path) -> None:
    """
    Paso 1 y 2 del RAG:
    - extraer texto
    - dividir en chunks
    - generar embeddings
    - guardar todo en PostgreSQL
    """
    upload.status = "processing"
    upload.error_message = None
    session.flush()

    pages = extract_pages(pdf_path)
    chunks = split_pages_into_chunks(pages)
    chunk_texts = [chunk["chunk_text"] for chunk in chunks]

    embeddings = embed_texts([str(text) for text in chunk_texts], model=EMBEDDING_MODEL)
    if len(embeddings) != len(chunks):
        raise ValueError("La cantidad de embeddings no coincide con la cantidad de chunks.")

    documents: list[Document] = []
    for chunk_info, embedding in zip(chunks, embeddings):
        documents.append(
            Document(
                upload_id=upload.id,
                file_name=upload.original_filename,
                page_number=int(chunk_info["page_number"]),
                chunk_index=int(chunk_info["chunk_index"]),
                chunk_text=str(chunk_info["chunk_text"]),
                embedding=embedding,
            )
        )

    session.add_all(documents)
    upload.page_count = len(pages)
    upload.chunk_count = len(documents)
    upload.status = "completed"
    logger.info("PDF indexado correctamente: upload_id=%s, chunks=%s", upload.id, len(documents))


def mark_upload_failed(session: Session, upload: Upload, error_message: str) -> None:
    upload.status = "failed"
    upload.error_message = error_message[:1000]
    session.flush()


def get_completed_upload(session: Session, upload_id: Optional[int]) -> Upload:
    if upload_id is None:
        stmt = select(Upload).where(Upload.status == "completed").order_by(Upload.id.desc())
        upload = session.execute(stmt).scalars().first()
        if upload is None:
            raise ValueError("Todavía no hay ningún PDF procesado con éxito.")
        return upload

    upload = session.get(Upload, upload_id)
    if upload is None:
        raise ValueError("No existe un upload con ese identificador.")
    if upload.status != "completed":
        raise ValueError(f"El PDF todavía no está listo. Estado actual: {upload.status}.")
    return upload


def retrieve_relevant_chunks(session: Session, upload_id: int, question: str, top_k: Optional[int] = None) -> list[dict[str, object]]:
    """
    Paso 3 del RAG:
    - convertir la pregunta en embedding
    - comparar contra los embeddings guardados
    - traer los fragmentos más parecidos
    """
    question_embedding = embed_texts([question], model=EMBEDDING_MODEL)[0]
    limit = top_k or TOP_K

    distance_expr = Document.embedding.cosine_distance(question_embedding)
    stmt = (
        select(Document, distance_expr.label("distance"))
        .where(Document.upload_id == upload_id)
        .order_by(distance_expr)
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    sources: list[dict[str, object]] = []
    for document, distance in rows:
        sources.append(
            {
                "id": document.id,
                "file_name": document.file_name,
                "page_number": document.page_number,
                "chunk_index": document.chunk_index,
                "distance": float(distance),
                "chunk_text": document.chunk_text,
            }
        )

    if not sources:
        raise ValueError("No se encontraron fragmentos relevantes para responder.")

    return sources


def build_prompt(question: str, sources: list[dict[str, object]]) -> str:
    """
    Paso 4 del RAG:
    - mezclar pregunta + contexto recuperado
    - dejar reglas claras para que el LLM responda solo con evidencia
    """
    context_blocks = []
    for index, source in enumerate(sources, start=1):
        context_blocks.append(
            "\n".join(
                [
                    f"[Fuente {index}]",
                    f"Archivo: {source['file_name']}",
                    f"Página: {source['page_number']}",
                    f"Chunk: {source['chunk_index']}",
                    f"Distancia: {source['distance']:.4f}",
                    "Texto:",
                    str(source["chunk_text"]),
                ]
            )
        )

    context_text = "\n\n".join(context_blocks)

    return f"""
Eres un asistente escolar para explicar contenido de un PDF.
Responde en español y de forma clara.

Reglas:
- Usa únicamente el contexto proporcionado.
- Si el contexto no alcanza para responder, dilo explícitamente.
- No inventes datos.
- Si te sirve, menciona qué fuentes apoyan la respuesta.

Pregunta del usuario:
{question}

Contexto recuperado:
{context_text}

Respuesta:
""".strip()


def answer_question(session: Session, upload_id: int, question: str, top_k: Optional[int] = None) -> dict[str, object]:
    """
    Paso 5 del RAG:
    - recuperar chunks
    - construir prompt
    - generar respuesta final con el LLM local
    """
    sources = retrieve_relevant_chunks(session, upload_id, question, top_k=top_k)
    prompt = build_prompt(question, sources)
    answer = generate_answer(prompt, model=LLM_MODEL)
    return {
        "answer": answer,
        "sources": sources,
    }
