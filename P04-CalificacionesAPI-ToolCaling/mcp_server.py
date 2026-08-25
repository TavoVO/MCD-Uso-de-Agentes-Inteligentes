from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

from common import API_BASE_URL, MCP_PORT, build_filters_summary


def _call_api(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
    """Hace una peticion HTTP a la API REST local."""
    # El MCP no toca Mongo directo: delega todo a la API REST.
    with httpx.Client(base_url=API_BASE_URL, timeout=20.0) as client:
        response = client.request(method, path, params=params, json=json)
        response.raise_for_status()
        return response.json()


calificaciones_mcp = FastMCP(
    "CalificacionesAPI",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@calificaciones_mcp.tool()
async def consultar_calificaciones(
    alumno: Optional[str] = None,
    materia: Optional[str] = None,
    periodo: Optional[str] = None,
) -> dict:
    """Tool MCP para consultar calificaciones."""
    try:
        # Tool para consultar calificaciones via HTTP.
        return _call_api("GET", "/api/calificaciones", params=build_filters_summary(alumno, materia, periodo))
    except httpx.HTTPStatusError as exc:
        return {"status": "error", "message": "No fue posible consultar calificaciones.", "detail": exc.response.text}
    except httpx.RequestError as exc:
        return {"status": "error", "message": "Error de red al consultar la API.", "detail": str(exc)}


@calificaciones_mcp.tool()
async def asignar_calificacion(
    alumno: str,
    materia: str,
    calificacion: float,
    fecha: Optional[str] = None,
    periodo: Optional[str] = None,
) -> dict:
    """Tool MCP para registrar una nueva calificacion."""
    body = {"alumno": alumno, "materia": materia, "calificacion": calificacion}
    if fecha is not None:
        body["fecha"] = fecha
    if periodo is not None:
        body["periodo"] = periodo
    try:
        # Tool para registrar una calificacion via HTTP.
        return _call_api("POST", "/api/calificaciones", json=body)
    except httpx.HTTPStatusError as exc:
        return {"status": "error", "message": "No fue posible crear la calificacion.", "detail": exc.response.text}
    except httpx.RequestError as exc:
        return {"status": "error", "message": "Error de red al crear la calificacion.", "detail": str(exc)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida minimo del servidor MCP."""
    async with calificaciones_mcp.session_manager.run():
        yield


app = FastAPI(
    title="CalificacionesMCP",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/mcp", calificaciones_mcp.streamable_http_app())


@app.get("/health")
def health() -> dict:
    """Devuelve un estado simple del servicio MCP."""
    # Salud local del servicio MCP, independiente de Mongo.
    return {"status": "ok", "service": "mcp"}


def main() -> None:
    """Arranca el servidor MCP con Uvicorn."""
    # Punto de entrada para correr solo el servidor MCP.
    uvicorn.run("mcp_server:app", host="127.0.0.1", port=MCP_PORT, reload=False)


if __name__ == "__main__":
    main()
