"""Registro/login públicos; cookie sólo después de las confirmaciones obligatorias."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import SesionDep
from app.core.errores import RespuestaAutenticacion
from app.core.security import emitir_token
from app.modules.usuarios import service
from app.modules.usuarios.schemas import LoginEntrada, RegistroEntrada, SesionLectura
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
    """Se entrega sin abrir; el servicio lo abre en fases cortas."""
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
    "/login", summary="Iniciar sesión por cookie",
    responses={
        401: {"model": RespuestaAutenticacion, "description": "Credenciales incorrectas o cuenta inactiva"},
        429: {
            "model": RespuestaAutenticacion, "description": "Demasiados intentos del mismo correo/IP",
            "headers": {"Retry-After": {
                "description": "Segundos hasta que salga el fallo vigente más antiguo; se reevalúa el límite.",
                "schema": {"type": "integer", "minimum": 1},
            }},
        },
    },
)
async def iniciar_sesion(
    datos: LoginEntrada, uow: UowUsuarioDep, intentos: UowIntentosDep,
    request: Request, response: Response,
) -> SesionLectura:
    settings = request.app.state.settings
    assert request.client is not None
    usuario_id, pendiente, roles = await service.iniciar_sesion(
        uow, intentos, datos, request.client.host, request.app.state.hash_ficticio,
    )
    poner_cookie_sesion(response, usuario_id, roles, settings)
    return SesionLectura(
        mensaje="Sesión iniciada", debe_cambiar_password=pendiente,
        expira_en_segundos=settings.access_token_expire_seconds,
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
