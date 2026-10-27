"""Verifica el seed inicial del taller (EJ-2, spec datos-iniciales).

El seed debe dejar la base en el estado conocido: catálogo, 7 usuarios con roles,
Laura y Jorge con sus vehículos, 4 repuestos con movimiento «Stock inicial»,
2 órdenes con historiales, historial de precios del filtro y evento `SISTEMA`.
Debe ser idempotente: dos corridas dejan el mismo estado.
"""

import ast
import asyncio
import inspect
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import leer_variable, requiere_base_de_test
from sqlalchemy import MetaData, select, text
from sqlalchemy.exc import DBAPIError

RAIZ = Path(__file__).resolve().parents[2]
TABLAS_DEL_SEED = (
    "estado_orden", "usuario", "asignacion_rol", "cliente", "vehiculo", "repuesto",
    "orden_trabajo", "item_orden", "historial_estado_orden", "movimiento_stock",
    "historial_precio_repuesto", "evento_seguridad", "intento_acceso",
)


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


async def _consulta(motor, sql: str, **params):
    async with motor.connect() as conn:
        resultado = await conn.execute(text(sql), params)
        return resultado.all()


async def _estado_completo(motor):
    metadata = MetaData()
    async with motor.connect() as conexion:
        await conexion.run_sync(lambda conn: metadata.reflect(conn, only=TABLAS_DEL_SEED))
        estado = {}
        for nombre in TABLAS_DEL_SEED:
            tabla = metadata.tables[nombre]
            consulta = select(tabla).order_by(*tabla.primary_key.columns)
            estado[nombre] = (await conexion.execute(consulta)).all()
        return estado


@pytest.mark.parametrize("al_confirmar", [False, True], ids=["carga", "commit"])
async def test_seed_fallido_conserva_datos_e_historiales(base_migrada, al_confirmar):
    """Falla real de PostgreSQL, tras TRUNCATE y recarga, sin mocks de la base."""
    from seed import sembrar

    await sembrar()
    async with base_migrada.begin() as conn:
        await conn.execute(text("UPDATE cliente SET nombre = 'Nombre conservado' WHERE id = 1"))
        await conn.execute(text("""
            CREATE FUNCTION rechazar_seed_de_test() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Fallo de recarga de prueba';
            END;
            $$ LANGUAGE plpgsql
        """))
        if al_confirmar:
            await conn.execute(text("""
                CREATE CONSTRAINT TRIGGER rechazar_seed_de_test
                AFTER INSERT ON evento_seguridad DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION rechazar_seed_de_test()
            """))
        else:
            await conn.execute(text("""
                CREATE TRIGGER rechazar_seed_de_test BEFORE INSERT ON evento_seguridad
                FOR EACH ROW EXECUTE FUNCTION rechazar_seed_de_test()
            """))
    antes = await _estado_completo(base_migrada)
    with pytest.raises(DBAPIError, match="Fallo de recarga de prueba"):
        await sembrar()
    assert await _estado_completo(base_migrada) == antes
    # La recarga fallida tampoco debe dejar adelantada la secuencia del cliente.
    async with base_migrada.begin() as conn:
        identificador = await conn.execute(text(
            "INSERT INTO cliente (nombre, documento, telefono) "
            "VALUES ('Cliente posterior', 'DNI-POSTERIOR', '111') RETURNING id"
        ))
        assert identificador.scalar_one() == 3


def test_seed_confirma_solo_por_el_uow_existente():
    """S4 es arquitectónico: ambas implementaciones pueden ser atómicas.

    Esta comprobación estructural complementa la integración real, no pretende
    demostrar una pérdida de atomicidad en el seed anterior.
    """
    import seed
    from app.core.unit_of_work import UnitOfWork

    arbol = ast.parse(inspect.getsource(seed.sembrar))
    bloques = [
        nodo for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "UnitOfWork"
            for item in nodo.items
        )
    ]
    assert len(bloques) == 1, "El seed debe abrir un único UnitOfWork para vaciar y recargar."
    assert seed.UnitOfWork is UnitOfWork
    llamadas = [nodo.func for nodo in ast.walk(bloques[0]) if isinstance(nodo, ast.Call)]
    assert {"_vaciar", "_cargar"} <= {
        funcion.id for funcion in llamadas if isinstance(funcion, ast.Name)
    }
    assert not any(
        isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr in {"commit", "begin"}
        for nodo in ast.walk(arbol)
    ), "El seed no debe confirmar mediante una sesión o conexión fuera del UoW."
    hashes = [
        nodo for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
        and nodo.func.id == "_hashear"
    ]
    assert hashes and all(nodo.lineno < bloques[0].lineno for nodo in hashes)


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
        async def estado_logico():
            # Sólo cambian las marcas de ejecución y las sales aleatorias de bcrypt.
            variables = {"password_hash", "cuando", "creada_en", "desde"}
            estado = await _estado_completo(base_migrada)
            return {
                tabla: [
                    {clave: valor for clave, valor in fila._mapping.items() if clave not in variables}
                    for fila in filas
                ]
                for tabla, filas in estado.items()
            }

        await _ejecutar_seed()
        estado_1 = await estado_logico()
        await _ejecutar_seed()
        assert await estado_logico() == estado_1

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
