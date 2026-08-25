from __future__ import annotations

"""Servidor MCP para la biblioteca.

Las tools de este archivo no tocan el JSON directamente. En su lugar, llaman
a la API REST local, para que la arquitectura se vea en capas:

Llama 3.1 -> MCP -> API REST -> JSON local
"""

from typing import Optional

import httpx
import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp.server import MCPServer

from common import API_BASE_URL, MCP_PORT, build_filters_summary


def _call_api(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
    """Hace una llamada HTTP a la API local de la biblioteca."""

    with httpx.Client(base_url=API_BASE_URL, timeout=20.0) as client:
        response = client.request(method, path, params=params, json=json)
        response.raise_for_status()
        return response.json()


biblioteca_mcp = MCPServer(
    "BibliotecaMCP",
    description="Servidor MCP educativo para una biblioteca local.",
    instructions="Usa las tools para listar, agregar, prestar y devolver libros.",
)


@biblioteca_mcp.tool()
async def listar_libros(
    titulo: Optional[str] = None,
    autor: Optional[str] = None,
    genero: Optional[str] = None,
    estado: Optional[str] = None,
) -> dict:
    """Tool MCP para listar libros con filtros opcionales."""

    try:
        params = build_filters_summary(titulo=titulo, autor=autor, genero=genero, estado=estado)
        return _call_api("GET", "/api/libros", params=params)
    except httpx.HTTPStatusError as exc:
        return {
            "status": "error",
            "message": "No fue posible listar los libros.",
            "detail": exc.response.text,
        }
    except httpx.RequestError as exc:
        return {
            "status": "error",
            "message": "Error de red al consultar la API.",
            "detail": str(exc),
        }


@biblioteca_mcp.tool()
async def agregar_libro(
    titulo: str,
    autor: str,
    anio_publicacion: Optional[int] = None,
    genero: Optional[str] = None,
    sinopsis: Optional[str] = None,
) -> dict:
    """Tool MCP para registrar un nuevo libro."""

    body = {
        "titulo": titulo,
        "autor": autor,
    }
    if anio_publicacion is not None:
        body["anio_publicacion"] = anio_publicacion
    if genero is not None:
        body["genero"] = genero
    if sinopsis is not None:
        body["sinopsis"] = sinopsis

    try:
        return _call_api("POST", "/api/libros", json=body)
    except httpx.HTTPStatusError as exc:
        return {
            "status": "error",
            "message": "No fue posible agregar el libro.",
            "detail": exc.response.text,
        }
    except httpx.RequestError as exc:
        return {
            "status": "error",
            "message": "Error de red al crear el libro.",
            "detail": str(exc),
        }


@biblioteca_mcp.tool()
async def prestar_libro(
    libro_id: Optional[str] = None,
    titulo: Optional[str] = None,
    prestado_a: Optional[str] = None,
) -> dict:
    """Tool MCP para marcar un libro como prestado."""

    body = {
        "libro_id": libro_id,
        "titulo": titulo,
        "prestado_a": prestado_a,
    }

    try:
        return _call_api("POST", "/api/libros/prestar", json=body)
    except httpx.HTTPStatusError as exc:
        return {
            "status": "error",
            "message": "No fue posible prestar el libro.",
            "detail": exc.response.text,
        }
    except httpx.RequestError as exc:
        return {
            "status": "error",
            "message": "Error de red al prestar el libro.",
            "detail": str(exc),
        }


@biblioteca_mcp.tool()
async def devolver_libro(
    libro_id: Optional[str] = None,
    titulo: Optional[str] = None,
) -> dict:
    """Tool MCP para marcar un libro como disponible otra vez."""

    body = {
        "libro_id": libro_id,
        "titulo": titulo,
    }

    try:
        return _call_api("POST", "/api/libros/devolver", json=body)
    except httpx.HTTPStatusError as exc:
        return {
            "status": "error",
            "message": "No fue posible devolver el libro.",
            "detail": exc.response.text,
        }
    except httpx.RequestError as exc:
        return {
            "status": "error",
            "message": "Error de red al devolver el libro.",
            "detail": str(exc),
        }


@biblioteca_mcp.custom_route("/health", methods=["GET"])
async def health(request: Request):
    """Devuelve un estado simple del servidor MCP."""

    return JSONResponse({
        "status": "ok",
        "service": "mcp",
        "api_base_url": API_BASE_URL,
    })


app = biblioteca_mcp.streamable_http_app()


def main() -> None:
    """Punto de entrada para correr solo el servidor MCP."""

    uvicorn.run("mcp_server:app", host="127.0.0.1", port=MCP_PORT, reload=False)


if __name__ == "__main__":
    main()
