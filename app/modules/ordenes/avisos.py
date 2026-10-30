"""Aviso en segundo plano al terminar una orden (RT-TX-07, DD-07, US-024).

La tarea se agenda desde el router, DESPUÉS de que el servicio confirmó la
terminación (T-9), y Starlette la ejecuta cuando terminó de enviarse la
respuesta. Recibe datos planos tomados de la respuesta que ya salió: **no abre
sesión ni toca la base** (la sesión de la petición ya hizo su trabajo), y si el
proceso se reinicia en el medio segundo se pierde el aviso (sin reintento: DD-07).
"""

import asyncio
import logging

logger = logging.getLogger("app.ordenes.avisos")


async def avisar_cliente(orden_id: int, cliente: str) -> None:
    """Espera medio segundo sin bloquear el bucle y registra el aviso en español claro."""
    await asyncio.sleep(0.5)
    logger.info(
        "Aviso al cliente %s: la orden #%s terminó y ya puede retirar el vehículo.",
        cliente,
        orden_id,
    )
