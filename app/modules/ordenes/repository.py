"""Repositorios del módulo ordenes: una clase por entidad (EJ-5, T-2/T-8; EJ-6, D3).

Las consultas sobre `orden_trabajo` viven acá y no en servicios ni en otros
módulos (RT-TX-05). La precarga del detalle se declara dentro del método que la
necesita (T-10, B-4): nadie depende de la carga perezosa. Ningún método confirma
la transacción (B-1): sólo `flush`.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.repository import BaseRepository
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import EstadoOrden, HistorialEstadoOrden, ItemOrden, OrdenTrabajo


class OrdenRepository(BaseRepository[OrdenTrabajo]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, OrdenTrabajo)

    async def get_ordenes_de_cliente(
        self, cliente_id: int, page: int, size: int,
    ) -> tuple[list[OrdenTrabajo], int]:
        """Órdenes de los vehículos del cliente, **todas** (DD-28): incluye dados de baja."""
        base = (
            select(OrdenTrabajo)
            .join(Vehiculo, OrdenTrabajo.vehiculo_id == Vehiculo.id)
            .join(Cliente, Vehiculo.cliente_id == Cliente.id)
            .where(Cliente.id == cliente_id)
            .order_by(OrdenTrabajo.id)
        )
        total_resultado = await self.sesion.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = total_resultado.scalar_one()
        if total == 0:
            return [], 0
        pagina_resultado = await self.sesion.execute(
            base.offset((page - 1) * size).limit(size)
        )
        return list(pagina_resultado.scalars().all()), total

    async def get_detalle_con_items_e_historial(self, orden_id: int) -> OrdenTrabajo | None:
        """Orden con vehículo→cliente, ítems→repuesto (también dado de baja, DD-21) e historial.

        `populate_existing` hace que, dentro de un mismo bloque, la relectura refleje
        los ítems y las líneas de historial recién agregados aunque la orden ya esté
        en la sesión. El orden cronológico del historial lo aplica quien lo serializa.
        """
        resultado = await self.sesion.execute(
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == orden_id)
            .options(
                joinedload(OrdenTrabajo.vehiculo).joinedload(Vehiculo.cliente),
                selectinload(OrdenTrabajo.items).joinedload(ItemOrden.repuesto),
                selectinload(OrdenTrabajo.historial_estados),
            )
            .execution_options(populate_existing=True)
        )
        return resultado.scalars().first()

    async def get_cliente_de_usuario(self, usuario_id: int) -> Cliente | None:
        """Ficha de cliente vinculada al usuario; nula si no tiene (SU-11)."""
        resultado = await self.sesion.execute(
            select(Cliente).where(Cliente.usuario_id == usuario_id)
        )
        return resultado.scalars().first()

    async def es_dueno_del_vehiculo(self, usuario_id: int, vehiculo_id: int) -> bool:
        """¿El usuario es el cliente dueño de ese vehículo? (sin ficha → False).

        También vale para vehículos dados de baja (DD-28): el dueño no lo deja de ser.
        """
        resultado = await self.sesion.execute(
            select(Cliente.id)
            .join(Vehiculo, Vehiculo.cliente_id == Cliente.id)
            .where(Vehiculo.id == vehiculo_id, Cliente.usuario_id == usuario_id)
        )
        return resultado.scalar_one_or_none() is not None

    async def tiene_abiertas_del_vehiculo(self, vehiculo_id: int) -> bool:
        """¿Tiene órdenes en un estado que el catálogo no marca como final? (RN-16)."""
        resultado = await self.sesion.execute(
            select(func.count())
            .select_from(OrdenTrabajo)
            .join(EstadoOrden, OrdenTrabajo.estado == EstadoOrden.codigo)
            .where(
                OrdenTrabajo.vehiculo_id == vehiculo_id,
                EstadoOrden.es_final.is_(False),
            )
        )
        return resultado.scalar_one() > 0


class ItemOrdenRepository(BaseRepository[ItemOrden]):
    """Los ítems se agregan sólo dentro del bloque del alta de su orden (no hay endpoint propio)."""

    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, ItemOrden)


class HistorialEstadoOrdenRepository:
    """Historial de sólo agregado (RN-15): no hereda `update` ni `delete`."""

    def __init__(self, sesion: AsyncSession) -> None:
        self.sesion = sesion

    async def add(self, linea: HistorialEstadoOrden) -> HistorialEstadoOrden:
        self.sesion.add(linea)
        await self.sesion.flush()
        return linea


class EstadoOrdenRepository:
    """Catálogo `estado_orden` de sólo lectura (A-5, RN-19): no hereda de `BaseRepository`.

    Su clave es `codigo`, no `id`, y no ofrece escrituras. Las lecturas llegan con la
    tarea 4.1 (`get_all_por_posicion`, `get_by_codigo`).
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self.sesion = sesion
