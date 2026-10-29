"""Apoyo compartido por las pruebas HTTP de transiciones de órdenes (iniciar, cancelar, terminar)."""


async def instantanea(entorno) -> dict:
    """Todo lo que una transición podría tocar, leído por una conexión independiente."""
    return {
        "ordenes": [tuple(f) for f in await entorno.consulta(
            "SELECT id, estado, mecanico_id, total FROM orden_trabajo ORDER BY id")],
        "historial": [tuple(f) for f in await entorno.consulta(
            "SELECT id, orden_id, desde_estado, hasta_estado, usuario_id FROM historial_estado_orden ORDER BY id")],
        "stock": [tuple(f) for f in await entorno.consulta("SELECT id, stock FROM repuesto ORDER BY id")],
        "movimientos": [tuple(f) for f in await entorno.consulta(
            "SELECT id, repuesto_id, orden_id, cantidad FROM movimiento_stock ORDER BY id")],
    }


async def poner_estado(entorno, orden_id: int, estado: str) -> None:
    await entorno.ejecutar("UPDATE orden_trabajo SET estado = :e WHERE id = :i", e=estado, i=orden_id)


async def crear_orden(entorno, usuario: str, cuerpo: dict) -> int:
    async with entorno.entrar(usuario) as sesion:
        respuesta = await sesion.post("/ordenes", json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def linea_nueva(antes: dict, despues: dict) -> list[tuple]:
    return despues["historial"][len(antes["historial"]):]
