"""Verifica las migraciones de Alembic contra la PostgreSQL real de test (EJ-2).

Ciclo completo: `upgrade head` → `downgrade base` → `upgrade head`. También comprueba
el disparador de sólo agregado (migración 2) y que el downgrade lo limpia.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import configurar_entorno, leer_variable, requiere_base_de_test


def _url_test() -> str:
    from app.core.config import cargar_settings

    return cargar_settings().url_base_datos


@pytest.fixture
async def base_para_migraciones(configurar_entorno):
    """Base de test en cero, con un motor asincrónico para las migraciones."""
    requiere_base_de_test()
    configurar_entorno()

    from sqlalchemy.ext.asyncio import create_async_engine

    motor = create_async_engine(_url_test())
    # Empezar de cero: eliminar todas las tablas (incluida alembic_version).
    async with motor.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    yield motor
    await motor.dispose()


async def _alembic(motor, *comandos: str) -> None:
    """Corre comandos de Alembic con el motor de test (usando el env.py real)."""
    import asyncio
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    raiz = Path(__file__).resolve().parents[2]

    def _correr():
        cfg = Config(str(raiz / "alembic.ini"))
        cfg.set_main_option("script_location", str(raiz / "migrations"))
        # Alembic usa asyncio.run internamente en env.py; acá ya hay loop, así que
        # corremos cada comando en un thread para que asyncio.run pueda crear el suyo.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            for comando in comandos:
                if comando == "upgrade":
                    pool.submit(command.upgrade, cfg, "head").result()
                elif comando == "downgrade":
                    pool.submit(command.downgrade, cfg, "base").result()
                else:
                    raise ValueError(comando)

    await asyncio.to_thread(_correr)


async def _existe(motor, consulta: str) -> bool:
    async with motor.connect() as conn:
        resultado = await conn.execute(text(consulta))
        return resultado.scalar() is not None


async def _falla(motor, consulta: str, **params) -> str:
    try:
        async with motor.begin() as conn:
            await conn.execute(text(consulta), params)
    except DBAPIError as error:
        return str(error.orig)
    raise AssertionError(f"Debía fallar: {consulta}")


@pytest.mark.asyncio
class TestMigraciones:
    async def test_upgrade_crea_las_trece_tablas(self, base_para_migraciones):
        await _alembic(base_para_migraciones, "upgrade")
        esperadas = [
            "usuario", "asignacion_rol", "intento_acceso", "evento_seguridad",
            "cliente", "vehiculo", "repuesto", "estado_orden", "orden_trabajo",
            "item_orden", "historial_estado_orden", "movimiento_stock",
            "historial_precio_repuesto",
        ]
        async with base_para_migraciones.connect() as conn:
            for tabla in esperadas:
                existe = await conn.execute(
                    text("SELECT to_regclass(:t) IS NOT NULL"), {"t": tabla}
                )
                assert existe.scalar(), f"Falta la tabla {tabla}"

    async def test_estado_orden_vacio_tras_upgrade(self, base_para_migraciones):
        await _alembic(base_para_migraciones, "upgrade")
        async with base_para_migraciones.connect() as conn:
            cantidad = await conn.execute(text("SELECT count(*) FROM estado_orden"))
            assert cantidad.scalar() == 0, "El catálogo debe quedar vacío tras migrar"

    async def test_indices_parciales_existen(self, base_para_migraciones):
        await _alembic(base_para_migraciones, "upgrade")
        async with base_para_migraciones.connect() as conn:
            resultado = await conn.execute(text(
                "SELECT indexname FROM pg_indexes "
                "WHERE indexname IN "
                "('uq_asignacion_rol_abierta', 'uq_vehiculo_patente_vigente', 'uq_repuesto_codigo_vigente')"
            ))
            nombres = {fila[0] for fila in resultado}
            assert nombres == {
                "uq_asignacion_rol_abierta",
                "uq_vehiculo_patente_vigente",
                "uq_repuesto_codigo_vigente",
            }, f"Índices parciales encontrados: {nombres}"

    async def test_ciclo_upgrade_downgrade_upgrade(self, base_para_migraciones):
        await _alembic(base_para_migraciones, "upgrade")
        async with base_para_migraciones.connect() as conn:
            antes = await conn.execute(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
            ))
            total_antes = antes.scalar()

        await _alembic(base_para_migraciones, "downgrade")
        async with base_para_migraciones.connect() as conn:
            # Sólo debe quedar la tabla de versión de Alembic (o nada si downgrade la quitó).
            tablas = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ))
            restantes = {fila[0] for fila in tablas}
            assert "usuario" not in restantes, "El downgrade debe eliminar las tablas"

        await _alembic(base_para_migraciones, "upgrade")
        async with base_para_migraciones.connect() as conn:
            despues = await conn.execute(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
            ))
            assert despues.scalar() == total_antes, "El segundo upgrade debe dejar el mismo esquema"


@pytest.mark.asyncio
class TestDisparadorSoloAgregado:
    async def _preparar(self, motor):
        await _alembic(motor, "upgrade")
        ahora = datetime.now(timezone.utc)
        async with motor.begin() as conn:
            await conn.execute(text(
                "INSERT INTO estado_orden (codigo, descripcion, posicion, es_final) "
                "VALUES ('PENDIENTE', 'Pendiente', 1, false)"
            ))
            await conn.execute(text(
                "INSERT INTO usuario (id, email, nombre, password_hash, activo, debe_cambiar_password) "
                "VALUES (1, 'a@x.com', 'A', 'h', true, false)"
            ))
            await conn.execute(text(
                "INSERT INTO cliente (id, nombre, documento, telefono) VALUES (1, 'Laura', 'D-1', '111')"
            ))
            await conn.execute(text(
                "INSERT INTO vehiculo (id, cliente_id, patente, marca, modelo, anio) "
                "VALUES (1, 1, 'AB123CD', 'Fiat', 'Cronos', 2020)"
            ))
            await conn.execute(text(
                "INSERT INTO orden_trabajo (id, vehiculo_id, estado, falla, creada_en, total) "
                "VALUES (1, 1, 'PENDIENTE', 'Falla', :ahora, 0)"
            ), {"ahora": ahora})
            await conn.execute(text(
                "INSERT INTO repuesto (id, codigo, descripcion, precio, stock) "
                "VALUES (1, 'FIL-001', 'Filtro', 8500.00, 10)"
            ))
            # Filas en las tres tablas de auditoría.
            await conn.execute(text(
                "INSERT INTO historial_estado_orden (orden_id, hasta_estado, usuario_id, cuando) "
                "VALUES (1, 'PENDIENTE', 1, :ahora)"
            ), {"ahora": ahora})
            await conn.execute(text(
                "INSERT INTO movimiento_stock (repuesto_id, usuario_id, cantidad, motivo, cuando) "
                "VALUES (1, 1, 10, 'Stock inicial', :ahora)"
            ), {"ahora": ahora})
            await conn.execute(text(
                "INSERT INTO historial_precio_repuesto (repuesto_id, usuario_id, precio_anterior, precio_nuevo, cuando) "
                "VALUES (1, 1, 8000.00, 8500.00, :ahora)"
            ), {"ahora": ahora})

    @pytest.mark.parametrize("tabla", ["historial_estado_orden", "movimiento_stock", "historial_precio_repuesto"])
    async def test_update_rechazado(self, base_para_migraciones, tabla):
        await self._preparar(base_para_migraciones)
        mensaje = await _falla(
            base_para_migraciones,
            f"UPDATE {tabla} SET id = id WHERE id = 1",
        )
        assert "sólo agregado" in mensaje.lower() or "solo agregado" in mensaje.lower() or "append" in mensaje.lower()

    @pytest.mark.parametrize("tabla", ["historial_estado_orden", "movimiento_stock", "historial_precio_repuesto"])
    async def test_delete_rechazado(self, base_para_migraciones, tabla):
        await self._preparar(base_para_migraciones)
        mensaje = await _falla(
            base_para_migraciones,
            f"DELETE FROM {tabla} WHERE id = 1",
        )
        assert "sólo agregado" in mensaje.lower() or "solo agregado" in mensaje.lower() or "append" in mensaje.lower()

    @pytest.mark.parametrize("tabla", ["historial_estado_orden", "movimiento_stock", "historial_precio_repuesto"])
    async def test_insert_admitido(self, base_para_migraciones, tabla):
        await self._preparar(base_para_migraciones)
        ahora = datetime.now(timezone.utc)
        inserts = {
            "historial_estado_orden": (
                "INSERT INTO historial_estado_orden (orden_id, hasta_estado, usuario_id, cuando) "
                "VALUES (1, 'PENDIENTE', 1, :ahora)"
            ),
            "movimiento_stock": (
                "INSERT INTO movimiento_stock (repuesto_id, usuario_id, cantidad, motivo, cuando) "
                "VALUES (1, 1, 1, 'Otro', :ahora)"
            ),
            "historial_precio_repuesto": (
                "INSERT INTO historial_precio_repuesto (repuesto_id, usuario_id, precio_anterior, precio_nuevo, cuando) "
                "VALUES (1, 1, 8500.00, 9000.00, :ahora)"
            ),
        }
        async with base_para_migraciones.begin() as conn:
            await conn.execute(text(inserts[tabla]), {"ahora": ahora})

    async def test_disparador_instalado(self, base_para_migraciones):
        await _alembic(base_para_migraciones, "upgrade")
        assert await _existe(
            base_para_migraciones,
            "SELECT tgname FROM pg_trigger WHERE tgname = 'trg_historial_estado_orden_solo_agregado'",
        ), "Falta el trigger de historial_estado_orden"
        assert await _existe(
            base_para_migraciones,
            "SELECT tgname FROM pg_trigger WHERE tgname = 'trg_movimiento_stock_solo_agregado'",
        ), "Falta el trigger de movimiento_stock"
        assert await _existe(
            base_para_migraciones,
            "SELECT tgname FROM pg_trigger WHERE tgname = 'trg_historial_precio_repuesto_solo_agregado'",
        ), "Falta el trigger de historial_precio_repuesto"

    async def test_downgrade_limpia_disparador(self, base_para_migraciones):
        await _alembic(base_para_migraciones, "upgrade")
        await _alembic(base_para_migraciones, "downgrade")
        # Tras el downgrade no debe existir ni la función ni los triggers (las tablas ya no están).
        assert not await _existe(
            base_para_migraciones,
            "SELECT proname FROM pg_proc WHERE proname = 'solo_agregado'",
        ), "El downgrade debe eliminar la función solo_agregado"
