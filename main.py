"""Aplicación, lifespan y los dos grupos de rutas."""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from app.core.config import obtener_settings
from app.core.database import crear_fabrica_sesiones, crear_motor
from app.core.dependencies import cambio_pendiente_bloqueado
from app.core.errores import RespuestaValidacion, registrar_traductores
from app.core.security import configurar_semaforo_bcrypt, hashear_password
from app.modules.clientes.router import router as router_clientes
from app.modules.health.router import router as router_salud
from app.modules.ordenes.router import router as router_ordenes
from app.modules.repuestos.router import router as router_repuestos
from app.modules.usuarios.router import router as router_auth
from app.modules.usuarios.router import router_administracion


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = obtener_settings()
    motor = crear_motor(settings)
    # El motor se libera también si el arranque falla o se cancela después de crearlo.
    try:
        configurar_semaforo_bcrypt(settings.bcrypt_max_concurrency)

        app.state.settings = settings
        app.state.motor = motor
        app.state.fabrica_sesiones = crear_fabrica_sesiones(motor)
        # Hash de un texto cualquiera: el login lo usa con correos inexistentes para tardar lo mismo (RN-09).
        # No es un secreto; se calcula una sola vez al arrancar.
        app.state.hash_ficticio = await hashear_password(secrets.token_urlsafe(16), settings.bcrypt_rounds)
        yield
    finally:
        await motor.dispose()


app = FastAPI(title="Taller Mecánico API", lifespan=lifespan)
# Excepciones de dominio → 404/409 con mensaje propio (D8, RN-18).
registrar_traductores(app)

# Grupo abierto: salud y /auth (login, identidad y cambio obligatorio: C-09).
rutas_abiertas = APIRouter()
rutas_abiertas.include_router(router_salud)
rutas_abiertas.include_router(router_auth, responses={422: {"model": RespuestaValidacion}})

# Grupo protegido: clientes/vehículos, repuestos, administración de personal y
# lo propio, con la matriz RBAC por ruta. El cambio de contraseña pendiente
# bloquea todo el grupo (C-09, D2, DD-10).
rutas_protegidas = APIRouter(dependencies=[Depends(cambio_pendiente_bloqueado)])
rutas_protegidas.include_router(
    router_clientes, responses={422: {"model": RespuestaValidacion}}
)
rutas_protegidas.include_router(
    router_repuestos, responses={422: {"model": RespuestaValidacion}}
)
rutas_protegidas.include_router(
    router_administracion, responses={422: {"model": RespuestaValidacion}}
)
rutas_protegidas.include_router(
    router_ordenes, responses={422: {"model": RespuestaValidacion}}
)

app.include_router(rutas_abiertas)
app.include_router(rutas_protegidas)
