"""Fixtures compartidas: entorno de test, aplicación con su lifespan y cliente HTTP.

Los tests nunca usan la base de desarrollo: `POSTGRES_DB` se reemplaza por `POSTGRES_TEST_DB`.
Si no hay base de test, los tests que la necesitan se saltean con un motivo claro; la
verificación de cierre de cada change exige correrlos con la base levantada (0 skipped).
"""

import asyncio
import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

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


@asynccontextmanager
async def esquema_migrado_de_test() -> AsyncIterator[AsyncEngine]:
    """Esquema aislado por test: Alembic real, incluidos los tres disparadores.

    Limpia también alembic_version antes y después: los tests de migraciones
    pueden haber dejado otra revisión o eliminado public por completo.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine

    requiere_base_de_test()
    url = obtener_settings().url_base_datos
    if make_url(url).database != leer_variable("POSTGRES_TEST_DB"):
        raise RuntimeError("La limpieza sólo puede ejecutarse sobre POSTGRES_TEST_DB.")
    motor = create_async_engine(url)

    async def limpiar() -> None:
        async with motor.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))

    def migrar() -> None:
        cfg = Config(str(RAIZ / "alembic.ini"))
        cfg.set_main_option("script_location", str(RAIZ / "migrations"))
        command.upgrade(cfg, "head")

    try:
        await limpiar()
        # env.py usa asyncio.run: necesita su propio bucle, fuera del de pytest.
        await asyncio.to_thread(migrar)
        yield motor
    finally:
        try:
            await limpiar()
        finally:
            await motor.dispose()


@pytest.fixture
async def base_migrada(configurar_entorno):
    """Motor de PostgreSQL con esquema vacío migrado a head, nunca metadata."""
    requiere_base_de_test()
    configurar_entorno()
    async with esquema_migrado_de_test() as motor:
        yield motor


@pytest.fixture
async def api(base_migrada):
    """Aplicación con esquema Alembic real y catálogo + admin sembrados.

    Devuelve `(cliente_http, motor)`; la fixture base_migrada limpia al salir,
    incluso si falla la preparación de datos o el lifespan.
    """
    from sqlalchemy import text

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
        # El admin lo usa `actor_temporal` (T-4); en producción lo crea seed.py.
        await conn.execute(
            text(
                "INSERT INTO usuario (id, email, nombre, password_hash, activo, debe_cambiar_password) "
                "VALUES (1, 'admin@example.com', 'Administrador Uno', 'hash-de-test', true, false)"
            )
        )

    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        yield cliente, motor
