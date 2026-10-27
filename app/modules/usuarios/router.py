"""Registro público; la respuesta de sesión se emite sólo tras confirmar el UoW."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import SesionDep
from app.core.security import emitir_token
from app.modules.usuarios import service
from app.modules.usuarios.schemas import RegistroEntrada, SesionLectura
from app.modules.usuarios.unit_of_work import UnitOfWorkIntentoAcceso, UnitOfWorkUsuario

router = APIRouter(prefix="/auth", tags=["autenticación"])


def construir_uow(sesion: SesionDep) -> UnitOfWorkUsuario:
    return UnitOfWorkUsuario(sesion)


UowUsuarioDep = Annotated[UnitOfWorkUsuario, Depends(construir_uow)]


async def get_session_intentos(request: Request) -> AsyncIterator[AsyncSession]:
    # DD-19: otra sesión/transacción y una conexión adicional al consultar/escribir.
    # Sus intentos confirmados sobreviven al rollback de la petición normal.
    # Esta dependencia crea/cierra la sesión; el UoW nunca la cierra.
    async with request.app.state.fabrica_sesiones() as sesion:
        yield sesion


SesionIntentosDep = Annotated[AsyncSession, Depends(get_session_intentos)]


def construir_uow_intentos(sesion: SesionIntentosDep) -> UnitOfWorkIntentoAcceso:
    """Se entrega sin abrir; el servicio futuro lo abre en fases cortas."""
    return UnitOfWorkIntentoAcceso(sesion)


UowIntentosDep = Annotated[UnitOfWorkIntentoAcceso, Depends(construir_uow_intentos)]


def poner_cookie_sesion(
    respuesta: Response, usuario_id: int, roles: list[str], settings: Settings,
) -> None:
    """Reutilizable por login/cambio: el llamador ya confirmó su operación."""
    respuesta.set_cookie(
        "access_token", emitir_token(usuario_id, roles, settings),
        max_age=settings.access_token_expire_seconds, path="/",
        secure=settings.cookie_secure, httponly=True, samesite="lax",
    )


@router.post(
    "/registro", status_code=201,
    summary="Registrar cliente e iniciar sesión por cookie",
    responses={409: {"description": "Correo o documento ya registrado"}},
)
async def registrar_usuario(
    datos: RegistroEntrada, uow: UowUsuarioDep, request: Request, response: Response,
) -> SesionLectura:
    settings = request.app.state.settings
    usuario_id = await service.registrar_usuario(uow, datos, settings.bcrypt_rounds)
    poner_cookie_sesion(response, usuario_id, ["CLIENTE"], settings)
    return SesionLectura(
        mensaje="Registro completado", debe_cambiar_password=False,
        expira_en_segundos=settings.access_token_expire_seconds,
    )
