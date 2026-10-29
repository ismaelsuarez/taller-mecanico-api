"""Ruta mínima del módulo ordenes para EJ-5: `/mis-ordenes` (T-8, RN-17).

Sólo pide sesión (la aporta el grupo protegido de `main.py`); no exige rol.
EJ-6 agrega el resto de rutas con `requiere_rol` según la matriz RBAC.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import SesionDep
from app.core.dependencies import UsuarioActualDep
from app.core.paginacion import Pagina, ParametrosPagina
from app.modules.ordenes import service
from app.modules.ordenes.schemas import EstadoOrdenLectura, OrdenResumenLectura
from app.modules.ordenes.unit_of_work import UnitOfWorkOrden

router = APIRouter(tags=["órdenes"])


def construir_uow(sesion: SesionDep) -> UnitOfWorkOrden:
    """El UoW se arma con la sesión de la petición y se pasa SIN abrir (B-2)."""
    return UnitOfWorkOrden(sesion)


UowOrdenDep = Annotated[UnitOfWorkOrden, Depends(construir_uow)]


@router.get(
    "/mis-ordenes", response_model=Pagina[OrdenResumenLectura],
    summary="Órdenes de los vehículos del usuario autenticado (RN-17)",
)
async def obtener_mis_ordenes(
    uow: UowOrdenDep,
    identidad: UsuarioActualDep,
    params: Annotated[ParametrosPagina, Query()],
) -> Pagina[OrdenResumenLectura]:
    return await service.mis_ordenes(uow, identidad.usuario.id, params.page, params.size)


@router.get(
    "/estados-orden", response_model=list[EstadoOrdenLectura],
    summary="Catálogo de estados de una orden, por posición (C-17, sólo lectura)",
)
async def obtener_estados_orden(
    uow: UowOrdenDep,
    _identidad: UsuarioActualDep,
) -> list[EstadoOrdenLectura]:
    """Cualquier usuario autenticado; la API no ofrece escrituras sobre el catálogo (A-5)."""
    return await service.listar_estados(uow)
