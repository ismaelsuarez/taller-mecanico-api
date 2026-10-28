"""Repositorio mínimo del módulo ordenes para `/mis-ordenes` (EJ-5, T-2/T-8).

EJ-6 completa la jerarquía (`get_by_id_including_deleted`, precargas del
detalle, catálogo de sólo lectura). Acá sólo se pagina lo propio del cliente.
"""

from sqlalchemy import func, select

from app.core.repository import BaseRepository
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import OrdenTrabajo


class OrdenRepository(BaseRepository[OrdenTrabajo]):
    def __init__(self, sesion) -> None:
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

    async def get_cliente_de_usuario(self, usuario_id: int) -> Cliente | None:
        """Ficha de cliente vinculada al usuario; nula si no tiene (SU-11)."""
        resultado = await self.sesion.execute(
            select(Cliente).where(Cliente.usuario_id == usuario_id)
        )
        return resultado.scalars().first()
