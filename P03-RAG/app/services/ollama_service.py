from __future__ import annotations

from typing import Optional

import httpx

from ..config import EMBEDDING_MODEL, LLM_MODEL, OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL


class OllamaError(RuntimeError):
    """Errores de conectividad o respuesta inválida desde Ollama."""


def _request_json(method: str, path: str, payload: Optional[dict[str, object]] = None) -> dict[str, object]:
    url = f"{OLLAMA_URL.rstrip('/')}{path}"
    try:
        response = httpx.request(
            method,
            url,
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise OllamaError(f"No se pudo comunicar con Ollama en {url}: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()
        if not detail:
            detail = f"HTTP {response.status_code}"
        raise OllamaError(f"Ollama respondió error en {url}: {detail}")

    try:
        data = response.json()
    except ValueError as exc:
        raise OllamaError("Ollama respondió con un formato inválido.") from exc

    if not isinstance(data, dict):
        raise OllamaError("Ollama respondió con datos inesperados.")

    return data


def _extract_embeddings_from_response(data: dict[str, object]) -> list[list[float]]:
    """
    Ollama ha tenido dos formatos para embeddings:
    - /api/embed -> {"embeddings": [[...], [...]]}
    - /api/embeddings -> {"embedding": [...]}
    """
    embeddings = data.get("embeddings")
    if isinstance(embeddings, list):
        normalized: list[list[float]] = []
        for item in embeddings:
            if not isinstance(item, list):
                raise OllamaError("Uno de los embeddings no tiene el formato esperado.")
            normalized.append([float(value) for value in item])
        return normalized

    embedding = data.get("embedding")
    if isinstance(embedding, list):
        return [[float(value) for value in embedding]]

    raise OllamaError("Ollama devolvió embeddings inválidos.")


def _embed_with_modern_endpoint(texts: list[str], model: str) -> list[list[float]]:
    data = _request_json(
        "POST",
        "/api/embed",
        {
            "model": model,
            "input": texts,
        },
    )
    return _extract_embeddings_from_response(data)


def _embed_with_legacy_endpoint(texts: list[str], model: str) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for text in texts:
        data = _request_json(
            "POST",
            "/api/embeddings",
            {
                "model": model,
                "prompt": text,
            },
        )
        item_embeddings = _extract_embeddings_from_response(data)
        if len(item_embeddings) != 1:
            raise OllamaError("Ollama legacy devolvió más de un embedding por texto.")
        embeddings.append(item_embeddings[0])
    return embeddings


def check_ollama() -> dict[str, object]:
    """Verifica si el servidor local de Ollama responde y devuelve sus modelos."""
    try:
        data = _request_json("GET", "/api/tags")
        models = data.get("models", [])
        return {
            "available": True,
            "models": models,
        }
    except OllamaError as exc:
        return {
            "available": False,
            "error": str(exc),
            "models": [],
        }


def embed_texts(texts: list[str], model: str = EMBEDDING_MODEL) -> list[list[float]]:
    """Convierte una lista de textos en embeddings usando el modelo local."""
    if not texts:
        return []

    try:
        embeddings = _embed_with_legacy_endpoint(texts, model)
    except OllamaError as exc:
        # Algunas instalaciones de Ollama exponen /api/embed en lugar de /api/embeddings.
        # Probamos ese formato nuevo si el legacy no está disponible.
        message = str(exc).lower()
        if "404" not in message and "not found" not in message:
            raise
        embeddings = _embed_with_modern_endpoint(texts, model)

    if len(embeddings) != len(texts):
        raise OllamaError("La cantidad de embeddings no coincide con la cantidad de textos.")

    return embeddings


def generate_answer(prompt: str, model: str = LLM_MODEL) -> str:
    """Pide al LLM local que redacte la respuesta final."""
    data = _request_json(
        "POST",
        "/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
            },
        },
    )

    response_text = data.get("response")
    if not isinstance(response_text, str):
        raise OllamaError("Ollama no devolvió un texto de respuesta válido.")
    return response_text.strip()
