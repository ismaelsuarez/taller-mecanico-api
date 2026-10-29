"""Las consultas sobre `orden_trabajo` viven en `OrdenRepository` (3.2, D3, RT-TX-05).

La baja de vehículos (RN-16, C-19) y el helper de dueño (T-8) conservan su
contrato; sólo cambia el repositorio que responde.
"""

import pytest

from app.core.errores import EnConflicto
from app.modules.clientes.repository import VehiculoRepository
from app.modules.clientes.service import borrar_vehiculo
from app.modules.clientes.unit_of_work import UnitOfWorkCliente
from app.modules.ordenes.repository import OrdenRepository
from app.modules.ordenes.service import es_personal_o_dueno
from app.modules.ordenes.unit_of_work import UnitOfWorkOrden
from app.modules.usuarios.schemas import IdentidadLectura, UsuarioLectura

from .conftest import Datos


def _identidad(usuario_id: int, roles: list[str]) -> IdentidadLectura:
    return IdentidadLectura(
        usuario=UsuarioLectura(id=usuario_id, email="x@x", nombre="x", debe_cambiar_password=False),
        roles_vigentes=roles, roles_token=roles,
    )


def test_el_repositorio_de_vehiculos_ya_no_consulta_ordenes():
    assert not hasattr(VehiculoRepository, "tiene_ordenes_abiertas")


async def test_el_uow_de_clientes_compone_ordenes_con_la_misma_sesion(fabrica):
    async with fabrica() as sesion:
        uow = UnitOfWorkCliente(sesion)
        assert isinstance(uow.ordenes, OrdenRepository)
        assert uow.ordenes.sesion is sesion


class TestBajaDeVehiculoConOrdenesAbiertas:
    @pytest.mark.parametrize("estado", ["PENDIENTE", "EN_REPARACION"])
    async def test_con_una_orden_abierta_la_baja_es_un_conflicto(self, fabrica, estado):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            vehiculo = await datos.vehiculo(await datos.cliente("DNI-1"), "AA111AA")
            await datos.orden(vehiculo, estado)
            await sesion.commit()
            vehiculo_id = vehiculo.id  # el rollback del conflicto expira las instancias

            with pytest.raises(EnConflicto):
                await borrar_vehiculo(UnitOfWorkCliente(sesion), vehiculo_id)
        async with fabrica() as sesion:
            assert (await VehiculoRepository(sesion).get_by_id(vehiculo_id)) is not None

    @pytest.mark.parametrize("estado", ["TERMINADA", "CANCELADA"])
    async def test_con_ordenes_finales_la_baja_se_hace(self, fabrica, estado):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            vehiculo = await datos.vehiculo(await datos.cliente("DNI-1"), "AA111AA")
            await datos.orden(vehiculo, estado)
            await sesion.commit()
            vehiculo_id = vehiculo.id

            await borrar_vehiculo(UnitOfWorkCliente(sesion), vehiculo_id)
        async with fabrica() as sesion:
            repo = VehiculoRepository(sesion)
            assert await repo.get_by_id(vehiculo_id) is None
            assert (await repo.get_by_id_including_deleted(vehiculo_id)) is not None


class TestEsPersonalODueno:
    async def test_el_personal_pasa_el_dueno_pasa_y_el_ajeno_no(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            duenio = await datos.usuario("duenio@example.com")
            ajeno = await datos.usuario("ajeno@example.com")
            vehiculo = await datos.vehiculo(await datos.cliente("DNI-1", duenio), "AA111AA")
            orden = await datos.orden(vehiculo)
            await sesion.commit()

            uow = UnitOfWorkOrden(sesion)
            assert await es_personal_o_dueno(uow, _identidad(ajeno.id, ["MECANICO"]), orden) is True
            assert await es_personal_o_dueno(uow, _identidad(duenio.id, ["CLIENTE"]), orden) is True
            assert await es_personal_o_dueno(uow, _identidad(ajeno.id, ["CLIENTE"]), orden) is False

    async def test_el_dueno_pasa_aunque_el_vehiculo_este_dado_de_baja(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            duenio = await datos.usuario("duenio@example.com")
            vehiculo = await datos.vehiculo(
                await datos.cliente("DNI-1", duenio), "AA111AA", de_baja=True,
            )
            orden = await datos.orden(vehiculo, "TERMINADA")
            await sesion.commit()

            resultado = await es_personal_o_dueno(
                UnitOfWorkOrden(sesion), _identidad(duenio.id, ["CLIENTE"]), orden,
            )
            assert resultado is True
