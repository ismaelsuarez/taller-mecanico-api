"""Repositorios de autenticación: heredan flush, nunca confirman transacciones."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import BaseRepository
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, Usuario


class UsuarioRepository(BaseRepository[Usuario]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, Usuario)


class AsignacionRolRepository(BaseRepository[AsignacionRol]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, AsignacionRol)


class EventoSeguridadRepository(BaseRepository[EventoSeguridad]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, EventoSeguridad)
