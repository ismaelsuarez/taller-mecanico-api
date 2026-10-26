"""Aplicación, lifespan y los dos grupos de rutas."""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.config import obtener_settings
from app.core.database import crear_fabrica_sesiones, crear_motor
from app.core.errores import registrar_traductores
from app.core.security import configurar_semaforo_bcrypt, hashear_password
from app.modules.clientes.router import router as router_clientes
from app.modules.health.router import router as router_salud
from app.modules.repuestos.router import router as router_repuestos


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

# Grupo abierto: salud, clientes, vehículos y repuestos y, desde EJ-4, /auth.
# El grupo protegido llega en EJ-5 (T-11).
rutas_abiertas = APIRouter()
rutas_abiertas.include_router(router_salud)
rutas_abiertas.include_router(router_clientes)
rutas_abiertas.include_router(router_repuestos)

app.include_router(rutas_abiertas)
