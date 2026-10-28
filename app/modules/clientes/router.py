"""Rutas HTTP de clientes y vehículos (EJ-3): construyen el Unit of Work con una
dependencia, llaman al servicio y devuelven los contratos del módulo.

La matriz RBAC (KB 03) entra por ruta: ADMIN y RECEPCION (D2) sobre el CRUD;
`/mis-vehiculos` sólo pide sesión (RN-17). Sin sesión la ruta responde 401 y no
se escribe nada. Las excepciones de dominio las traduce la aplicación en
404/409 (D8): este archivo no las atrapa.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.database import SesionDep
from app.core.dependencies import UsuarioActualDep, requiere_rol
from app.core.paginacion import Pagina, ParametrosPagina
from app.modules.clientes import service
from app.modules.clientes.schemas import (
    ClienteCrear,
    ClienteDetalle,
    ClienteLectura,
    VehiculoCrear,
    VehiculoLectura,
)
from app.modules.clientes.unit_of_work import UnitOfWorkCliente

router = APIRouter(tags=["clientes"])

RequierePersonalClientes = Depends(requiere_rol("ADMIN", "RECEPCION"))


def construir_uow(sesion: SesionDep) -> UnitOfWorkCliente:
    """El UoW se arma con la sesión de la petición y se pasa SIN abrir (B-2)."""
    return UnitOfWorkCliente(sesion)


UowClienteDep = Annotated[UnitOfWorkCliente, Depends(construir_uow)]


@router.post(
    "/clientes", status_code=201, response_model=ClienteLectura,
    dependencies=[RequierePersonalClientes],
)
async def crear_cliente(datos: ClienteCrear, uow: UowClienteDep) -> ClienteLectura:
    return await service.crear_cliente(uow, datos)


@router.get(
    "/clientes/{cliente_id}", response_model=ClienteDetalle,
    dependencies=[RequierePersonalClientes],
)
async def obtener_cliente(cliente_id: int, uow: UowClienteDep) -> ClienteDetalle:
    return await service.obtener_cliente(uow, cliente_id)


@router.post(
    "/clientes/{cliente_id}/vehiculos", status_code=201, response_model=VehiculoLectura,
    dependencies=[RequierePersonalClientes],
)
async def crear_vehiculo(
    cliente_id: int, datos: VehiculoCrear, uow: UowClienteDep
) -> VehiculoLectura:
    return await service.crear_vehiculo(uow, cliente_id, datos)


@router.delete(
    "/vehiculos/{vehiculo_id}", status_code=204,
    dependencies=[RequierePersonalClientes],
)
async def borrar_vehiculo(vehiculo_id: int, uow: UowClienteDep) -> Response:
    await service.borrar_vehiculo(uow, vehiculo_id)
    return Response(status_code=204)


@router.get(
    "/mis-vehiculos", response_model=Pagina[VehiculoLectura],
    summary="Vehículos vigentes del usuario autenticado (RN-17)",
)
async def obtener_mis_vehiculos(
    uow: UowClienteDep,
    identidad: UsuarioActualDep,
    params: Annotated[ParametrosPagina, Query()],
) -> Pagina[VehiculoLectura]:
    return await service.mis_vehiculos(uow, identidad.usuario.id, params.page, params.size)
