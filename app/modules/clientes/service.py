"""Reglas de negocio de clientes y vehículos (Cliente y Vehiculo) — EJ-3/EJ-5.

Cada función recibe el UoW y lo abre con `async with` (RT-TX-02); nunca lo
construye (B-2). Los errores son excepciones de dominio que la aplicación
traduce a HTTP (D8): `NoEncontrado` → 404, `EnConflicto` → 409.

La unicidad de `documento` y de `patente` entre vigentes la garantiza la base
(S-2): no hay consulta previa, sólo el `IntegrityError` traducido a 409.
"""

from sqlalchemy.exc import IntegrityError

from app.core.errores import EnConflicto, NoEncontrado
from app.core.paginacion import Pagina, pagina
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.clientes.schemas import (
    ClienteCrear,
    ClienteDetalle,
    ClienteLectura,
    VehiculoCrear,
    VehiculoLectura,
)
from app.modules.clientes.unit_of_work import UnitOfWorkCliente


async def crear_cliente(uow: UnitOfWorkCliente, datos: ClienteCrear) -> ClienteLectura:
    """Alta de cliente (201); el documento repetido es 409 con mensaje propio."""
    async with uow:
        cliente = Cliente(**datos.model_dump())
        try:
            await uow.clientes.add(cliente)
        except IntegrityError:
            raise EnConflicto("Ya existe un cliente con ese documento.") from None
    return ClienteLectura.model_validate(cliente, from_attributes=True)


async def obtener_cliente(uow: UnitOfWorkCliente, cliente_id: int) -> ClienteDetalle:
    """Detalle con los vehículos vigentes; sin la ficha o si está borrada → 404 (DD-22)."""
    async with uow:
        cliente = await uow.clientes.get_by_id_con_vehiculos(cliente_id)
        if cliente is None:
            raise NoEncontrado("Cliente no encontrado.")
        base = ClienteLectura.model_validate(cliente, from_attributes=True)
        vehiculos = [
            VehiculoLectura.model_validate(v, from_attributes=True)
            for v in cliente.vehiculos
        ]
    return ClienteDetalle(**base.model_dump(), vehiculos=vehiculos)


async def crear_vehiculo(
    uow: UnitOfWorkCliente, cliente_id: int, datos: VehiculoCrear
) -> VehiculoLectura:
    """Alta de vehículo para un cliente existente (201); patente repetida → 409."""
    async with uow:
        if await uow.clientes.get_by_id(cliente_id) is None:
            raise NoEncontrado("Cliente no encontrado.")
        vehiculo = Vehiculo(cliente_id=cliente_id, **datos.model_dump())
        try:
            await uow.vehiculos.add(vehiculo)
        except IntegrityError:
            raise EnConflicto("Ya existe un vehículo con esa patente.") from None
    return VehiculoLectura.model_validate(vehiculo, from_attributes=True)


async def borrar_vehiculo(uow: UnitOfWorkCliente, vehiculo_id: int) -> None:
    """Baja lógica (DD-18): el dato queda y la patente vuelve a estar libre (C-19).

    Un vehículo con órdenes no finales no se puede dar de baja → 409 (RN-16);
    el segundo intento de baja es 404 (DD-22).
    """
    async with uow:
        vehiculo = await uow.vehiculos.get_by_id(vehiculo_id)
        if vehiculo is None:
            raise NoEncontrado("Vehículo no encontrado.")
        if await uow.ordenes.tiene_abiertas_del_vehiculo(vehiculo_id):
            raise EnConflicto(
                "El vehículo tiene órdenes de trabajo abiertas y no se puede dar de baja."
            )
        await uow.vehiculos.soft_delete(vehiculo)


async def mis_vehiculos(
    uow: UnitOfWorkCliente, usuario_id: int, page: int, size: int,
) -> Pagina[VehiculoLectura]:
    """Lo propio (RN-17, DD-28): sólo los vehículos vigentes; sin ficha → página vacía (SU-11)."""
    async with uow:
        items, total = await uow.clientes.get_vehiculos_vigentes_de_usuario(
            usuario_id, page, size,
        )
    lectura = [VehiculoLectura.model_validate(v, from_attributes=True) for v in items]
    return pagina(lectura, total, page, size)
