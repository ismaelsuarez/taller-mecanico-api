"""Sondas de salud /health/live y /health/ready (EJ-1).

`live` no toca la base: el proceso puede estar vivo con la base caída, y reiniciarlo no la arregla.
`ready` ejecuta SELECT 1 y responde 503 si la base no contesta, sin exponer el error interno.
"""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SesionDep

TIEMPO_MAXIMO_READY = 2.0

logger = logging.getLogger("app.salud")

router = APIRouter(prefix="/health", tags=["salud"])


class EstadoSalud(BaseModel):
    estado: str


class EstadoNoListo(EstadoSalud):
    detalle: str


@router.get("/live")
async def live() -> EstadoSalud:
    return EstadoSalud(estado="vivo")


@router.get("/ready", responses={503: {"model": EstadoNoListo}})
async def ready(sesion: SesionDep) -> EstadoSalud:
    try:
        await asyncio.wait_for(sesion.execute(text("SELECT 1")), timeout=TIEMPO_MAXIMO_READY)
    except (SQLAlchemyError, OSError, TimeoutError) as error:
        # Sólo el tipo: el mensaje del driver puede traer host, usuario o la sentencia.
        logger.warning("La sonda de preparación respondió 503: %s", type(error).__name__)
        cuerpo = EstadoNoListo(estado="no listo", detalle="La base de datos no está disponible en este momento.")
        return JSONResponse(status_code=503, content=cuerpo.model_dump())
    return EstadoSalud(estado="listo")
