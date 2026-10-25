"""Hash de contraseñas con bcrypt fuera del bucle de eventos (EJ-1); token de sesión (EJ-4).

bcrypt tarda cientos de milisegundos a propósito: cada llamada corre en un hilo
(`asyncio.to_thread`) y bajo un semáforo que limita cuántas corren a la vez. El semáforo lo crea
el lifespan con `configurar_semaforo_bcrypt`, así los servicios lo comparten sin depender de la
petición.
"""

import asyncio

import bcrypt

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
    async with _obtener_semaforo():
        resultado = await asyncio.to_thread(bcrypt.hashpw, texto.encode(), bcrypt.gensalt(rounds=rondas))
    return resultado.decode()
