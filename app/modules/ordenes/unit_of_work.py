"""Unit of Work del módulo ordenes (EJ-5, T-2; completado en EJ-6, D4).

El router lo construye con una dependencia y lo pasa sin abrir; el servicio lo
abre con `async with` (RT-TX-02). Compone con la misma sesión los repositorios que
necesitan el alta, el detalle y las transiciones: órdenes, ítems, historial,
catálogo de estados, vehículos y repuestos.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import VehiculoRepository
from app.modules.ordenes.repository import (
    EstadoOrdenRepository,
    HistorialEstadoOrdenRepository,
    ItemOrdenRepository,
    OrdenRepository,
)
from app.modules.repuestos.repository import RepuestoRepository


class UnitOfWorkOrden(UnitOfWork):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion)
        self.ordenes = OrdenRepository(sesion)
        self.items = ItemOrdenRepository(sesion)
        self.historial = HistorialEstadoOrdenRepository(sesion)
        self.estados = EstadoOrdenRepository(sesion)
        self.vehiculos = VehiculoRepository(sesion)
        self.repuestos = RepuestoRepository(sesion)
