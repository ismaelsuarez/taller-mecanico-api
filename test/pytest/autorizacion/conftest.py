"""Fixtures de sesión autenticada de EJ-5: PostgreSQL real con Alembic y login real.

No reemplazan `api` (CRUD) ni `api_auth` (EJ-4): agregan usuarios fijos con hash
real y un logger de sesiones simultáneas sobre su propia base migrada.
"""

import secrets
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import hashear_password
from app.core.unit_of_work import UnitOfWork
from app.modules.usuarios.models import AsignacionRol, Usuario

if TYPE_CHECKING:
    from conftest import cliente_http  # noqa: F401
else:
    from conftest import CATALOGO_ESTADOS, aplicacion_iniciada, cliente_http

PASSWORD_DE_PRUEBA = "clave-de-sesion-123"

# email, nombre, roles vigentes, cambio de contraseña pendiente
USUARIOS_DE_PRUEBA = (
    ("admin@example.com", "Administrador Uno", ("ADMIN",), False),
    ("admin2@example.com", "Administrador Dos", ("ADMIN",), False),
    ("recepcion@example.com", "Recepcion Uno", ("RECEPCION",), False),
    ("mecanico@example.com", "Mecanico Uno", ("MECANICO",), False),
    ("cliente@example.com", "Cliente Uno", ("CLIENTE",), False),
    ("nuevo@example.com", "Personal Nuevo", ("MECANICO",), True),
)


@dataclass(frozen=True)
class EntornoAutorizacion:
    """Aplicación levantada con sus usuarios fijos; `cliente` no tiene sesión."""

    app: FastAPI
    motor: AsyncEngine
    cliente: AsyncClient


@pytest.fixture
async def api_autorizacion(base_migrada: AsyncEngine) -> AsyncIterator[EntornoAutorizacion]:
    motor = base_migrada
    async with motor.begin() as conn:
        for codigo, descripcion, posicion, es_final in CATALOGO_ESTADOS:
            await conn.execute(
                text(
                    "INSERT INTO estado_orden (codigo, descripcion, posicion, es_final) "
                    "VALUES (:c, :d, :p, :f)"
                ),
                {"c": codigo, "d": descripcion, "p": posicion, "f": es_final},
            )

    async with aplicacion_iniciada() as app:
        rondas = app.state.settings.bcrypt_rounds
        hash_fijo = await hashear_password(PASSWORD_DE_PRUEBA, rondas)
        async with app.state.fabrica_sesiones() as sesion, UnitOfWork(sesion):
            for email, nombre, roles, pendiente in USUARIOS_DE_PRUEBA:
                usuario = Usuario(
                    email=email, nombre=nombre, password_hash=hash_fijo,
                    activo=True, debe_cambiar_password=pendiente,
                )
                sesion.add(usuario)
                await sesion.flush()
                assert usuario.id is not None
                for rol in roles:
                    sesion.add(AsignacionRol(
                        usuario_id=usuario.id, rol=rol, desde=datetime.now(UTC),
                    ))
            await sesion.flush()

        async with cliente_http(app) as cliente:
            yield EntornoAutorizacion(app=app, motor=motor, cliente=cliente)


@pytest.fixture
async def abrir_sesion(api_autorizacion: EntornoAutorizacion) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Cada llamada devuelve un cliente nuevo con login real (cookies aisladas)."""

    @asynccontextmanager
    async def _abrir(email: str, password: str = PASSWORD_DE_PRUEBA):
        async with cliente_http(api_autorizacion.app) as cliente:
            respuesta = await cliente.post(
                "/auth/login", json={"email": email, "password": password},
            )
            assert respuesta.status_code == 200, respuesta.text
            yield cliente

    return _abrir


@pytest.fixture
async def crear_usuario_autorizacion(
    api_autorizacion: EntornoAutorizacion,
) -> Callable[..., Coroutine[Any, Any, tuple[Usuario, str]]]:
    """Fábrica de usuarios adicionales con hash real; nunca reemplaza la fábrica de auth."""

    async def crear(
        *,
        email: str,
        roles: tuple[str, ...] = (),
        activo: bool = True,
        debe_cambiar_password: bool = False,
    ) -> tuple[Usuario, str]:
        password = secrets.token_hex(16)
        password_hash = await hashear_password(
            password, api_autorizacion.app.state.settings.bcrypt_rounds,
        )
        usuario = Usuario(
            email=email, nombre="Usuario adicional", password_hash=password_hash,
            activo=activo, debe_cambiar_password=debe_cambiar_password,
        )
        async with (
            api_autorizacion.app.state.fabrica_sesiones() as sesion,
            UnitOfWork(sesion),
        ):
            sesion.add(usuario)
            await sesion.flush()
            assert usuario.id is not None
            for rol in roles:
                sesion.add(AsignacionRol(
                    usuario_id=usuario.id, rol=rol, desde=datetime.now(UTC),
                ))
            await sesion.flush()
        return usuario, password

    return crear
