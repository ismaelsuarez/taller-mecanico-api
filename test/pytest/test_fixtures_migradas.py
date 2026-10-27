"""S2: las fixtures de integración incluyen el esquema real y sus disparadores."""

import asyncio
import subprocess
import sys

import pytest
from conftest import (
    CLAVE_DE_TEST,
    RAIZ,
    aplicacion_iniciada,
    cliente_http,
    esquema_migrado_de_test,
)
from sqlalchemy import MetaData, Table, delete, select, text, update
from sqlalchemy.exc import DBAPIError
from test_salud import puerto_libre

from seed import sembrar

TABLAS_AUDITORIA = (
    "historial_estado_orden", "movimiento_stock", "historial_precio_repuesto",
)


async def test_migrar_preserva_el_diagnostico_503_en_la_captura_actual(configurar_entorno, caplog):
    configurar_entorno()
    # Inicializar la aplicación antes de Alembic reproduce el orden de la suite.
    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        assert (await cliente.get("/health/live")).status_code == 200

    with caplog.at_level("WARNING", logger="app.salud"):
        async with esquema_migrado_de_test():
            pass
        configurar_entorno(
            POSTGRES_HOST="127.0.0.1",
            POSTGRES_PORT=str(puerto_libre()),
            POSTGRES_PASSWORD=CLAVE_DE_TEST,
            JWT_SECRET=CLAVE_DE_TEST,
        )
        async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
            assert (await cliente.get("/health/ready")).status_code == 503

    avisos = [registro for registro in caplog.records if registro.name == "app.salud"]
    assert len(avisos) == 1
    assert "ConnectionRefusedError" in avisos[0].getMessage()
    assert CLAVE_DE_TEST not in caplog.text


async def test_alembic_cli_conserva_sus_diagnosticos(base_migrada):
    # Proceso nuevo sin handlers: debe conservar el logging normal de alembic.ini.
    # Hereda POSTGRES_DB de la fixture; current no modifica el esquema.
    resultado = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "current"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert "a1b2c3d4e5f6 (head)" in resultado.stdout
    assert "[alembic.runtime.migration] Context impl PostgresqlImpl." in resultado.stderr


async def test_api_instala_los_tres_disparadores_y_alembic_head(api):
    _, motor = api
    async with motor.connect() as conexion:
        disparadores = await conexion.execute(text(
            "SELECT tgname FROM pg_trigger "
            "WHERE NOT tgisinternal AND tgrelid IN ("
            "'historial_estado_orden'::regclass, 'movimiento_stock'::regclass, "
            "'historial_precio_repuesto'::regclass)"
        ))
        assert set(disparadores.scalars()) == {
            "trg_historial_estado_orden_solo_agregado",
            "trg_movimiento_stock_solo_agregado",
            "trg_historial_precio_repuesto_solo_agregado",
        }
        version = await conexion.execute(text("SELECT version_num FROM alembic_version"))
        assert version.scalars().all() == ["a1b2c3d4e5f6"]


@pytest.mark.parametrize("tabla", TABLAS_AUDITORIA)
@pytest.mark.parametrize("operacion", ["UPDATE", "DELETE"])
async def test_api_protege_historiales_sin_alterar_filas(api, tabla, operacion):
    _, motor = api
    await sembrar()  # INSERT sigue permitido con los tres disparadores activos.
    async with motor.connect() as conexion:
        historial = await conexion.run_sync(
            lambda conn: Table(tabla, MetaData(), autoload_with=conn)
        )
        lectura = select(historial).order_by(historial.c.id)
        antes = (await conexion.execute(lectura)).all()
    assert antes
    consulta = (
        update(historial).values(id=historial.c.id)
        if operacion == "UPDATE" else delete(historial)
    ).where(historial.c.id == 1)
    with pytest.raises(DBAPIError, match="sólo agregado"):
        async with motor.begin() as conexion:
            await conexion.execute(consulta)
    async with motor.connect() as conexion:
        despues = (await conexion.execute(lectura)).all()
    assert despues == antes


async def test_fixture_rechaza_una_base_distinta_de_la_asignada(configurar_entorno):
    configurar_entorno(POSTGRES_DB="otra_base_no_autorizada")
    with pytest.raises(RuntimeError, match="sólo puede ejecutarse sobre POSTGRES_TEST_DB"):
        async with esquema_migrado_de_test():
            pytest.fail("No debe abrir ni limpiar otra base.")


async def test_fixture_limpia_version_tras_fallo_y_permite_remigrar(configurar_entorno):
    configurar_entorno()
    motor = None
    with pytest.raises(RuntimeError, match="falla del test"):
        async with esquema_migrado_de_test() as motor:
            await sembrar()
            raise RuntimeError("falla del test")

    # Otra conexión observa el teardown: no quedan tablas ni alembic_version.
    assert motor is not None
    try:
        async with motor.connect() as conexion:
            tablas = await conexion.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ))
            assert tablas.all() == []
    finally:
        await motor.dispose()

    async with esquema_migrado_de_test() as motor, motor.connect() as conexion:
        cantidad = await conexion.execute(text("SELECT count(*) FROM estado_orden"))
        assert cantidad.scalar_one() == 0
        version = await conexion.execute(text("SELECT version_num FROM alembic_version"))
        assert version.scalars().all() == ["a1b2c3d4e5f6"]
