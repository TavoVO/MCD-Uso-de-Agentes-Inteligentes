from __future__ import annotations

"""API REST de la biblioteca.

Este archivo solo se encarga de exponer HTTP. Toda la logica real vive en
`common.py` para que el proyecto sea mas facil de estudiar y mantener.
"""

from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from common import (
    API_HOST,
    API_PORT,
    LibroCreate,
    LibroMovimiento,
    add_book,
    build_filters_summary,
    list_books,
    load_library_state,
    return_book,
    loan_book,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan minimo para dejar clara la intencion del proyecto."""

    # No hace falta abrir conexiones externas; solo dejamos el contexto listo.
    yield


app = FastAPI(
    title="BibliotecaAPI",
    version="1.0.0",
    description="API REST local para aprender MCP con una biblioteca simple.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Devuelve un estado simple de la API y el numero de libros guardados."""

    state = load_library_state()
    books = state.get("books", [])
    return {
        "status": "ok",
        "service": "biblioteca-api",
        "books": len(books),
    }


@app.get("/api/libros")
def get_libros(
    titulo: Optional[str] = Query(default=None),
    autor: Optional[str] = Query(default=None),
    genero: Optional[str] = Query(default=None),
    estado: Optional[str] = Query(default=None),
) -> dict:
    """Lista libros aplicando filtros opcionales."""

    try:
        items = list_books(titulo=titulo, autor=autor, genero=genero, estado=estado)
        return {
            "status": "ok",
            "count": len(items),
            "filters": build_filters_summary(titulo=titulo, autor=autor, genero=genero, estado=estado),
            "items": [item.model_dump() for item in items],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/libros", status_code=201)
def post_libro(payload: LibroCreate) -> dict:
    """Agrega un libro nuevo a la biblioteca."""

    try:
        created = add_book(payload)
        return {
            "status": "ok",
            "message": "Libro agregado correctamente",
            "item": created.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/libros/prestar")
def post_prestar(payload: LibroMovimiento) -> dict:
    """Marca un libro como prestado."""

    try:
        updated = loan_book(payload)
        return {
            "status": "ok",
            "message": "Libro prestado correctamente",
            "item": updated.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/libros/devolver")
def post_devolver(payload: LibroMovimiento) -> dict:
    """Marca un libro como disponible otra vez."""

    try:
        updated = return_book(payload)
        return {
            "status": "ok",
            "message": "Libro devuelto correctamente",
            "item": updated.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def main() -> None:
    """Punto de entrada para correr la API desde terminal."""

    uvicorn.run("api:app", host=API_HOST, port=API_PORT, reload=False)


if __name__ == "__main__":
    main()

