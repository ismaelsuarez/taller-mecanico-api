"""Servicio del módulo ordenes: lo propio, el catálogo, el alta, el listado y el detalle.

EJ-6 completa el ciclo de vida (RN-10..RN-14). Cada función recibe el Unit of Work y lo
abre con `async with` (B-2); toda escritura de un caso de uso ocurre en ese único bloque
(RT-TX-04) y los errores son excepciones de dominio que la aplicación traduce a HTTP.
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.core.errores import EnConflicto, NoAutorizado, NoEncontrado
from app.core.paginacion import Pagina, pagina
from app.modules.ordenes.models import HistorialEstadoOrden, ItemOrden, OrdenTrabajo
from app.modules.ordenes.schemas import (
    EstadoOrdenCodigo,
    EstadoOrdenLectura,
    HistorialLectura,
    ID_MAXIMO,
    ItemOrdenLectura,
    OrdenCrear,
    OrdenDetalle,
    OrdenResumenLectura,
)
from app.modules.ordenes.unit_of_work import UnitOfWorkOrden
from app.modules.usuarios.schemas import IdentidadLectura

ROLES_DE_PERSONAL = ("ADMIN", "RECEPCION", "MECANICO")  # SU-03
# Tope de la columna `orden_trabajo.total`, NUMERIC(12,2): 9 999 999 999.99.
TOTAL_MAXIMO = Decimal("9999999999.99")


async def mis_ordenes(
    uow: UnitOfWorkOrden, usuario_id: int, page: int, size: int,
) -> Pagina[OrdenResumenLectura]:
    """Lo propio (RN-17, DD-28): todas las órdenes de los vehículos del usuario.

    Incluye las de vehículos dados de baja; sin ficha → página vacía (SU-11).
    """
    async with uow:
        cliente = await uow.ordenes.get_cliente_de_usuario(usuario_id)
        if cliente is None:
            items, total = [], 0
        else:
            items, total = await uow.ordenes.get_ordenes_de_cliente(
                cliente.id, page, size,
            )
    lectura = [
        OrdenResumenLectura.model_validate(o, from_attributes=True) for o in items
    ]
    return pagina(lectura, total, page, size)


async def listar_ordenes(
    uow: UnitOfWorkOrden, estado: EstadoOrdenCodigo | None, page: int, size: int,
) -> Pagina[OrdenResumenLectura]:
    """Listado del personal por id, con el filtro `estado` ya validado por el contrato (C-17)."""
    async with uow:
        items, total = await uow.ordenes.listar(
            estado.value if estado is not None else None, page, size,
        )
    lectura = [OrdenResumenLectura.model_validate(o, from_attributes=True) for o in items]
    return pagina(lectura, total, page, size)


async def obtener_orden(
    uow: UnitOfWorkOrden, identidad: IdentidadLectura, orden_id: int,
) -> OrdenDetalle:
    """Detalle: 404 si no existe, 403 si no es personal ni dueño del vehículo (D2, DD-27/28).

    Un id fuera del rango de la columna no puede existir: es un 404, nunca un error de la base.
    """
    async with uow:
        orden = None
        if 1 <= orden_id <= ID_MAXIMO:
            orden = await uow.ordenes.get_detalle_con_items_e_historial(orden_id)
        if orden is None:
            raise NoEncontrado("Orden no encontrada.")
        if not await es_personal_o_dueno(uow, identidad, orden):
            raise NoAutorizado("No tenés permiso para ver esta orden.")
        return armar_detalle(orden)


async def listar_estados(uow: UnitOfWorkOrden) -> list[EstadoOrdenLectura]:
    """El catálogo `estado_orden` por posición; sólo lectura (A-5, RN-19)."""
    async with uow:
        estados = await uow.estados.get_all_por_posicion()
    return [EstadoOrdenLectura.model_validate(e, from_attributes=True) for e in estados]


async def es_personal_o_dueno(
    uow: UnitOfWorkOrden, identidad: IdentidadLectura, orden: OrdenTrabajo,
) -> bool:
    """T-8/SU-03: el personal ve cualquier orden; el dueño sólo las suyas.

    La consulta del dueño vive en `OrdenRepository.es_dueno_del_vehiculo` (EJ-6, D3).
    """
    if set(ROLES_DE_PERSONAL) & set(identidad.roles_vigentes):
        return True
    return await uow.ordenes.es_dueno_del_vehiculo(identidad.usuario.id, orden.vehiculo_id)


def armar_detalle(orden: OrdenTrabajo) -> OrdenDetalle:
    """Detalle con la forma de la consigna a partir de la orden con su precarga (T-10).

    Ítems por id (orden de alta) e historial cronológico por `(cuando, id)`; el repositorio
    no ordena la colección, así que el orden se aplica acá (D1).
    """
    items = [
        ItemOrdenLectura(
            repuesto_id=item.repuesto_id,
            codigo=item.repuesto.codigo,
            descripcion=item.repuesto.descripcion,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            subtotal=item.cantidad * item.precio_unitario,
        )
        for item in sorted(orden.items, key=lambda i: i.id)
    ]
    historial = [
        HistorialLectura(
            desde_estado=linea.desde_estado,
            hasta_estado=linea.hasta_estado,
            usuario_id=linea.usuario_id,
            cuando=linea.cuando,
        )
        for linea in sorted(orden.historial_estados, key=lambda h: (h.cuando, h.id))
    ]
    return OrdenDetalle(
        id=orden.id,
        estado=orden.estado,
        patente=orden.vehiculo.patente,
        total=orden.total,
        creada_en=orden.creada_en,
        mecanico_id=orden.mecanico_id,
        falla=orden.falla,
        cliente=orden.vehiculo.cliente.nombre,
        items=items,
        historial=historial,
    )


async def crear_orden(
    uow: UnitOfWorkOrden, datos: OrdenCrear, usuario_id: int,
) -> OrdenDetalle:
    """Alta en un solo bloque (D6): orden, ítems con precio copiado e historial `null → PENDIENTE`.

    Cualquier 409 sale del bloque antes de la primera escritura o la deshace entera.
    """
    async with uow:
        pendiente = await uow.estados.get_by_codigo(EstadoOrdenCodigo.PENDIENTE.value)
        if pendiente is None:
            raise EnConflicto(
                "Todavía no se pueden crear órdenes: falta cargar los estados del taller."
            )
        if await uow.vehiculos.get_by_id(datos.vehiculo_id) is None:
            raise EnConflicto("El vehículo no existe o fue dado de baja.")

        pedidos = [item.repuesto_id for item in datos.items]
        vigentes = {r.id: r for r in await uow.repuestos.get_vigentes_por_ids(pedidos)}
        faltantes = [str(repuesto_id) for repuesto_id in pedidos if repuesto_id not in vigentes]
        if faltantes:
            raise EnConflicto(
                f"Estos repuestos no existen o fueron dados de baja: {', '.join(faltantes)}."
            )

        total = sum(
            (vigentes[item.repuesto_id].precio * item.cantidad for item in datos.items),
            Decimal("0.00"),
        )
        if total > TOTAL_MAXIMO:
            raise EnConflicto(
                "El total de la orden supera el máximo permitido: revisá las cantidades."
            )

        ahora = datetime.now(timezone.utc)
        orden = await uow.ordenes.add(OrdenTrabajo(
            vehiculo_id=datos.vehiculo_id, estado=pendiente.codigo, falla=datos.falla,
            creada_en=ahora, total=total,
        ))
        for item in datos.items:
            await uow.items.add(ItemOrden(
                orden_id=orden.id, repuesto_id=item.repuesto_id, cantidad=item.cantidad,
                precio_unitario=vigentes[item.repuesto_id].precio,
            ))
        await uow.historial.add(HistorialEstadoOrden(
            orden_id=orden.id, desde_estado=None, hasta_estado=pendiente.codigo,
            usuario_id=usuario_id, cuando=ahora,
        ))
        # Relectura con la precarga declarada: refleja los ítems y la línea recién agregados.
        completa = await uow.ordenes.get_detalle_con_items_e_historial(orden.id)
        return armar_detalle(completa)
