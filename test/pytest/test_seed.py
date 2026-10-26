"""Verifica el seed inicial del taller (EJ-2, spec datos-iniciales).

El seed debe dejar la base en el estado conocido: catálogo, 7 usuarios con roles,
Laura y Jorge con sus vehículos, 4 repuestos con movimiento «Stock inicial»,
2 órdenes con historiales, historial de precios del filtro y evento `SISTEMA`.
Debe ser idempotente: dos corridas dejan el mismo estado.
"""

import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from conftest import configurar_entorno, leer_variable, requiere_base_de_test

RAIZ = Path(__file__).resolve().parents[2]


def _url_test() -> str:
    from app.core.config import cargar_settings

    return cargar_settings().url_base_datos


async def _ejecutar_seed() -> None:
    """Corre `python seed.py` como subproceso contra la base de test (variables del entorno)."""
    import os

    entorno = dict(os.environ)
    entorno["POSTGRES_DB"] = leer_variable("POSTGRES_TEST_DB") or ""
    entorno.setdefault("JWT_SECRET", "clave-de-test-fija")
    # Bajamos el costo de bcrypt para que el seed de test sea rápido.
    entorno["BCRYPT_ROUNDS"] = "4"

    proceso = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, str(RAIZ / "seed.py")],
        capture_output=True,
        text=True,
        env=entorno,
        cwd=str(RAIZ),
    )
    if proceso.returncode != 0:
        raise AssertionError(
            f"seed.py terminó con código {proceso.returncode}:\n"
            f"stdout:\n{proceso.stdout}\nstderr:\n{proceso.stderr}"
        )


@pytest.fixture
async def base_migrada(configurar_entorno):
    """Base de test migrada a head, lista para el seed."""
    requiere_base_de_test()
    configurar_entorno()

    from sqlalchemy.ext.asyncio import create_async_engine

    motor = create_async_engine(_url_test())

    # Migrar a head con Alembic (en thread, porque env.py usa asyncio.run).
    def _migrar():
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(RAIZ / "alembic.ini"))
        cfg.set_main_option("script_location", str(RAIZ / "migrations"))
        command.upgrade(cfg, "head")

    await asyncio.to_thread(_migrar)

    yield motor

    async with motor.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await motor.dispose()


async def _consulta(motor, sql: str, **params):
    async with motor.connect() as conn:
        resultado = await conn.execute(text(sql), params)
        return resultado.all()


