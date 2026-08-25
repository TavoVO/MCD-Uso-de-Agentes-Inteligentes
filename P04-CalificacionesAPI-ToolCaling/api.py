from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from common import (
    API_HOST,
    API_PORT,
    CalificacionCreate,
    build_filters_summary,
    create_calificacion,
    is_mongo_error,
    list_calificaciones,
    ping_mongo,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida minimo de la API REST."""
    yield


app = FastAPI(
    title="CalificacionesAPI",
    version="1.0.0",
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
    """Expone el estado de conexion hacia MongoDB."""
    # Endpoint de salud para comprobar que la API ve a Mongo.
    try:
        ping_mongo()
        return {"status": "ok", "mongo": "connected"}
    except Exception as exc:
        return {"status": "error", "mongo": "disconnected", "detail": str(exc)}


@app.get("/api/calificaciones")
def get_calificaciones(
    alumno: Optional[str] = Query(default=None),
    materia: Optional[str] = Query(default=None),
    periodo: Optional[str] = Query(default=None),
) -> dict:
    """Devuelve calificaciones filtradas por alumno, materia o periodo."""
    try:
        # La API responde con el formato que luego consume el chat de terminal.
        items = list_calificaciones(alumno=alumno, materia=materia, periodo=periodo)
        return {
            "status": "ok",
            "count": len(items),
            "filters": build_filters_summary(alumno, materia, periodo),
            "items": [item.model_dump() for item in items],
        }
    except Exception as exc:
        if is_mongo_error(exc):
            raise HTTPException(status_code=503, detail=f"MongoDB no disponible: {exc}") from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/calificaciones", status_code=201)
def post_calificacion(payload: CalificacionCreate) -> dict:
    """Crea una nueva calificacion a partir del body recibido."""
    try:
        # Inserta una nueva calificacion y devuelve el documento creado.
        created = create_calificacion(payload)
        return {"status": "ok", "message": "Calificacion creada correctamente", "item": created.model_dump()}
    except Exception as exc:
        if is_mongo_error(exc):
            raise HTTPException(status_code=503, detail=f"MongoDB no disponible: {exc}") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def main() -> None:
    """Arranca la API REST con Uvicorn."""
    # Punto de entrada para correr solo la API REST.
    uvicorn.run("api:app", host=API_HOST, port=API_PORT, reload=False)


if __name__ == "__main__":
    main()
