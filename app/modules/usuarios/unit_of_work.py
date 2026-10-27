"""Registro atómico sobre una sesión propiedad de get_session, no del UoW."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository
from app.modules.usuarios.repository import (
    AsignacionRolRepository,
    EventoSeguridadRepository,
    UsuarioRepository,
)


class UnitOfWorkUsuario(UnitOfWork):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion)
        self.usuarios = UsuarioRepository(sesion)
        self.roles = AsignacionRolRepository(sesion)
        self.clientes = ClienteRepository(sesion)
        self.eventos = EventoSeguridadRepository(sesion)

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        try:
            return await super().__aexit__(exc_type, exc, tb)
        except Exception:
            # El commit también puede fallar: no depender del cierre de get_session.
            await self.sesion.rollback()
            raise
