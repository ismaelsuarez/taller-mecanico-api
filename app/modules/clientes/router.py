"""Rutas HTTP de clientes y vehículos (EJ-3): construyen el Unit of Work con una
dependencia, llaman al servicio y devuelven los contratos del módulo.

Las excepciones de dominio las traduce la aplicación en 404/409 (D8): este
archivo no las atrapa. SIN PROTECCIÓN hasta EJ-5 (T-11): acá entra
`requiere_rol` (RECEPCION/ADMIN) y el control del cambio obligatorio.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.database import SesionDep
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


def construir_uow(sesion: SesionDep) -> UnitOfWorkCliente:
    """El UoW se arma con la sesión de la petición y se pasa SIN abrir (B-2)."""
    return UnitOfWorkCliente(sesion)


UowClienteDep = Annotated[UnitOfWorkCliente, Depends(construir_uow)]


@router.post("/clientes", status_code=201, response_model=ClienteLectura)
async def crear_cliente(datos: ClienteCrear, uow: UowClienteDep) -> ClienteLectura:
    return await service.crear_cliente(uow, datos)


@router.get("/clientes/{cliente_id}", response_model=ClienteDetalle)
async def obtener_cliente(cliente_id: int, uow: UowClienteDep) -> ClienteDetalle:
    return await service.obtener_cliente(uow, cliente_id)


@router.post(
    "/clientes/{cliente_id}/vehiculos", status_code=201, response_model=VehiculoLectura
)
async def crear_vehiculo(
    cliente_id: int, datos: VehiculoCrear, uow: UowClienteDep
) -> VehiculoLectura:
    return await service.crear_vehiculo(uow, cliente_id, datos)


@router.delete("/vehiculos/{vehiculo_id}", status_code=204)
async def borrar_vehiculo(vehiculo_id: int, uow: UowClienteDep) -> Response:
    await service.borrar_vehiculo(uow, vehiculo_id)
    return Response(status_code=204)
