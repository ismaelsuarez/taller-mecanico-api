"""Servicio mínimo del módulo ordenes (EJ-5): lo propio y el helper de dueño.

EJ-6 completa alta, iniciar, terminar y cancelar (RN-10..RN-14). El helper
`es_personal_o_dueno` queda documentado para el 403 de `GET /ordenes/{id}` y
de cancelar (T-8), sin anticipar esos endpoints.
"""

from app.core.paginacion import Pagina, pagina
from app.modules.ordenes.models import OrdenTrabajo
from app.modules.ordenes.schemas import EstadoOrdenLectura, OrdenResumenLectura
from app.modules.ordenes.unit_of_work import UnitOfWorkOrden
from app.modules.usuarios.schemas import IdentidadLectura

ROLES_DE_PERSONAL = ("ADMIN", "RECEPCION", "MECANICO")  # SU-03


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
