"""Punto único de escritura de stock con guarda (5.2, RN-13/RN-14, B-7, D5).

`RepuestoRepository.registrar_movimiento` rechaza una salida mayor al stock antes de
tocar nada (→ `StockInsuficiente`, 409) y es el único lugar que asigna `stock` de un
repuesto existente. PostgreSQL real migrada con Alembic.
"""

import ast
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.errores import EnConflicto
from app.modules.repuestos.models import MovimientoStock
from app.modules.repuestos.repository import RepuestoRepository

from .conftest import Datos

RAIZ = Path(__file__).resolve().parents[3]


async def _movimientos(sesion, repuesto_id: int) -> list[int]:
    resultado = await sesion.execute(
        select(MovimientoStock.cantidad).where(MovimientoStock.repuesto_id == repuesto_id)
    )
    return list(resultado.scalars().all())


class TestGuardaDeStockInsuficiente:
    async def test_una_salida_mayor_al_stock_lanza_conflicto_sin_cambiar_nada(self, fabrica):
        from app.core.errores import StockInsuficiente

        async with fabrica() as sesion:
            datos = Datos(sesion)
            usuario = await datos.usuario("mecanico@example.com")
            repuesto = await datos.repuesto("BUJ-014", stock=2)
            await sesion.commit()

            with pytest.raises(StockInsuficiente) as error:
                await RepuestoRepository(sesion).registrar_movimiento(
                    repuesto, -4, "Salida por orden de trabajo #2", usuario.id,
                )

            assert isinstance(error.value, EnConflicto)
            assert repuesto.stock == 2
            assert await _movimientos(sesion, repuesto.id) == []
            assert not sesion.new  # tampoco quedó un movimiento pendiente en la sesión

    async def test_el_mensaje_es_humano_y_nombra_el_repuesto_y_las_cantidades(self, fabrica):
        from app.core.errores import StockInsuficiente

        async with fabrica() as sesion:
            datos = Datos(sesion)
            usuario = await datos.usuario("mecanico@example.com")
            repuesto = await datos.repuesto("BUJ-014", stock=2)
            await sesion.commit()

            with pytest.raises(StockInsuficiente) as error:
                await RepuestoRepository(sesion).registrar_movimiento(repuesto, -4, "x", usuario.id)

        mensaje = str(error.value)
        assert mensaje == (
            "No hay stock suficiente de Repuesto BUJ-014 (BUJ-014): hay 2 y se necesitan 4."
        )
        for tecnico in ("ck_", "repuesto_stock", "constraint", "IntegrityError"):
            assert tecnico not in mensaje

    async def test_otro_repuesto_y_otras_cantidades_dan_otro_mensaje(self, fabrica):
        from app.core.errores import StockInsuficiente

        async with fabrica() as sesion:
            datos = Datos(sesion)
            usuario = await datos.usuario("mecanico@example.com")
            repuesto = await datos.repuesto("FIL-001", stock=0)
            await sesion.commit()

            with pytest.raises(StockInsuficiente) as error:
                await RepuestoRepository(sesion).registrar_movimiento(repuesto, -1, "x", usuario.id)

        assert "hay 0 y se necesitan 1" in str(error.value)
        assert "FIL-001" in str(error.value)


class TestTraduccionHttp:
    @pytest.mark.parametrize(
        ("descripcion", "codigo", "hay", "pide"),
        [("Bujía de encendido", "BUJ-014", 2, 4), ("Filtro de aceite", "FIL-001", 0, 1)],
    )
    async def test_el_traductor_de_conflictos_responde_409_con_el_mensaje_humano(
        self, descripcion, codigo, hay, pide,
    ):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from app.core.errores import StockInsuficiente, registrar_traductores

        app = FastAPI()
        registrar_traductores(app)

        @app.get("/prueba")
        async def _prueba() -> None:
            raise StockInsuficiente(descripcion, codigo, hay, pide)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cliente:
            respuesta = await cliente.get("/prueba")

        assert respuesta.status_code == 409
        assert respuesta.json() == {
            "detail": f"No hay stock suficiente de {descripcion} ({codigo}): hay {hay} y se necesitan {pide}."
        }


