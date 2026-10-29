"""`UnitOfWorkOrden` compone todos sus repositorios con la misma sesión (3.4, D4)."""

import pytest

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import VehiculoRepository
from app.modules.ordenes.repository import (
    EstadoOrdenRepository,
    HistorialEstadoOrdenRepository,
    ItemOrdenRepository,
    OrdenRepository,
)
from app.modules.ordenes.unit_of_work import UnitOfWorkOrden
from app.modules.repuestos.repository import RepuestoRepository

COMPOSICION = {
    "ordenes": OrdenRepository,
    "items": ItemOrdenRepository,
    "historial": HistorialEstadoOrdenRepository,
    "estados": EstadoOrdenRepository,
    "vehiculos": VehiculoRepository,
    "repuestos": RepuestoRepository,
}


def test_es_un_unit_of_work():
    assert issubclass(UnitOfWorkOrden, UnitOfWork)


@pytest.mark.parametrize(("atributo", "clase"), COMPOSICION.items())
async def test_cada_repositorio_es_de_su_clase_y_usa_la_sesion_del_uow(fabrica, atributo, clase):
    async with fabrica() as sesion:
        repositorio = getattr(UnitOfWorkOrden(sesion), atributo)
        assert isinstance(repositorio, clase)
        assert repositorio.sesion is sesion


async def test_dos_unit_of_work_con_sesiones_distintas_no_comparten_repositorios(fabrica):
    async with fabrica() as una, fabrica() as otra:
        uow_uno, uow_otro = UnitOfWorkOrden(una), UnitOfWorkOrden(otra)
        for atributo in COMPOSICION:
            assert getattr(uow_uno, atributo).sesion is una
            assert getattr(uow_otro, atributo).sesion is otra
