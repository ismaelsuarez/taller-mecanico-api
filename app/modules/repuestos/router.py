"""Rutas HTTP del catálogo de repuestos (EJ-3): construyen el Unit of Work con
una dependencia, llaman al servicio y devuelven los contratos del módulo.

La matriz RBAC (KB 03) entra por ruta: lecturas del catálogo para personal
(ADMIN, RECEPCION, MECANICO); escrituras, reposición y auditoría sólo para
ADMIN, que firma con el usuario de la sesión (T-4 reemplazado). Sin sesión la
ruta responde 401 y no se escribe nada. Las excepciones de dominio las traduce
la aplicación en 404/409 (D8).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.database import SesionDep
from app.core.dependencies import requiere_rol
from app.core.paginacion import Pagina, ParametrosPagina
from app.modules.repuestos import service
from app.modules.repuestos.schemas import (
    MovimientoLectura,
    PrecioLectura,
    RepuestoActualizar,
    RepuestoCrear,
    RepuestoLectura,
    RepuestoReponer,
)
from app.modules.repuestos.unit_of_work import UnitOfWorkRepuesto
from app.modules.usuarios.schemas import IdentidadLectura

router = APIRouter(tags=["repuestos"])

SoloAdministracion = Annotated[IdentidadLectura, Depends(requiere_rol("ADMIN"))]
RequierePersonal = Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO"))
RequiereAdministracion = Depends(requiere_rol("ADMIN"))


class ParametrosRepuestos(ParametrosPagina):
    """Query params de `GET /repuestos`: paginación + búsqueda `q` (C-16).

    FastAPI valida todos los query contra el modelo `Query` declarado, así que
    `q` va como campo acá y no como parámetro suelto (hereda `extra="forbid"`).
    """

    q: str | None = None


def construir_uow(sesion: SesionDep) -> UnitOfWorkRepuesto:
    """El UoW se arma con la sesión de la petición y se pasa SIN abrir (B-2)."""
    return UnitOfWorkRepuesto(sesion)


UowRepuestoDep = Annotated[UnitOfWorkRepuesto, Depends(construir_uow)]


@router.get(
    "/repuestos",
    response_model=Pagina[RepuestoLectura],
    dependencies=[RequierePersonal],
)
async def listar_repuestos(
    uow: UowRepuestoDep,
    params: Annotated[ParametrosRepuestos, Query()],
) -> Pagina[RepuestoLectura]:
    return await service.listar_repuestos(uow, params.q, params.page, params.size)


@router.post(
    "/repuestos", status_code=201, response_model=RepuestoLectura,
    dependencies=[RequiereAdministracion],
)
async def crear_repuesto(
    datos: RepuestoCrear, uow: UowRepuestoDep, identidad: SoloAdministracion
) -> RepuestoLectura:
    return await service.crear_repuesto(uow, datos, identidad.usuario.id)


@router.get(
    "/repuestos/{repuesto_id}",
    response_model=RepuestoLectura,
    dependencies=[RequierePersonal],
)
async def obtener_repuesto(
    repuesto_id: int, uow: UowRepuestoDep
) -> RepuestoLectura:
    return await service.obtener_repuesto(uow, repuesto_id)


@router.patch(
    "/repuestos/{repuesto_id}", response_model=RepuestoLectura,
    dependencies=[RequiereAdministracion],
)
async def actualizar_repuesto(
    repuesto_id: int,
    datos: RepuestoActualizar,
    uow: UowRepuestoDep,
    identidad: SoloAdministracion,
) -> RepuestoLectura:
    return await service.actualizar_repuesto(
        uow, repuesto_id, datos, identidad.usuario.id
    )


@router.delete(
    "/repuestos/{repuesto_id}", status_code=204, dependencies=[RequiereAdministracion]
)
async def borrar_repuesto(repuesto_id: int, uow: UowRepuestoDep) -> Response:
    await service.borrar_repuesto(uow, repuesto_id)
    return Response(status_code=204)


@router.post(
    "/repuestos/{repuesto_id}/reponer", response_model=RepuestoLectura,
    dependencies=[RequiereAdministracion],
)
async def reponer_repuesto(
    repuesto_id: int,
    datos: RepuestoReponer,
    uow: UowRepuestoDep,
    identidad: SoloAdministracion,
) -> RepuestoLectura:
    return await service.reponer_repuesto(
        uow, repuesto_id, datos, identidad.usuario.id
    )


@router.get(
    "/repuestos/{repuesto_id}/movimientos",
    response_model=list[MovimientoLectura],
    dependencies=[RequiereAdministracion],
)
async def listar_movimientos(
    repuesto_id: int, uow: UowRepuestoDep
) -> list[MovimientoLectura]:
    return await service.listar_movimientos(uow, repuesto_id)


@router.get(
    "/repuestos/{repuesto_id}/precios",
    response_model=list[PrecioLectura],
    dependencies=[RequiereAdministracion],
)
async def listar_precios(
    repuesto_id: int, uow: UowRepuestoDep
) -> list[PrecioLectura]:
    return await service.listar_precios(uow, repuesto_id)
