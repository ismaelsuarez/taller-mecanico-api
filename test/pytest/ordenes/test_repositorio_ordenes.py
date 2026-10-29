"""Consultas de `OrdenRepository` reubicadas desde servicios y `VehiculoRepository` (3.1, D3).

Contra PostgreSQL real migrada con Alembic: el dueño de un vehículo (también
dado de baja, DD-28) y las órdenes abiertas según `es_final` del catálogo (RN-16).
"""

import pytest

from app.modules.ordenes.repository import OrdenRepository

from .conftest import Datos


class TestEsDuenoDelVehiculo:
    async def test_el_dueno_lo_es_y_un_ajeno_no(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            duenio = await datos.usuario("duenio@example.com")
            ajeno = await datos.usuario("ajeno@example.com")
            vehiculo = await datos.vehiculo(await datos.cliente("DNI-1", duenio), "AA111AA")
            await datos.cliente("DNI-2", ajeno)
            await sesion.commit()

            repo = OrdenRepository(sesion)
            assert await repo.es_dueno_del_vehiculo(duenio.id, vehiculo.id) is True
            assert await repo.es_dueno_del_vehiculo(ajeno.id, vehiculo.id) is False

    async def test_un_usuario_sin_ficha_o_un_vehiculo_inexistente_no_cuentan(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            duenio = await datos.usuario("duenio@example.com")
            sin_ficha = await datos.usuario("sinficha@example.com")
            vehiculo = await datos.vehiculo(await datos.cliente("DNI-1", duenio), "AA111AA")
            await sesion.commit()

            repo = OrdenRepository(sesion)
            assert await repo.es_dueno_del_vehiculo(sin_ficha.id, vehiculo.id) is False
            assert await repo.es_dueno_del_vehiculo(duenio.id, 999_999) is False

    async def test_el_dueno_lo_sigue_siendo_con_el_vehiculo_dado_de_baja(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            duenio = await datos.usuario("duenio@example.com")
            vehiculo = await datos.vehiculo(
                await datos.cliente("DNI-1", duenio), "AA111AA", de_baja=True,
            )
            await sesion.commit()

            assert await OrdenRepository(sesion).es_dueno_del_vehiculo(duenio.id, vehiculo.id) is True


class TestTieneAbiertasDelVehiculo:
    @pytest.mark.parametrize(
        ("estados", "esperado"),
        [
            (("PENDIENTE",), True),
            (("EN_REPARACION",), True),
            (("TERMINADA",), False),
            (("CANCELADA",), False),
            (("TERMINADA", "CANCELADA"), False),
            (("TERMINADA", "PENDIENTE"), True),
            ((), False),
        ],
    )
    async def test_abierta_es_la_que_el_catalogo_no_marca_como_final(
        self, fabrica, estados, esperado,
    ):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            vehiculo = await datos.vehiculo(await datos.cliente("DNI-1"), "AA111AA")
            for estado in estados:
                await datos.orden(vehiculo, estado)
            await sesion.commit()

            assert await OrdenRepository(sesion).tiene_abiertas_del_vehiculo(vehiculo.id) is esperado

    async def test_las_ordenes_abiertas_de_otro_vehiculo_no_cuentan(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            cliente = await datos.cliente("DNI-1")
            con_orden = await datos.vehiculo(cliente, "AA111AA")
            sin_orden = await datos.vehiculo(cliente, "BB222BB")
            await datos.orden(con_orden, "PENDIENTE")
            await sesion.commit()

            repo = OrdenRepository(sesion)
            assert await repo.tiene_abiertas_del_vehiculo(con_orden.id) is True
            assert await repo.tiene_abiertas_del_vehiculo(sin_orden.id) is False
