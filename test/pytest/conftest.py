"""Fixtures compartidas: entorno de test, aplicación con su lifespan y cliente HTTP.

Los tests nunca usan la base de desarrollo: `POSTGRES_DB` se reemplaza por `POSTGRES_TEST_DB`.
Si no hay base de test, los tests que la necesitan se saltean con un motivo claro; la
verificación de cierre de cada change exige correrlos con la base levantada (0 skipped).
"""

import os
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
    """Saltea el test con un motivo claro si no hay base de test configurada."""
    if not leer_variable("POSTGRES_TEST_DB"):
        pytest.skip("Falta POSTGRES_TEST_DB: levantá la base (docker compose up -d db) y definila en .env")
