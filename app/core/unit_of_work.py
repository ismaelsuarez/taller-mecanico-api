"""UnitOfWork base: confirma o revierte al salir del bloque (EJ-3, T-2; completado en EJ-6).

RT-TX-02/RT-TX-03: el router lo construye con una dependencia y lo pasa sin abrir;
el servicio lo abre con `async with`. Commit al salir, rollback si sale con
excepción (también si el propio commit falla) y **no cierra la sesión** (no la
creó — B-3, la cierra `get_session`).
"""

from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    """Gestor de contexto asincrónico sobre una sesión ya creada."""

    def __init__(self, sesion: AsyncSession) -> None:
        self.sesion = sesion

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            try:
                await self.sesion.commit()
            except Exception:
                # El propio commit puede fallar: se revierte antes de propagar el error
                # (no depender del cierre de get_session ni de un override por módulo).
                await self.sesion.rollback()
                raise
        else:
            await self.sesion.rollback()
        # Nunca traga la excepción: la propaga al llamador.
        return False
