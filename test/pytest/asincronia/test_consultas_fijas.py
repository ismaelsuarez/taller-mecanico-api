"""Consultas fijas en el detalle de una orden (RT-TX-05/06, C-15, US-023).

Mide con el evento `before_cursor_execute` del motor las consultas que emite
`OrdenRepository.get_detalle_con_items_e_historial`: el conteo con 2 ítems debe
ser igual al de 4 ítems y no debe crecer con las líneas de historial. Las
mediciones usan una sesión propia cada una, así que no entra ruido de login ni
del pool (design D3). Caracterización con sensibilidad: una réplica del método
con una consulta extra por ítem (N+1) sí crece con los ítems.
"""

from datetime import UTC, datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.modules.clientes.models import Vehiculo
from app.modules.ordenes.models import HistorialEstadoOrden, ItemOrden, OrdenTrabajo
from app.modules.ordenes.repository import OrdenRepository
from app.modules.repuestos.models import Repuesto
from ordenes.conftest import Datos


async def _crear_escenario(fabrica) -> dict[str, int]:
    """Orden de 2 ítems, orden de 4 ítems y una de 2 ítems con historial largo."""
    async with fabrica() as sesion:
        datos = Datos(sesion)
        cliente = await datos.cliente("30111222")
        vehiculo = await datos.vehiculo(cliente, "AA111BB")
        repuestos = [await datos.repuesto(f"REP-{n:03d}") for n in range(1, 5)]
        orden_2 = await datos.orden(
            vehiculo, "PENDIENTE", items=((repuestos[0], 1), (repuestos[1], 2)),
        )
        orden_4 = await datos.orden(
            vehiculo, "PENDIENTE", items=tuple((repuesto, 1) for repuesto in repuestos),
        )
        orden_historial = await datos.orden(
            vehiculo, "EN_REPARACION", items=((repuestos[0], 1), (repuestos[1], 1)),
        )
        usuario = await datos.usuario("mecanico-de-prueba@example.com")
        transiciones = (
            (None, "PENDIENTE"),
            ("PENDIENTE", "EN_REPARACION"),
            ("EN_REPARACION", "TERMINADA"),
        )
        for desde, hasta in transiciones:
            sesion.add(HistorialEstadoOrden(
                orden_id=orden_historial.id, desde_estado=desde, hasta_estado=hasta,
                usuario_id=usuario.id, cuando=datetime.now(UTC),
            ))
        await sesion.commit()
        return {
            "orden_2_items": orden_2.id,
            "orden_4_items": orden_4.id,
            "orden_historial_largo": orden_historial.id,
        }


def _instalar_contador(motor) -> tuple[list[str], callable]:
    """(consultas, quitar_contador) sobre el motor sync del asíncrono."""
    consultas: list[str] = []

    def _antes(_conn, _cursor, statement, _parameters, _context, _executemany):
        consultas.append(statement)

    event.listen(motor.sync_engine, "before_cursor_execute", _antes)
    return consultas, lambda: event.remove(motor.sync_engine, "before_cursor_execute", _antes)


async def _contar_detalle(fabrica, motor, orden_id: int) -> int:
    """Consultas que emite una medición del detalle, en una sesión fresca."""
    consultas, quitar = _instalar_contador(motor)
    try:
        async with fabrica() as sesion:
            orden = await OrdenRepository(sesion).get_detalle_con_items_e_historial(orden_id)
            assert orden is not None, f"la orden {orden_id} del escenario no existe"
            assert orden.items and orden.vehiculo.cliente, "la precarga no trajo las relaciones"
    finally:
        quitar()
    return len(consultas)


async def _contar_detalle_con_n_mas_uno(fabrica, motor, orden_id: int) -> int:
    """Réplica del método con una consulta extra por ítem: el N+1 que el contador debe detectar."""

    async def _detalle_mas_una_consulta_por_item(sesion: AsyncSession, id_orden: int) -> OrdenTrabajo | None:
        resultado = await sesion.execute(
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == id_orden)
            .options(
                joinedload(OrdenTrabajo.vehiculo).joinedload(Vehiculo.cliente),
                selectinload(OrdenTrabajo.items).joinedload(ItemOrden.repuesto),
                selectinload(OrdenTrabajo.historial_estados),
            )
            .execution_options(populate_existing=True)
        )
        orden = resultado.scalars().first()
        if orden is not None:
            for item in orden.items:
                await sesion.execute(select(Repuesto).where(Repuesto.id == item.repuesto_id))
        return orden

    consultas, quitar = _instalar_contador(motor)
    try:
        async with fabrica() as sesion:
            await _detalle_mas_una_consulta_por_item(sesion, orden_id)
    finally:
        quitar()
    return len(consultas)


async def test_el_detalle_de_una_orden_tiene_numero_fijo_de_consultas(fabrica, base_migrada):
    """C-15: mismas consultas con 2 y con 4 ítems, y sin crecer con el historial."""
    ids = await _crear_escenario(fabrica)

    conteo_2_items = await _contar_detalle(fabrica, base_migrada, ids["orden_2_items"])
    conteo_4_items = await _contar_detalle(fabrica, base_migrada, ids["orden_4_items"])
    conteo_historial = await _contar_detalle(fabrica, base_migrada, ids["orden_historial_largo"])

    assert conteo_2_items == conteo_4_items, (
        f"el detalle con 4 ítems emitió {conteo_4_items} consultas y con 2 ítems {conteo_2_items}"
    )
    assert conteo_historial == conteo_2_items, (
        "el detalle creció con las líneas de historial "
        f"({conteo_historial} vs {conteo_2_items})"
    )


async def test_el_contador_detecta_un_n_mas_uno_por_item(fabrica, base_migrada):
    """Sensibilidad del contador: la réplica N+1 sí crece con los ítems."""
    ids = await _crear_escenario(fabrica)

    replicas_2_items = await _contar_detalle_con_n_mas_uno(fabrica, base_migrada, ids["orden_2_items"])
    replicas_4_items = await _contar_detalle_con_n_mas_uno(fabrica, base_migrada, ids["orden_4_items"])

    assert replicas_4_items == replicas_2_items + 2, (
        "la réplica N+1 no creció exactamente en una consulta por ítem extra: "
        f"{replicas_2_items} con 2 ítems, {replicas_4_items} con 4"
    )
