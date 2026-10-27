"""Fixtures auth locales: Alembic y lifespan reales; no reemplazan `api` del CRUD."""

import secrets
from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import hashear_password
from app.core.unit_of_work import UnitOfWork
from app.modules.usuarios.models import AsignacionRol, Usuario

if TYPE_CHECKING:
    from test.pytest.conftest import aplicacion_iniciada, cliente_http
else:
    from conftest import aplicacion_iniciada, cliente_http


@pytest.fixture
async def aplicacion_auth(base_migrada: AsyncEngine) -> AsyncIterator[FastAPI]:
    """La fixture compartida migra/limpia exclusivamente la base de test."""
    async with aplicacion_iniciada() as app:
        yield app


@pytest.fixture
async def api_auth(aplicacion_auth: FastAPI) -> AsyncIterator[AsyncClient]:
    async with cliente_http(aplicacion_auth) as cliente:
        yield cliente


@pytest.fixture
async def crear_usuario_auth(
    aplicacion_auth: FastAPI,
) -> Callable[..., Coroutine[Any, Any, tuple[Usuario, str]]]:
    """Fábrica: devuelve usuario confirmado y contraseña efímera, nunca del seed."""
    async def crear(
        *,
        email: str,
        roles: tuple[str, ...] = ("CLIENTE",),
        activo: bool = True,
        debe_cambiar_password: bool = False,
    ) -> tuple[Usuario, str]:
        password = secrets.token_hex(16)
        password_hash = await hashear_password(
            password, aplicacion_auth.state.settings.bcrypt_rounds,
        )
        usuario = Usuario(
            email=email, nombre="Usuario de prueba", password_hash=password_hash,
            activo=activo, debe_cambiar_password=debe_cambiar_password,
        )
        async with (
            aplicacion_auth.state.fabrica_sesiones() as sesion,
            UnitOfWork(sesion),
        ):
            sesion.add(usuario)
            await sesion.flush()
            assert usuario.id is not None
            # IDs generados: los INSERT avanzan las secuencias sin setval manual.
            for rol in roles:
                sesion.add(AsignacionRol(
                    usuario_id=usuario.id, rol=rol, desde=datetime.now(UTC),
                ))
            await sesion.flush()
        return usuario, password

    return crear
