"""Registro/login públicos; cookie sólo después de las confirmaciones obligatorias.

`router_administracion` cubre el alta de personal, la gestión de roles y los
eventos de seguridad (EJ-5): todas sus rutas exigen el rol ADMIN vigente.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import SesionDep
from app.core.dependencies import UsuarioActualDep, requiere_rol
from app.core.errores import RespuestaAutenticacion
from app.core.paginacion import Pagina, ParametrosPagina
from app.core.security import emitir_token
from app.modules.usuarios import service
from app.modules.usuarios.schemas import (
    AltaPersonalEntrada,
    AsignacionRolEntrada,
    CambioPasswordEntrada,
    EventoLectura,
    IdentidadLectura,
    LoginEntrada,
    MensajeLectura,
    RegistroEntrada,
    RolAsignadoLectura,
    RolesAsignadosLectura,
    SesionLectura,
    UsuarioLectura,
)
from app.modules.usuarios.unit_of_work import UnitOfWorkIntentoAcceso, UnitOfWorkUsuario

router = APIRouter(prefix="/auth", tags=["autenticación"])

SoloAdministracion = Annotated[IdentidadLectura, Depends(requiere_rol("ADMIN"))]
RequiereAdministracion = Depends(requiere_rol("ADMIN"))


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
    *, emitido_en: datetime | None = None,
) -> None:
    """Reutilizable por login/cambio: el llamador ya confirmó su operación."""
    respuesta.set_cookie(
        "access_token", emitir_token(usuario_id, roles, settings, emitido_en=emitido_en),
        max_age=settings.access_token_expire_seconds, path="/",
        secure=settings.cookie_secure, httponly=True, samesite="lax",
    )


@router.post(
    "/cambiar-password", summary="Cambiar contraseña y reemplazar la cookie tras confirmar",
    responses={401: {"model": RespuestaAutenticacion,
                     "description": "Sesión no válida o contraseña actual incorrecta"}},
)
async def cambiar_password(
    datos: CambioPasswordEntrada, usuario: UsuarioActualDep, uow: UowUsuarioDep,
    request: Request, response: Response,
) -> SesionLectura:
    settings = request.app.state.settings
    cambio, roles = await service.cambiar_password(
        uow, usuario.usuario.id, datos, settings.bcrypt_rounds,
    )
    poner_cookie_sesion(response, usuario.usuario.id, roles, settings, emitido_en=cambio)
    return SesionLectura(
        mensaje="Contraseña actualizada", debe_cambiar_password=False,
        expira_en_segundos=settings.access_token_expire_seconds,
    )


@router.post("/logout", summary="Cerrar sesión eliminando la cookie; no requiere sesión válida")
async def cerrar_sesion(request: Request, response: Response) -> MensajeLectura:
    response.delete_cookie(
        "access_token", path="/", secure=request.app.state.settings.cookie_secure,
        httponly=True, samesite="lax",
    )
    return MensajeLectura(mensaje="Sesión cerrada")


@router.get(
    "/yo", summary="Consultar identidad por cookie (no acepta Bearer)",
    responses={401: {"model": RespuestaAutenticacion, "description": "Sesión ausente o no válida"}},
)
async def obtener_identidad(usuario: UsuarioActualDep) -> IdentidadLectura:
    return usuario


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


# --- Administración de personal y roles (EJ-5) ---


router_administracion = APIRouter(
    tags=["administración"],
    dependencies=[RequiereAdministracion],
)


@router_administracion.post(
    "/usuarios", status_code=201, response_model=UsuarioLectura,
    summary="Alta de personal con contraseña provisoria (ADMIN)",
    responses={409: {"description": "Correo ya registrado"}},
)
async def crear_personal(
    datos: AltaPersonalEntrada,
    identidad: SoloAdministracion,
    uow: UowUsuarioDep,
    request: Request,
) -> UsuarioLectura:
    return await service.alta_personal(
        uow, datos, identidad.usuario.id, identidad.usuario.email,
        request.app.state.settings.bcrypt_rounds,
    )


@router_administracion.get(
    "/usuarios/{usuario_id}/roles", response_model=RolesAsignadosLectura,
    summary="Roles vigentes de un usuario (ADMIN)",
)
async def obtener_roles(usuario_id: int, uow: UowUsuarioDep) -> RolesAsignadosLectura:
    return await service.listar_roles_usuario(uow, usuario_id)


@router_administracion.post(
    "/usuarios/{usuario_id}/roles", status_code=201, response_model=RolAsignadoLectura,
    summary="Asignar un rol con vencimiento opcional (ADMIN)",
    responses={409: {"description": "El usuario ya tiene ese rol vigente"}},
)
async def asignar_rol_a_usuario(
    usuario_id: int,
    datos: AsignacionRolEntrada,
    identidad: SoloAdministracion,
    uow: UowUsuarioDep,
) -> RolAsignadoLectura:
    return await service.asignar_rol(
        uow, usuario_id, datos, identidad.usuario.id, identidad.usuario.email,
    )


@router_administracion.delete(
    "/usuarios/{usuario_id}/roles/{rol}", response_model=MensajeLectura,
    summary="Revocar un rol sin borrar la fila (ADMIN)",
    responses={409: {"description": "Autoprotección o último administrador"}},
)
async def revocar_rol_de_usuario(
    usuario_id: int,
    rol: str,
    identidad: SoloAdministracion,
    uow: UowUsuarioDep,
) -> MensajeLectura:
    return await service.revocar_rol(
        uow, usuario_id, rol, identidad.usuario.id, identidad.usuario.email,
    )


@router_administracion.get(
    "/eventos", response_model=Pagina[EventoLectura],
    summary="Eventos de seguridad paginados (ADMIN)",
)
async def obtener_eventos(
    uow: UowUsuarioDep,
    params: Annotated[ParametrosPagina, Query()],
) -> Pagina[EventoLectura]:
    return await service.listar_eventos(uow, params.page, params.size)
