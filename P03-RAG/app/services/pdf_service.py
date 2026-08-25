from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from ..config import CHUNK_OVERLAP, CHUNK_SIZE


@dataclass
class PageText:
    page_number: int
    text: str


def clean_text(value: str) -> str:
    """Normaliza espacios para que los chunks queden más legibles."""
    value = value.replace("\x00", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def extract_pages(pdf_path: Path) -> list[PageText]:
    """Lee el PDF página por página para mantener el origen de cada fragmento."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {pdf_path}")

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise ValueError("El PDF está corrupto o no se puede leer.") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError("El PDF está encriptado y no se pudo abrir.") from exc

    pages: list[PageText] = []
    for page_number, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        extracted = clean_text(extracted)
        if extracted:
            pages.append(PageText(page_number=page_number, text=extracted))

    if not pages:
        raise ValueError("El PDF no contiene texto útil para indexar.")

    return pages


def build_splitter() -> RecursiveCharacterTextSplitter:
    """Chunking simple con overlap para conservar contexto entre fragmentos."""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def split_pages_into_chunks(pages: list[PageText]) -> list[dict[str, object]]:
    """Convierte cada página en chunks y conserva metadata educativa para explicar el flujo."""
    splitter = build_splitter()
    chunks: list[dict[str, object]] = []

    for page in pages:
        page_chunks = splitter.split_text(page.text)
        for chunk_index, chunk_text in enumerate(page_chunks, start=1):
            cleaned = clean_text(chunk_text)
            if not cleaned:
                continue
            chunks.append(
                {
                    "page_number": page.page_number,
                    "chunk_index": chunk_index,
                    "chunk_text": cleaned,
                }
            )

    if not chunks:
        raise ValueError("No se pudieron generar chunks a partir del PDF.")

    return chunks
