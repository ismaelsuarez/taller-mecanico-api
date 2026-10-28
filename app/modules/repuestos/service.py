"""Reglas de negocio del catálogo de repuestos (Repuesto, MovimientoStock,
HistorialPrecio) — EJ-3.

Cada función recibe el UoW y lo abre con `async with` (RT-TX-02); nunca lo
construye (B-2). Los errores son excepciones de dominio que la aplicación
traduce a HTTP (D8): `NoEncontrado` → 404, `EnConflicto` → 409.

El stock sólo cambia por `registrar_movimiento`, el punto único de escritura
(RN-14, T-3): alta con stock inicial y reposición pasan por ahí. El cambio de
precio con su línea de historial ocurre en el mismo bloque del UoW (RN-20,
RT-TX-04). La unicidad de `codigo` entre vigentes la garantiza la base (S-2).
"""

from sqlalchemy.exc import IntegrityError

from app.core.errores import EnConflicto, NoEncontrado
from app.core.paginacion import Pagina, pagina
from app.modules.repuestos.models import Repuesto
from app.modules.repuestos.schemas import (
    MAXIMO_STOCK,
    MovimientoLectura,
    PrecioLectura,
    RepuestoActualizar,
    RepuestoCrear,
    RepuestoLectura,
    RepuestoReponer,
)
from app.modules.repuestos.unit_of_work import UnitOfWorkRepuesto


async def listar_repuestos(
    uow: UnitOfWorkRepuesto, q: str | None, page: int, size: int
) -> Pagina[RepuestoLectura]:
    """Vigentes paginados con búsqueda «contiene» por descripción (RT-PG-05)."""
    async with uow:
        items, total = await uow.repuestos.buscar_vigentes(q, page, size)
    lectura = [RepuestoLectura.model_validate(r, from_attributes=True) for r in items]
    return pagina(lectura, total, page, size)


async def obtener_repuesto(
    uow: UnitOfWorkRepuesto, repuesto_id: int
) -> RepuestoLectura:
    async with uow:
        repuesto = await uow.repuestos.get_by_id(repuesto_id)
        if repuesto is None:
            raise NoEncontrado("Repuesto no encontrado.")
        return RepuestoLectura.model_validate(repuesto, from_attributes=True)


async def crear_repuesto(
    uow: UnitOfWorkRepuesto, datos: RepuestoCrear, usuario_id: int
) -> RepuestoLectura:
    """Alta con stock inicial; el movimiento «Stock inicial» sale del punto único (T-3)."""
    async with uow:
        repuesto = Repuesto(
            codigo=datos.codigo,
            descripcion=datos.descripcion,
            precio=datos.precio,
            stock=0,
        )
        try:
            await uow.repuestos.add(repuesto)
        except IntegrityError:
            raise EnConflicto("Ya existe un repuesto con ese código.") from None
        if datos.stock_inicial > 0:
            await uow.repuestos.registrar_movimiento(
                repuesto, datos.stock_inicial, "Stock inicial", usuario_id
            )
    return RepuestoLectura.model_validate(repuesto, from_attributes=True)


async def actualizar_repuesto(
    uow: UnitOfWorkRepuesto, repuesto_id: int, datos: RepuestoActualizar, usuario_id: int
) -> RepuestoLectura:
    """Precio y descripción en una sola transacción con su historial (RN-20)."""
    async with uow:
        repuesto = await uow.repuestos.get_by_id(repuesto_id)
        if repuesto is None:
            raise NoEncontrado("Repuesto no encontrado.")
        precio_anterior = repuesto.precio
        for campo, valor in datos.model_dump(exclude_unset=True).items():
            setattr(repuesto, campo, valor)
        await uow.repuestos.update(repuesto)
        await uow.precios.add_si_hubo_cambio(
            repuesto, precio_anterior, repuesto.precio, usuario_id
        )
    return RepuestoLectura.model_validate(repuesto, from_attributes=True)


async def borrar_repuesto(uow: UnitOfWorkRepuesto, repuesto_id: int) -> None:
    """204 siempre que esté vigente, aunque esté en órdenes abiertas (DD-21, RT-EQ-02)."""
    async with uow:
        repuesto = await uow.repuestos.get_by_id(repuesto_id)
        if repuesto is None:
            raise NoEncontrado("Repuesto no encontrado.")
        await uow.repuestos.soft_delete(repuesto)


async def reponer_repuesto(
    uow: UnitOfWorkRepuesto, repuesto_id: int, datos: RepuestoReponer, usuario_id: int
) -> RepuestoLectura:
    """`stock += cantidad` y movimiento positivo juntos (RN-14, T-3)."""
    async with uow:
        repuesto = await uow.repuestos.get_by_id(repuesto_id)
        if repuesto is None:
            raise NoEncontrado("Repuesto no encontrado.")
        if repuesto.stock + datos.cantidad > MAXIMO_STOCK:
            raise EnConflicto("La reposición supera el máximo de existencias permitido.")
        await uow.repuestos.registrar_movimiento(
            repuesto, datos.cantidad, datos.motivo, usuario_id
        )
    return RepuestoLectura.model_validate(repuesto, from_attributes=True)


async def listar_movimientos(
    uow: UnitOfWorkRepuesto, repuesto_id: int
) -> list[MovimientoLectura]:
    async with uow:
        if await uow.repuestos.get_by_id(repuesto_id) is None:
            raise NoEncontrado("Repuesto no encontrado.")
        movimientos = await uow.repuestos.get_movimientos(repuesto_id)
    return [
        MovimientoLectura.model_validate(m, from_attributes=True)
        for m in movimientos
    ]


async def listar_precios(
    uow: UnitOfWorkRepuesto, repuesto_id: int
) -> list[PrecioLectura]:
    async with uow:
        if await uow.repuestos.get_by_id(repuesto_id) is None:
            raise NoEncontrado("Repuesto no encontrado.")
        lineas = await uow.repuestos.get_historial_precios(repuesto_id)
    return [PrecioLectura.model_validate(linea, from_attributes=True) for linea in lineas]
