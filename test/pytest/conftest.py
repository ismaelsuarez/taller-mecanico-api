"""Fixtures compartidas: entorno de test, aplicación con su lifespan y cliente HTTP.

Los tests nunca usan la base de desarrollo: `POSTGRES_DB` se reemplaza por `POSTGRES_TEST_DB`.
Si no hay base de test, los tests que la necesitan se saltean con un motivo claro; la
verificación de cierre de cada change exige correrlos con la base levantada (0 skipped).
"""

import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import obtener_settings

RAIZ = Path(__file__).resolve().parents[2]
CLAVE_DE_TEST = "clave-de-test-fija"
SIN_BASE_DE_TEST = "sin_base_de_test"


def leer_variable(nombre: str) -> str | None:
    """Valor de una variable: primero el entorno, después el .env de la raíz."""
    return os.environ.get(nombre) or dotenv_values(RAIZ / ".env").get(nombre) or None


@pytest.fixture
def configurar_entorno(monkeypatch):
    """Ajusta el entorno para un test; acepta variables extra que pisan a las demás."""

    def _configurar(**extra: str) -> None:
        valores = {
            "JWT_SECRET": CLAVE_DE_TEST,
            "POSTGRES_PASSWORD": leer_variable("POSTGRES_PASSWORD") or "pass-de-test",
            "POSTGRES_DB": leer_variable("POSTGRES_TEST_DB") or SIN_BASE_DE_TEST,
            "BCRYPT_ROUNDS": "4",
        }
        valores.update(extra)
        for clave, valor in valores.items():
            monkeypatch.setenv(clave, valor)
        obtener_settings.cache_clear()

    yield _configurar
    obtener_settings.cache_clear()


@asynccontextmanager
async def aplicacion_iniciada() -> AsyncIterator[FastAPI]:
    """Corre el lifespan real: httpx.ASGITransport no lo dispara por su cuenta."""
    from main import app

    async with app.router.lifespan_context(app):
        yield app


@asynccontextmanager
async def cliente_http(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cliente:
        yield cliente


def requiere_base_de_test() -> None:
    """Saltea el test con un motivo claro si no hay base de test configurada o si no responde."""
    if not leer_variable("POSTGRES_TEST_DB"):
        pytest.skip("Falta POSTGRES_TEST_DB: levantá la base (docker compose up -d db) y definila en .env")
    host = leer_variable("POSTGRES_HOST") or "localhost"
    puerto = int(leer_variable("POSTGRES_PORT") or 5432)
    try:
        socket.create_connection((host, puerto), timeout=1).close()
    except OSError:
        pytest.skip(f"La base de test no responde en {host}:{puerto}: levantala con docker compose up -d db")


CATALOGO_ESTADOS = [
    ("PENDIENTE", "Esperando ser tomada por un mecánico", 1, False),
    ("EN_REPARACION", "En curso de reparación", 2, False),
    ("TERMINADA", "Reparación terminada", 3, True),
    ("CANCELADA", "Orden cancelada", 4, True),
]


@pytest.fixture
async def api(configurar_entorno):
    """Esquema de test (catálogo de estados + admin sembrados) con la aplicación levantada.

    Andamio de test (A-3): el esquema lo crea el metadata de SQLModel, no Alembic;
    en producción lo crean las migraciones y lo puebla `seed.py` (A-5). Devuelve
    `(cliente_http, motor)` para que los tests consulten la base directamente.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import SQLModel

    # Importar todos los modelos para que estén en el metadata compartido (FKs).
    from app.modules.clientes.models import Cliente, Vehiculo  # noqa: F401
    from app.modules.ordenes.models import (  # noqa: F401
        EstadoOrden,
        HistorialEstadoOrden,
        ItemOrden,
        OrdenTrabajo,
    )
    from app.modules.repuestos.models import (  # noqa: F401
        HistorialPrecio,
        MovimientoStock,
        Repuesto,
    )
    from app.modules.usuarios.models import (  # noqa: F401
        AsignacionRol,
        EventoSeguridad,
        IntentoAcceso,
        Usuario,
    )

    requiere_base_de_test()
    configurar_entorno()

    motor = create_async_engine(obtener_settings().url_base_datos)
    async with motor.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
        for codigo, descripcion, posicion, es_final in CATALOGO_ESTADOS:
            await conn.execute(
                text(
                    "INSERT INTO estado_orden (codigo, descripcion, posicion, es_final) "
                    "VALUES (:c, :d, :p, :f)"
                ),
                {"c": codigo, "d": descripcion, "p": posicion, "f": es_final},
            )
        # El admin lo usa `actor_temporal` (T-4); en producción lo crea seed.py.
        await conn.execute(
            text(
                "INSERT INTO usuario (id, email, nombre, password_hash, activo, debe_cambiar_password) "
                "VALUES (1, 'admin@example.com', 'Administrador Uno', 'hash-de-test', true, false)"
            )
        )

    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        yield cliente, motor

    async with motor.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await motor.dispose()
