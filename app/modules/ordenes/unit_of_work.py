"""Unit of Work mínimo del módulo ordenes (EJ-5, T-2); EJ-6 lo completa."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.ordenes.repository import OrdenRepository


class UnitOfWorkOrden(UnitOfWork):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion)
        self.ordenes = OrdenRepository(sesion)
