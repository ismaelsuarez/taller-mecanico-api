"""`EstadoOrdenRepository`: catálogo de sólo lectura (4.1, A-5, RN-19, spec estados-orden).

Contra PostgreSQL real migrada con Alembic. Los casos de estructura (sin herencia, sin
escrituras) auditan un esqueleto que ya cumplía la forma: no tienen RED observable y
fijan el contrato; las lecturas sí nacen con RED (`AttributeError`).
"""

import inspect

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.ordenes.models import EstadoOrden
from app.modules.ordenes.repository import EstadoOrdenRepository

CODIGOS_POR_POSICION = ["PENDIENTE", "EN_REPARACION", "TERMINADA", "CANCELADA"]


class TestEstructuraDeSoloLectura:
    def test_no_hereda_de_ninguna_jerarquia_de_repositorios(self):
        assert not issubclass(EstadoOrdenRepository, BaseRepository)
        assert not issubclass(EstadoOrdenRepository, SoftDeleteRepository)

    @pytest.mark.parametrize("metodo", ["add", "update", "delete", "soft_delete", "get_by_id"])
    def test_no_ofrece_escrituras_ni_lecturas_por_id(self, metodo):
        assert not hasattr(EstadoOrdenRepository, metodo)

    def test_sus_lecturas_son_asincronicas(self):
        for nombre in ("get_all_por_posicion", "get_by_codigo"):
            assert inspect.iscoroutinefunction(getattr(EstadoOrdenRepository, nombre))


class TestGetAllPorPosicion:
    async def test_con_el_catalogo_cargado_vuelve_por_posicion(self, fabrica):
        async with fabrica() as sesion:
            estados = await EstadoOrdenRepository(sesion).get_all_por_posicion()

        assert [e.codigo for e in estados] == CODIGOS_POR_POSICION
        assert [e.posicion for e in estados] == [1, 2, 3, 4]
        assert [e.es_final for e in estados] == [False, False, True, True]
        assert all(isinstance(e, EstadoOrden) for e in estados)

    async def test_ordena_por_posicion_aunque_se_haya_insertado_desordenado(self, base_migrada):
        filas = [("CANCELADA", 4, True), ("PENDIENTE", 1, False), ("TERMINADA", 3, True),
                 ("EN_REPARACION", 2, False)]
        async with base_migrada.begin() as conn:
            for codigo, posicion, es_final in filas:
                await conn.execute(
                    text("INSERT INTO estado_orden (codigo, descripcion, posicion, es_final) "
                         "VALUES (:c, 'x', :p, :f)"),
                    {"c": codigo, "p": posicion, "f": es_final},
                )

        async with async_sessionmaker(base_migrada)() as sesion:
            estados = await EstadoOrdenRepository(sesion).get_all_por_posicion()

        assert [e.codigo for e in estados] == CODIGOS_POR_POSICION

    async def test_con_el_catalogo_vacio_devuelve_una_lista_vacia(self, base_migrada):
        async with async_sessionmaker(base_migrada)() as sesion:
            assert await EstadoOrdenRepository(sesion).get_all_por_posicion() == []


class TestGetByCodigo:
    @pytest.mark.parametrize(
        ("codigo", "posicion", "es_final"),
        [("PENDIENTE", 1, False), ("TERMINADA", 3, True)],
    )
    async def test_devuelve_el_estado_pedido(self, fabrica, codigo, posicion, es_final):
        async with fabrica() as sesion:
            estado = await EstadoOrdenRepository(sesion).get_by_codigo(codigo)

        assert estado is not None
        assert (estado.codigo, estado.posicion, estado.es_final) == (codigo, posicion, es_final)

    @pytest.mark.parametrize("codigo", ["INVENTADO", "pendiente", ""])
    async def test_un_codigo_que_no_esta_en_el_catalogo_devuelve_nulo(self, fabrica, codigo):
        async with fabrica() as sesion:
            assert await EstadoOrdenRepository(sesion).get_by_codigo(codigo) is None

    async def test_con_el_catalogo_vacio_devuelve_nulo(self, base_migrada):
        async with async_sessionmaker(base_migrada)() as sesion:
            assert await EstadoOrdenRepository(sesion).get_by_codigo("PENDIENTE") is None
