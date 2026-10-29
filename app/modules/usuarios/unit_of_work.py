"""UoW de usuarios e intentos; cada sesión pertenece a su dependencia, no al UoW.

El rollback de un commit fallido lo hace el `UnitOfWork` base (EJ-6, D4).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository
from app.modules.usuarios.repository import (
    AsignacionRolRepository,
    EventoSeguridadRepository,
    IntentoAccesoRepository,
    UsuarioRepository,
)


class UnitOfWorkUsuario(UnitOfWork):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion)
        self.usuarios = UsuarioRepository(sesion)
        self.roles = AsignacionRolRepository(sesion)
        self.clientes = ClienteRepository(sesion)
        self.eventos = EventoSeguridadRepository(sesion)


class UnitOfWorkIntentoAcceso(UnitOfWork):
    """Confirma sólo intentos; recibe una sesión distinta de la petición normal.

    EXCEPCIÓN DECLARADA (consigna Ej. 7, RT-SE-09, DD-05/DD-19): es la única escritura del
    sistema que no comparte la transacción de su petición. Existe porque el fallo que se
    quiere contar es el mismo que revierte la petición. Costo: deja filas aunque la petición
    falle, y usa otra conexión. Toda otra escritura se confirma con `UnitOfWorkUsuario` (o el
    UoW de su módulo) sobre la sesión de su petición.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion)
        self.intentos = IntentoAccesoRepository(sesion)