@pytest.mark.asyncio
class TestSeed:
    async def test_catalogo_cuatro_estados(self, base_migrada):
        await _ejecutar_seed()
        filas = await _consulta(
            base_migrada,
            "SELECT codigo, posicion, es_final FROM estado_orden ORDER BY posicion",
        )
        assert len(filas) == 4
        codigos = [f[0] for f in filas]
        assert codigos == ["PENDIENTE", "EN_REPARACION", "TERMINADA", "CANCELADA"]
        assert filas[2][2] is True and filas[3][2] is True  # TERMINADA y CANCELADA son finales
        assert filas[0][2] is False and filas[1][2] is False

    async def test_siete_usuarios_con_roles(self, base_migrada):
        await _ejecutar_seed()
        filas = await _consulta(
            base_migrada,
            "SELECT u.email, ar.rol FROM usuario u "
            "JOIN asignacion_rol ar ON ar.usuario_id = u.id "
            "WHERE ar.revocada_en IS NULL ORDER BY u.email",
        )
        esperado = {
            ("admin@example.com", "ADMIN"),
            ("admin2@example.com", "ADMIN"),
            ("recepcion@example.com", "RECEPCION"),
            ("mecanico@example.com", "MECANICO"),
            ("mecanico2@example.com", "MECANICO"),
            ("cliente@example.com", "CLIENTE"),
            ("nuevo@example.com", "MECANICO"),
        }
        assert set(filas) == esperado

    async def test_nuevo_pide_cambio_password(self, base_migrada):
        await _ejecutar_seed()
        filas = await _consulta(
            base_migrada,
            "SELECT debe_cambiar_password FROM usuario WHERE email = 'nuevo@example.com'",
        )
        assert filas[0][0] is True

    async def test_laura_y_jorge_con_vehiculos(self, base_migrada):
        await _ejecutar_seed()
        laura = await _consulta(
            base_migrada,
            "SELECT c.id, c.usuario_id IS NOT NULL, COUNT(v.id) "
            "FROM cliente c LEFT JOIN vehiculo v ON v.cliente_id = c.id "
            "WHERE c.nombre LIKE 'Laura%' GROUP BY c.id, c.usuario_id",
        )
        assert laura and laura[0][1] is True and laura[0][2] == 2

        jorge = await _consulta(
            base_migrada,
            "SELECT c.id, c.usuario_id IS NULL, COUNT(v.id) "
            "FROM cliente c LEFT JOIN vehiculo v ON v.cliente_id = c.id "
            "WHERE c.nombre LIKE 'Jorge%' GROUP BY c.id, c.usuario_id",
        )
        assert jorge and jorge[0][1] is True and jorge[0][2] == 1

        # El vehículo id=2 (AC456EF) es de Laura.
        patente = await _consulta(
            base_migrada,
            "SELECT c.nombre FROM vehiculo v JOIN cliente c ON c.id = v.cliente_id WHERE v.id = 2",
        )
        assert "Laura" in patente[0][0]

    async def test_repuestos_y_movimientos_coherentes(self, base_migrada):
        await _ejecutar_seed()
        filas = await _consulta(
            base_migrada,
            "SELECT r.codigo, r.precio, r.stock, "
            "COALESCE((SELECT SUM(ms.cantidad) FROM movimiento_stock ms WHERE ms.repuesto_id = r.id), 0) "
            "FROM repuesto r WHERE r.borrado_en IS NULL ORDER BY r.id",
        )
        assert len(filas) == 4
        por_codigo = {f[0]: f for f in filas}
        assert por_codigo["FIL-001"][1] == Decimal("8500.00")
        assert por_codigo["FIL-001"][2] == 10
        assert por_codigo["BUJ-014"][1] == Decimal("6500.00")
        assert por_codigo["BUJ-014"][2] == 2
        # Stock coherente con la suma de movimientos.
        for fila in filas:
            assert fila[2] == fila[3], f"Stock de {fila[0]} no coincide con sus movimientos"

    async def test_orden1_pendiente_dos_items_total(self, base_migrada):
        await _ejecutar_seed()
        orden = await _consulta(
            base_migrada,
            "SELECT o.estado, o.total, COUNT(i.id) FROM orden_trabajo o "
            "JOIN item_orden i ON i.orden_id = o.id WHERE o.id = 1 GROUP BY o.estado, o.total",
        )
        assert orden and orden[0][0] == "PENDIENTE"
        assert orden[0][1] == Decimal("56500.00")
        assert orden[0][2] == 2

    async def test_orden2_en_reparacion_asignada(self, base_migrada):
        await _ejecutar_seed()
        orden = await _consulta(
            base_migrada,
            "SELECT o.estado, o.total, u.email, COUNT(i.id) "
            "FROM orden_trabajo o "
            "JOIN usuario u ON u.id = o.mecanico_id "
            "JOIN item_orden i ON i.orden_id = o.id "
            "WHERE o.id = 2 GROUP BY o.estado, o.total, u.email",
        )
        assert orden and orden[0][0] == "EN_REPARACION"
        assert orden[0][1] == Decimal("26000.00")
        assert orden[0][2] == "mecanico@example.com"
        assert orden[0][3] == 1  # 1 tipo de ítem (4 bujías)

    async def test_historial_estados_coherente(self, base_migrada):
        await _ejecutar_seed()
        historial = await _consulta(
            base_migrada,
            "SELECT he.orden_id, he.desde_estado, he.hasta_estado, u.email "
            "FROM historial_estado_orden he JOIN usuario u ON u.id = he.usuario_id "
            "WHERE he.orden_id = 2 ORDER BY he.id",
        )
        assert len(historial) == 2
        assert historial[0][1] is None and historial[0][2] == "PENDIENTE"
        assert historial[0][3] == "recepcion@example.com"
        assert historial[1][1] == "PENDIENTE" and historial[1][2] == "EN_REPARACION"
        assert historial[1][3] == "mecanico@example.com"

    async def test_historial_precios_filtro(self, base_migrada):
        await _ejecutar_seed()
        historial = await _consulta(
            base_migrada,
            "SELECT hp.precio_anterior, hp.precio_nuevo, u.email "
            "FROM historial_precio_repuesto hp "
            "JOIN repuesto r ON r.id = hp.repuesto_id "
            "JOIN usuario u ON u.id = hp.usuario_id "
            "WHERE r.codigo = 'FIL-001'",
        )
        assert len(historial) == 1
        assert historial[0][0] == Decimal("8000.00")
        assert historial[0][1] == Decimal("8500.00")
        assert historial[0][2] == "admin@example.com"

    async def test_evento_sistema(self, base_migrada):
        await _ejecutar_seed()
        evento = await _consulta(
            base_migrada,
            "SELECT actor, accion FROM evento_seguridad WHERE actor = 'SISTEMA'",
        )
        assert evento and "datos iniciales" in evento[0][1].lower()

    async def test_idempotente_dos_corridas(self, base_migrada):
        await _ejecutar_seed()
        estado_1 = await _consulta(
            base_migrada,
            "SELECT (SELECT count(*) FROM usuario), (SELECT count(*) FROM cliente), "
            "(SELECT count(*) FROM vehiculo), (SELECT count(*) FROM repuesto), "
            "(SELECT count(*) FROM orden_trabajo), (SELECT count(*) FROM item_orden), "
            "(SELECT count(*) FROM historial_estado_orden), (SELECT count(*) FROM movimiento_stock), "
            "(SELECT count(*) FROM historial_precio_repuesto), (SELECT count(*) FROM estado_orden), "
            "(SELECT count(*) FROM evento_seguridad)",
        )
        await _ejecutar_seed()
        estado_2 = await _consulta(
            base_migrada,
            "SELECT (SELECT count(*) FROM usuario), (SELECT count(*) FROM cliente), "
            "(SELECT count(*) FROM vehiculo), (SELECT count(*) FROM repuesto), "
            "(SELECT count(*) FROM orden_trabajo), (SELECT count(*) FROM item_orden), "
            "(SELECT count(*) FROM historial_estado_orden), (SELECT count(*) FROM movimiento_stock), "
            "(SELECT count(*) FROM historial_precio_repuesto), (SELECT count(*) FROM estado_orden), "
            "(SELECT count(*) FROM evento_seguridad)",
        )
        assert estado_1 == estado_2, f"El seed no es idempotente: {estado_1} != {estado_2}"

    async def test_seed_sin_tablas_da_mensaje_claro(self, configurar_entorno):
        """Sin migrar, el seed debe informar que falta migrar, no un traceback crudo."""
        requiere_base_de_test()
        configurar_entorno()

        from sqlalchemy.ext.asyncio import create_async_engine

        motor = create_async_engine(_url_test())
        async with motor.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await motor.dispose()

        import os

        entorno = dict(os.environ)
        entorno["POSTGRES_DB"] = leer_variable("POSTGRES_TEST_DB") or ""
        entorno.setdefault("JWT_SECRET", "clave-de-test-fija")
        entorno["BCRYPT_ROUNDS"] = "4"

        proceso = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(RAIZ / "seed.py")],
            capture_output=True,
            text=True,
            env=entorno,
            cwd=str(RAIZ),
        )
        assert proceso.returncode != 0
        mensaje = proceso.stdout + proceso.stderr
        assert "migrar" in mensaje.lower() or "alembic" in mensaje.lower()
        assert "Traceback" not in mensaje or "migrar" in mensaje.lower()
