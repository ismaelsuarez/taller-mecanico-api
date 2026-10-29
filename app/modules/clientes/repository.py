"""Repositorios de cada entidad del módulo clientes (Cliente y Vehiculo) — EJ-3.

Precarga declarada dentro del método que la necesita (T-10, RT-TX-05): nadie
depende de la carga perezosa. Las órdenes abiertas de un vehículo (RN-16) las
responde `OrdenRepository.tiene_abiertas_del_vehiculo`, no este módulo (EJ-6, D3).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.clientes.models import Cliente, Vehiculo


class ClienteRepository(BaseRepository[Cliente]):
    def __init__(self, sesion) -> None:
        super().__init__(sesion, Cliente)

    async def get_by_id_con_vehiculos(self, id: int) -> Cliente | None:
        """Cliente con sus vehículos vigentes (sin cargar los dados de baja)."""
        resultado = await self.sesion.execute(
            select(Cliente)
            .where(Cliente.id == id)
            .options(
                selectinload(Cliente.vehiculos),
                with_loader_criteria(Vehiculo, Vehiculo.borrado_en.is_(None)),
            )
        )
        return resultado.scalars().first()

    async def get_vehiculos_vigentes_de_usuario(
        self, usuario_id: int, page: int, size: int,
    ) -> tuple[list[Vehiculo], int]:
        """Vehículos vigentes del usuario (RN-17, DD-28): sólo los no dados de baja."""
        base = (
            select(Vehiculo)
            .join(Cliente, Vehiculo.cliente_id == Cliente.id)
            .where(Cliente.usuario_id == usuario_id, Vehiculo.borrado_en.is_(None))
            .order_by(Vehiculo.id)
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


class VehiculoRepository(SoftDeleteRepository[Vehiculo]):
    def __init__(self, sesion) -> None:
        super().__init__(sesion, Vehiculo)
