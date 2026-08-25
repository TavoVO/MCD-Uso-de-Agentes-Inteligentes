from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UploadResponse(BaseModel):
    id: int
    original_filename: str
    stored_filename: str
    status: str
    page_count: int
    chunk_count: int
    error_message: Optional[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UploadCreateResponse(BaseModel):
    upload_id: int
    status: str
    message: str


class DeleteUploadResponse(BaseModel):
    upload_id: int
    message: str


class SourceChunk(BaseModel):
    id: int
    file_name: str
    page_number: int
    chunk_index: int
    distance: float
    chunk_text: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    upload_id: Optional[int] = None
    top_k: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    upload_id: int
    model: str
    sources: list[SourceChunk]


class HealthResponse(BaseModel):
    status: str
    database: str
    ollama: str
    llm_model: str
    embedding_model: str
