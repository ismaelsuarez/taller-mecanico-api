"""Rutas del módulo ordenes: `/mis-ordenes` (EJ-5), `/estados-orden`, alta, listado, detalle,
iniciar, terminar y cancelar (EJ-6).

Todas pertenecen al grupo protegido de `main.py` (401 sin sesión, 403 con cambio de contraseña
pendiente). El rol por ruta (`requiere_rol`) sólo se exige donde la matriz RBAC lo pide; el
permiso del detalle depende de la orden y lo decide el servicio (D2).
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.core.database import SesionDep
from app.core.dependencies import UsuarioActualDep, requiere_rol
from app.core.paginacion import Pagina, ParametrosPagina
from app.modules.ordenes import service
from app.modules.ordenes.avisos import avisar_cliente
from app.modules.ordenes.schemas import (
    EstadoOrdenLectura,
    OrdenCrear,
    OrdenDetalle,
    OrdenResumenLectura,
    ParametrosOrdenes,
)
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


@router.post(
    "/ordenes", status_code=201, response_model=OrdenDetalle,
    dependencies=[Depends(requiere_rol("RECEPCION", "ADMIN"))],
    summary="Alta de una orden con precios copiados y total del servidor (C-10, RN-10)",
)
async def crear_orden(
    datos: OrdenCrear,
    uow: UowOrdenDep,
    identidad: UsuarioActualDep,
) -> OrdenDetalle:
    return await service.crear_orden(uow, datos, identidad.usuario.id)


@router.get(
    "/ordenes", response_model=Pagina[OrdenResumenLectura],
    dependencies=[Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO"))],
    summary="Listado de órdenes del personal, filtrable por estado (C-17)",
)
async def listar_ordenes(
    uow: UowOrdenDep,
    params: Annotated[ParametrosOrdenes, Query()],
) -> Pagina[OrdenResumenLectura]:
    return await service.listar_ordenes(uow, params.estado, params.page, params.size)


@router.get(
    "/ordenes/{orden_id}", response_model=OrdenDetalle,
    summary="Detalle de una orden: el personal ve cualquiera, el dueño la suya (C-06)",
)
async def obtener_orden(
    orden_id: int,
    uow: UowOrdenDep,
    identidad: UsuarioActualDep,
) -> OrdenDetalle:
    return await service.obtener_orden(uow, identidad, orden_id)


@router.post(
    "/ordenes/{orden_id}/iniciar", response_model=OrdenDetalle,
    dependencies=[Depends(requiere_rol("MECANICO"))],
    summary="Un mecánico toma una orden pendiente (RN-11)",
)
async def iniciar_orden(
    orden_id: int,
    uow: UowOrdenDep,
    identidad: UsuarioActualDep,
) -> OrdenDetalle:
    return await service.iniciar_orden(uow, identidad, orden_id)


@router.post(
    "/ordenes/{orden_id}/cancelar", response_model=OrdenDetalle,
    summary="Cancelación de una orden pendiente: recepción, admin o el dueño (RN-12, C-13)",
)
async def cancelar_orden(
    orden_id: int,
    uow: UowOrdenDep,
    identidad: UsuarioActualDep,
) -> OrdenDetalle:
    """Sin `requiere_rol` (nota de la consigna): el permiso depende de la orden y lo decide el servicio."""
    return await service.cancelar_orden(uow, identidad, orden_id)


@router.post(
    "/ordenes/{orden_id}/terminar", response_model=OrdenDetalle,
    dependencies=[Depends(requiere_rol("MECANICO", "ADMIN"))],
    summary="Termina una orden en reparación y descuenta el stock, todo o nada (RN-13, C-11, C-12)",
)
async def terminar_orden(
    orden_id: int,
    uow: UowOrdenDep,
    identidad: UsuarioActualDep,
    background_tasks: BackgroundTasks,
) -> OrdenDetalle:
    """El rol lo pide la ruta; que sea el asignado (o un ADMIN) lo decide el servicio con la orden."""
    detalle = await service.terminar_orden(uow, identidad, orden_id)
    # Sólo si el servicio devolvió: un 404, 403 o 409 sale por excepción antes de esta línea (T-9).
    # Starlette ejecuta la tarea recién después de enviar la respuesta (RT-TX-07).
    background_tasks.add_task(avisar_cliente, orden_id, detalle.cliente)
    return detalle
