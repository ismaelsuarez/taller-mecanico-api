"""Motor asincrónico, fábrica de sesiones y get_session (EJ-1).

Nada se crea al importar este módulo: el lifespan llama a `crear_motor` y
`crear_fabrica_sesiones` cuando ya existe el bucle de eventos (EA-08) y los guarda en `app.state`.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings


def crear_motor(settings: Settings) -> AsyncEngine:
    # pool_pre_ping descarta conexiones muertas tras una caída de la base, así la app se recupera sola.
    return create_async_engine(
        settings.url_base_datos,
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        echo=settings.sql_echo,
    )


def crear_fabrica_sesiones(motor: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(motor, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Una sesión por petición; se cierra al terminar aunque la petición falle."""
    async with request.app.state.fabrica_sesiones() as sesion:
        yield sesion


SesionDep = Annotated[AsyncSession, Depends(get_session)]