class TestSalidaExactaYEntrada:
    async def test_una_salida_igual_al_stock_lo_deja_en_cero(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            usuario = await datos.usuario("mecanico@example.com")
            repuesto = await datos.repuesto("BUJ-014", stock=4)
            await sesion.commit()

            movimiento = await RepuestoRepository(sesion).registrar_movimiento(
                repuesto, -4, "Salida por orden de trabajo #2", usuario.id,
            )

            assert repuesto.stock == 0
            assert movimiento.cantidad == -4
            assert await _movimientos(sesion, repuesto.id) == [-4]

    async def test_una_salida_menor_al_stock_descuenta_la_diferencia(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            usuario = await datos.usuario("mecanico@example.com")
            repuesto = await datos.repuesto("FIL-001", stock=10)
            await sesion.commit()

            await RepuestoRepository(sesion).registrar_movimiento(repuesto, -3, "x", usuario.id)

            assert repuesto.stock == 7

    @pytest.mark.parametrize(("inicial", "entrada", "esperado"), [(0, 5, 5), (2, 3, 5)])
    async def test_una_entrada_suma_y_registra_el_movimiento_positivo(
        self, fabrica, inicial, entrada, esperado,
    ):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            usuario = await datos.usuario("admin@example.com")
            repuesto = await datos.repuesto("BUJ-014", stock=inicial)
            await sesion.commit()

            await RepuestoRepository(sesion).registrar_movimiento(
                repuesto, entrada, "Reposición", usuario.id,
            )

            assert repuesto.stock == esperado
            assert await _movimientos(sesion, repuesto.id) == [entrada]

    async def test_el_movimiento_de_salida_guarda_orden_usuario_y_motivo(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            usuario = await datos.usuario("mecanico@example.com")
            repuesto = await datos.repuesto("BUJ-014", stock=6)
            vehiculo = await datos.vehiculo(await datos.cliente("DNI-1"), "AA111AA")
            orden = await datos.orden(vehiculo, "EN_REPARACION")
            await sesion.commit()

            movimiento = await RepuestoRepository(sesion).registrar_movimiento(
                repuesto, -4, f"Salida por orden de trabajo #{orden.id}", usuario.id,
                orden_id=orden.id,
            )

            assert (movimiento.orden_id, movimiento.usuario_id) == (orden.id, usuario.id)
            assert movimiento.motivo == f"Salida por orden de trabajo #{orden.id}"
            total = await sesion.scalar(select(func.count()).select_from(MovimientoStock))
            assert total == 1


def _asignaciones_a_stock(raiz: Path) -> list[str]:
    """`x.stock = ...`, `x.stock += ...` y `setattr(x, "stock", ...)` en todo `app/`."""
    hallazgos = []
    for ruta in sorted((raiz / "app").rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for funcion in ast.walk(arbol):
            if not isinstance(funcion, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for nodo in ast.walk(funcion):
                objetivos = []
                if isinstance(nodo, ast.Assign):
                    objetivos = nodo.targets
                elif isinstance(nodo, ast.AugAssign | ast.AnnAssign):
                    objetivos = [nodo.target]
                for objetivo in objetivos:
                    if isinstance(objetivo, ast.Attribute) and objetivo.attr == "stock":
                        hallazgos.append(f"{ruta.name}:{funcion.name}")
                if (
                    isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                    and nodo.func.id == "setattr" and len(nodo.args) > 1
                    and isinstance(nodo.args[1], ast.Constant) and nodo.args[1].value == "stock"
                ):
                    hallazgos.append(f"{ruta.name}:{funcion.name}")
    return hallazgos


class TestSoloElPuntoUnicoAsignaStock:
    def test_solo_registrar_movimiento_asigna_el_stock_de_un_repuesto_existente(self):
        assert _asignaciones_a_stock(RAIZ) == ["repository.py:registrar_movimiento"]

    def test_el_detector_ve_una_asignacion_ajena(self, tmp_path):
        falso = tmp_path / "app" / "modulo.py"
        falso.parent.mkdir()
        falso.write_text(
            "def sumar(r):\n    r.stock += 1\n\n"
            "def fijar(r):\n    setattr(r, 'stock', 3)\n",
            encoding="utf-8",
        )
        assert _asignaciones_a_stock(tmp_path) == ["modulo.py:sumar", "modulo.py:fijar"]
