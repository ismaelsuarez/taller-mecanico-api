"""Ciclo de vida: los recursos se crean en el lifespan, nunca al importar, y se liberan al apagar."""

import os
import subprocess
import sys

import bcrypt
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core import security
from conftest import RAIZ, aplicacion_iniciada


async def test_el_lifespan_deja_los_recursos_en_el_estado_de_la_app(configurar_entorno):
    configurar_entorno()

    async with aplicacion_iniciada() as app:
        assert app.state.settings.jwt_secret.get_secret_value() == "clave-de-test-fija"
        assert isinstance(app.state.motor, AsyncEngine)
        assert isinstance(app.state.fabrica_sesiones, async_sessionmaker)
        assert bcrypt.checkpw(b"cualquier-cosa", app.state.hash_ficticio.encode()) is False


async def test_el_pool_del_motor_usa_el_tamano_configurado(configurar_entorno):
    configurar_entorno(DB_POOL_SIZE="3")

    async with aplicacion_iniciada() as app:
        assert app.state.motor.pool.size() == 3


async def test_al_apagar_se_libera_el_motor(configurar_entorno):
    """dispose() descarta el pool de conexiones y deja uno nuevo vacío en su lugar."""
    configurar_entorno()

    async with aplicacion_iniciada() as app:
        pool_en_uso = app.state.motor.pool

    assert app.state.motor.pool is not pool_en_uso


def test_importar_la_app_sin_configuracion_no_crea_recursos(tmp_path):
    """Sin variables ni .env, importar main no falla: nada se crea al importar (EA-08)."""
    entorno = {clave: valor for clave, valor in os.environ.items() if not clave.startswith(("POSTGRES_", "JWT_"))}
    entorno["PYTHONPATH"] = str(RAIZ)

    resultado = subprocess.run(
        [sys.executable, "-c", "import main; print(type(main.app).__name__)"],
        cwd=tmp_path,
        env=entorno,
        capture_output=True,
        text=True,
    )

    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "FastAPI"


async def test_hashear_password_sin_semaforo_configurado_falla_con_mensaje_claro(monkeypatch):
    monkeypatch.setattr(security, "_semaforo", None)

    with pytest.raises(RuntimeError, match="configurar_semaforo_bcrypt"):
        await security.hashear_password("una-contrasena", rondas=4)


async def test_hashear_password_produce_un_hash_bcrypt_verificable(monkeypatch):
    monkeypatch.setattr(security, "_semaforo", None)
    security.configurar_semaforo_bcrypt(2)

    resultado = await security.hashear_password("una-contrasena", rondas=4)

    assert bcrypt.checkpw(b"una-contrasena", resultado.encode())
