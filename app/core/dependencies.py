"""Dependencias compartidas: identidad, rol por petición y el cambio obligatorio.

Controles y su orden (D2):
1. `get_usuario_actual` — identidad por cookie; cualquier fallo → 401.
2. `cambio_pendiente_bloqueado` — montado una sola vez en el grupo protegido (main.py).
3. `requiere_rol(*roles)` — por ruta; consulta los roles vigentes en la base (D3) → 403.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.core.database import SesionDep
from app.core.errores import NoAutorizado, NoAutenticado
from app.core.security import TokenInvalido, verificar_token
from app.modules.usuarios.schemas import IdentidadLectura
from app.modules.usuarios.service import obtener_identidad, roles_vigentes
from app.modules.usuarios.unit_of_work import UnitOfWorkUsuario


async def get_usuario_actual(request: Request, sesion: SesionDep) -> IdentidadLectura:
    """Cookie exclusivamente; esta dependencia construye el UoW sin abrirlo."""
    try:
        claims = verificar_token(request.cookies.get("access_token", ""), request.app.state.settings)
    except TokenInvalido as error:
        raise NoAutenticado(str(error)) from None
    return await obtener_identidad(UnitOfWorkUsuario(sesion), claims)


UsuarioActualDep = Annotated[IdentidadLectura, Depends(get_usuario_actual)]


async def cambio_pendiente_bloqueado(identidad: UsuarioActualDep) -> IdentidadLectura:
    """Bloquea el grupo protegido si la contraseña obligatoria sigue pendiente (C-09)."""
    if identidad.usuario.debe_cambiar_password:
        raise NoAutorizado("Tenés que cambiar tu contraseña antes de continuar.")
    return identidad


def requiere_rol(*roles: str):
    """Dependencia de fábrica (D2): exige alguno de los roles vigentes en la base (D3).

    La identidad se resuelve primero (401 antes que cualquier 403) y los roles
    se consultan por petición, sin caché y sin mirar los roles del token.
    """
    if not roles:
        raise ValueError("requiere_rol necesita al menos un rol.")

    async def _dependencia(
        identidad: UsuarioActualDep, sesion: SesionDep,
    ) -> IdentidadLectura:
        vigentes = await roles_vigentes(UnitOfWorkUsuario(sesion), identidad.usuario.id)
        if not set(roles) & set(vigentes):
            raise NoAutorizado()
        return identidad

    return _dependencia
