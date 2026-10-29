"""Unit of Work del módulo clientes (Cliente y Vehiculo) — EJ-3 (T-2).

El router lo construye con una dependencia y lo pasa sin abrir; el servicio lo
abre con `async with` (RT-TX-02). Compone los repositorios con la misma sesión
y confirma o revierte al salir del bloque (RT-TX-03).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository, VehiculoRepository
from app.modules.ordenes.repository import OrdenRepository


class UnitOfWorkCliente(UnitOfWork):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion)
        self.clientes = ClienteRepository(sesion)
        self.vehiculos = VehiculoRepository(sesion)
        # Sólo para saber si un vehículo tiene órdenes abiertas (RN-16).
        self.ordenes = OrdenRepository(sesion)
