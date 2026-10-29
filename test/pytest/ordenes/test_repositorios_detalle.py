"""Repositorios de ítems e historial y el detalle precargado (3.3, D3, RT-TX-05, T-10).

PostgreSQL real migrada con Alembic. Para probar que no hay carga perezosa se
desprenden todas las instancias de la sesión: tocar una relación no precargada
lanzaría `DetachedInstanceError`, así que leer el detalle completo prueba que la
precarga está declarada dentro del método del repositorio.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.repository import BaseRepository
from app.modules.ordenes.models import HistorialEstadoOrden, ItemOrden
from app.modules.ordenes.repository import (
    HistorialEstadoOrdenRepository,
    ItemOrdenRepository,
    OrdenRepository,
)

from .conftest import Datos


async def _escenario_completo(sesion):
    """Orden de Laura con dos ítems (uno de un repuesto dado de baja) y dos líneas de historial."""
    datos = Datos(sesion)
    laura = await datos.usuario("laura@example.com")
    mecanico = await datos.usuario("mecanico@example.com")
    cliente = await datos.cliente("DNI-1", laura)
    vehiculo = await datos.vehiculo(cliente, "AA111AA")
    bujia = await datos.repuesto("BUJ-014", precio="1500.00")
    filtro = await datos.repuesto("FIL-007", precio="3200.50", de_baja=True)
    orden = await datos.orden(vehiculo, "EN_REPARACION", items=((bujia, 4), (filtro, 2)), mecanico=mecanico)
    base = datetime.now(UTC)
    sesion.add_all([
        HistorialEstadoOrden(
            orden_id=orden.id, desde_estado=None, hasta_estado="PENDIENTE",
            usuario_id=laura.id, cuando=base,
        ),
        HistorialEstadoOrden(
            orden_id=orden.id, desde_estado="PENDIENTE", hasta_estado="EN_REPARACION",
            usuario_id=mecanico.id, cuando=base + timedelta(minutes=5),
        ),
    ])
    await sesion.commit()
    return orden.id


class TestItemOrdenRepository:
    async def test_hereda_de_la_base_y_agrega_con_flush_sin_confirmar(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            orden = await datos.orden(await datos.vehiculo(await datos.cliente("DNI-1"), "AA111AA"))
            repuesto = await datos.repuesto("BUJ-014", precio="1500.00")
            await sesion.commit()
            orden_id, repuesto_id = orden.id, repuesto.id

            repo = ItemOrdenRepository(sesion)
            assert isinstance(repo, BaseRepository) and repo.modelo is ItemOrden
            item = await repo.add(ItemOrden(
                orden_id=orden_id, repuesto_id=repuesto_id, cantidad=3,
                precio_unitario=Decimal("1500.00"),
            ))
            assert item.id is not None
            await sesion.rollback()
        async with fabrica() as sesion:
            assert await ItemOrdenRepository(sesion).count() == 0


class TestHistorialEstadoOrdenRepository:
    async def test_solo_agrega_y_no_ofrece_update_ni_delete(self, fabrica):
        for nombre in ("update", "delete"):
            assert not hasattr(HistorialEstadoOrdenRepository, nombre), nombre
        assert not issubclass(HistorialEstadoOrdenRepository, BaseRepository)

        async with fabrica() as sesion:
            datos = Datos(sesion)
            usuario = await datos.usuario("recepcion@example.com")
            orden = await datos.orden(await datos.vehiculo(await datos.cliente("DNI-1"), "AA111AA"))
            await sesion.commit()
            orden_id = orden.id

            linea = await HistorialEstadoOrdenRepository(sesion).add(HistorialEstadoOrden(
                orden_id=orden_id, desde_estado=None, hasta_estado="PENDIENTE",
                usuario_id=usuario.id, cuando=datetime.now(UTC),
            ))
            assert linea.id is not None  # flush hecho
            await sesion.rollback()
        async with fabrica() as sesion:
            assert (await OrdenRepository(sesion).get_by_id(orden_id)) is not None
            detalle = await OrdenRepository(sesion).get_detalle_con_items_e_historial(orden_id)
            assert detalle is not None and detalle.historial_estados == []


class TestDetalleConItemsEHistorial:
    async def test_se_lee_completo_sin_carga_perezosa(self, fabrica):
        async with fabrica() as sesion:
            orden_id = await _escenario_completo(sesion)
        async with fabrica() as sesion:
            orden = await OrdenRepository(sesion).get_detalle_con_items_e_historial(orden_id)
            sesion.expunge_all()  # desde acá, cualquier relación sin precargar fallaría

            assert orden is not None
            assert orden.vehiculo.patente == "AA111AA"
            assert orden.vehiculo.cliente.documento == "DNI-1"
            por_codigo = {item.repuesto.codigo: item for item in orden.items}
            assert set(por_codigo) == {"BUJ-014", "FIL-007"}
            assert por_codigo["BUJ-014"].cantidad == 4
            assert por_codigo["FIL-007"].repuesto.borrado_en is not None  # dado de baja, DD-21
            lineas = sorted(orden.historial_estados, key=lambda h: (h.cuando, h.id))
            assert [(h.desde_estado, h.hasta_estado) for h in lineas] == [
                (None, "PENDIENTE"), ("PENDIENTE", "EN_REPARACION"),
            ]

    async def test_una_orden_sin_items_ni_historial_trae_listas_vacias(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            orden = await datos.orden(await datos.vehiculo(await datos.cliente("DNI-9"), "ZZ999ZZ"))
            await sesion.commit()
            orden_id = orden.id
        async with fabrica() as sesion:
            detalle = await OrdenRepository(sesion).get_detalle_con_items_e_historial(orden_id)
            sesion.expunge_all()
            assert detalle is not None
            assert detalle.items == [] and detalle.historial_estados == []
            assert detalle.vehiculo.cliente.documento == "DNI-9"

    async def test_una_orden_inexistente_devuelve_none(self, fabrica):
        async with fabrica() as sesion:
            assert await OrdenRepository(sesion).get_detalle_con_items_e_historial(999_999) is None

    async def test_refleja_items_e_historial_agregados_en_el_mismo_bloque(self, fabrica):
        async with fabrica() as sesion:
            datos = Datos(sesion)
            usuario = await datos.usuario("recepcion@example.com")
            vehiculo = await datos.vehiculo(await datos.cliente("DNI-1"), "AA111AA")
            repuesto = await datos.repuesto("BUJ-014", precio="1500.00")
            orden = await datos.orden(vehiculo)
            repo = OrdenRepository(sesion)

            antes = await repo.get_detalle_con_items_e_historial(orden.id)
            assert antes is not None and antes.items == [] and antes.historial_estados == []

            await ItemOrdenRepository(sesion).add(ItemOrden(
                orden_id=orden.id, repuesto_id=repuesto.id, cantidad=2,
                precio_unitario=Decimal("1500.00"),
            ))
            await HistorialEstadoOrdenRepository(sesion).add(HistorialEstadoOrden(
                orden_id=orden.id, desde_estado=None, hasta_estado="PENDIENTE",
                usuario_id=usuario.id, cuando=datetime.now(UTC),
            ))

            despues = await repo.get_detalle_con_items_e_historial(orden.id)
            assert despues is not None
            assert [(i.repuesto.codigo, i.cantidad) for i in despues.items] == [("BUJ-014", 2)]
            assert [h.hasta_estado for h in despues.historial_estados] == ["PENDIENTE"]
            await sesion.rollback()
