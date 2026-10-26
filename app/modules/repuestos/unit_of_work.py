"""Unit of Work del módulo repuestos (Repuesto, MovimientoStock y HistorialPrecio) — EJ-3 (T-2).

El router lo construye con una dependencia y lo pasa sin abrir; el servicio lo
abre con `async with` (RT-TX-02). El cambio de precio con su línea de historial
(RN-20) ocurre en un solo bloque de este UoW (RT-TX-04).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.repuestos.repository import (
    HistorialPrecioRepository,
    MovimientoStockRepository,
    RepuestoRepository,
)


class UnitOfWorkRepuesto(UnitOfWork):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion)
        self.repuestos = RepuestoRepository(sesion)
        self.movimientos = MovimientoStockRepository(sesion)
        self.precios = HistorialPrecioRepository(sesion)
