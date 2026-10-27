"""Dependencias compartidas: usuario actual, roles y el actor temporal (T-4).

`actor_temporal` es TEMPORAL hasta EJ-5 (T-4): como el login llega en EJ-4 y
`movimiento_stock.usuario_id` / `historial_precio_repuesto.usuario_id` son NOT
NULL, las escrituras de auditoría del EJ-3 se firman con el admin sembrado por
`seed.py`. En EJ-5 se reemplaza por `get_usuario_actual` y este grupo de rutas
pasa a estar protegido con `requiere_rol`.
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlmodel import col

from app.core.database import SesionDep
from app.core.errores import NoAutenticado
from app.core.security import TokenInvalido, verificar_token
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.schemas import IdentidadLectura
from app.modules.usuarios.service import obtener_identidad
from app.modules.usuarios.unit_of_work import UnitOfWorkUsuario


async def actor_temporal(sesion: SesionDep) -> Usuario:
    """Usuario `admin@example.com` (una fila del seed) como actor de auditoría."""
    resultado = await sesion.execute(
        select(Usuario).where(col(Usuario.email) == "admin@example.com")
    )
    usuario = resultado.scalars().first()
    if usuario is None:
        raise RuntimeError("Falta el usuario admin@example.com: corré `python seed.py`.")
    return usuario


ActorTemporalDep = Annotated[Usuario, Depends(actor_temporal)]


async def get_usuario_actual(request: Request, sesion: SesionDep) -> IdentidadLectura:
    """Cookie exclusivamente; esta dependencia construye el UoW sin abrirlo."""
    try:
        claims = verificar_token(request.cookies.get("access_token", ""), request.app.state.settings)
    except TokenInvalido as error:
        raise NoAutenticado(str(error)) from None
    return await obtener_identidad(UnitOfWorkUsuario(sesion), claims)


UsuarioActualDep = Annotated[IdentidadLectura, Depends(get_usuario_actual)]
