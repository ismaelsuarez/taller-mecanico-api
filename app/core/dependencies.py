"""Dependencias compartidas: usuario actual, roles y el actor temporal (T-4).

`actor_temporal` es TEMPORAL hasta EJ-5 (T-4): como el login llega en EJ-4 y
`movimiento_stock.usuario_id` / `historial_precio_repuesto.usuario_id` son NOT
NULL, las escrituras de auditoría del EJ-3 se firman con el admin sembrado por
`seed.py`. En EJ-5 se reemplaza por `get_usuario_actual` y este grupo de rutas
pasa a estar protegido con `requiere_rol`.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SesionDep
from app.modules.usuarios.models import Usuario


async def actor_temporal(sesion: SesionDep) -> Usuario:
    """Usuario `admin@example.com` (una fila del seed) como actor de auditoría."""
    resultado = await sesion.execute(
        select(Usuario).where(Usuario.email == "admin@example.com")
    )
    usuario = resultado.scalars().first()
    if usuario is None:
        raise RuntimeError("Falta el usuario admin@example.com: corré `python seed.py`.")
    return usuario


ActorTemporalDep = Annotated[Usuario, Depends(actor_temporal)]
