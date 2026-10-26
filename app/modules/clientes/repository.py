"""Repositorios de cada entidad del módulo clientes (Cliente y Vehiculo) — EJ-3.

Precarga declarada dentro del método que la necesita (T-10, RT-TX-05): nadie
depende de la carga perezosa. `VehiculoRepository.tiene_ordenes_abiertas` consulta
`orden_trabajo` con `es_final = false` del catálogo en una sola consulta (D7);
cuando exista el repositorio de órdenes (EJ-6) se reemplaza por él.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo


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


class VehiculoRepository(SoftDeleteRepository[Vehiculo]):
    def __init__(self, sesion) -> None:
        super().__init__(sesion, Vehiculo)

    async def tiene_ordenes_abiertas(self, vehiculo_id: int) -> bool:
        """¿Tiene órdenes en un estado que el catálogo no marca como final? (RN-16, D7)."""
        consulta = (
            select(func.count())
            .select_from(OrdenTrabajo)
            .join(EstadoOrden, OrdenTrabajo.estado == EstadoOrden.codigo)
            .where(
                OrdenTrabajo.vehiculo_id == vehiculo_id,
                EstadoOrden.es_final.is_(False),
            )
        )
        resultado = await self.sesion.execute(consulta)
        return resultado.scalar_one() > 0
