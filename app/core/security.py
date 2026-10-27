"""Hash de contraseñas con bcrypt fuera del bucle de eventos (EJ-1); token de sesión (EJ-4).

bcrypt tarda cientos de milisegundos a propósito: cada llamada corre en un hilo
(`asyncio.to_thread`) y bajo un semáforo que limita cuántas corren a la vez. El semáforo lo crea
el lifespan con `configurar_semaforo_bcrypt`, así los servicios lo comparten sin depender de la
petición.
"""

import asyncio
import math
from datetime import UTC, datetime
from typing import TypedDict

import bcrypt
import jwt

from app.core.config import Settings

_semaforo: asyncio.Semaphore | None = None


def configurar_semaforo_bcrypt(max_concurrencia: int) -> None:
    global _semaforo
    _semaforo = asyncio.Semaphore(max_concurrencia)


def _obtener_semaforo() -> asyncio.Semaphore:
    if _semaforo is None:
        raise RuntimeError(
            "El semáforo de bcrypt no está configurado: el lifespan debe llamar a configurar_semaforo_bcrypt()."
        )
    return _semaforo


async def hashear_password(texto: str, rondas: int) -> str:
    def calcular() -> bytes:
        return bcrypt.hashpw(texto.encode(), bcrypt.gensalt(rounds=rondas))

    async with _obtener_semaforo():
        resultado = await asyncio.to_thread(calcular)
    return resultado.decode()


async def verificar_password(texto: str, password_hash: str) -> bool:
    """Mismo trabajo para un hash real o el ficticio ya creado por el lifespan."""
    async with _obtener_semaforo():
        return await asyncio.to_thread(bcrypt.checkpw, texto.encode(), password_hash.encode())


class ClaimsSesion(TypedDict):
    sub: str
    iat: float
    exp: float
    roles: list[str]


class TokenInvalido(ValueError):
    """Rechazo de sesión sin detalles criptográficos ni datos del token."""

    def __init__(self) -> None:
        super().__init__("La sesión no es válida. Volvé a iniciar sesión.")


def verificar_token(token: str, settings: Settings) -> ClaimsSesion:
    """Validar firma y claims; devolver los NumericDate originales, sin coerción."""
    try:
        claims = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=[settings.jwt_algorithm],
            options={
                "require": ["sub", "iat", "exp", "roles"],
                # PyJWT trunca estos tiempos a int: se validan abajo sin perder fracciones.
                "verify_iat": False, "verify_exp": False, "verify_aud": False,
            },
        )
        sub, roles = claims["sub"], claims["roles"]
        if not isinstance(sub, str) or not sub.isascii() or not sub.isdecimal() or int(sub) <= 0:
            raise TokenInvalido()
        if not isinstance(roles, list) or not all(isinstance(rol, str) for rol in roles):
            raise TokenInvalido()
        for campo in ("iat", "exp"):
            valor = claims[campo]
            if type(valor) not in (int, float) or not math.isfinite(valor):
                raise TokenInvalido()
        ahora = datetime.now(UTC).timestamp()
        if claims["iat"] > ahora or claims["exp"] <= ahora:
            raise TokenInvalido()
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
        raise TokenInvalido() from None
    return {
        "sub": claims["sub"], "iat": claims["iat"], "exp": claims["exp"], "roles": claims["roles"],
    }


def emitir_token(
    usuario_id: int, roles: list[str], settings: Settings, *, emitido_en: datetime | None = None,
) -> str:
    """Emitir tras confirmar el UoW; la marca no debe anteceder al cambio persistido."""
    instante = emitido_en if emitido_en is not None else datetime.now(UTC)
    if instante.utcoffset() is None:
        raise ValueError("La fecha de emisión debe incluir zona horaria.")
    iat = instante.timestamp()
    return jwt.encode(
        {"sub": str(usuario_id), "iat": iat,
         "exp": iat + settings.access_token_expire_seconds, "roles": roles},
        settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm,
    )
