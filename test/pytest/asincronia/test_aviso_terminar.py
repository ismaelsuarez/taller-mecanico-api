"""Aviso en segundo plano al terminar una orden (RT-TX-07, DD-07, C-12 / C-11).

C-12: la terminación confirmada agenda el aviso, que se registra DESPUÉS de enviarse
la respuesta. C-11: un 409 (o un 404) no deja ningún aviso en el registro.

Para comparar instantes se envuelve la aplicación con una capa que marca con
`time.time()` el instante en que sale el último trozo del cuerpo; el `LogRecord`
trae su propio `created`, que se compara contra esa marca.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

LOGGER_AVISOS = "app.ordenes.avisos"
MENSAJE_ESPERADO = "la orden #2 terminó y ya puede retirar el vehículo"


@asynccontextmanager
async def _cliente_marcando_respuesta(app) -> AsyncIterator[tuple[AsyncClient, list[float]]]:
    """Cliente httpx sobre el app real; devuelve también las marcas de envío de respuesta."""

    marcas: list[float] = []

    async def aplicacion_envoltura(scope, receive, send):
        async def send_marcado(mensaje) -> None:
            if mensaje.get("type") == "http.response.body" and not mensaje.get("more_body", False):
                marcas.append(time.time())
            await send(mensaje)

        await app(scope, receive, send_marcado)

    async with AsyncClient(
        transport=ASGITransport(app=aplicacion_envoltura), base_url="http://test",
    ) as cliente:
        yield cliente, marcas


async def _entrar(cliente: AsyncClient, email: str) -> None:
    from ordenes.conftest import _passwords_del_seed

    login = await cliente.post(
        "/auth/login", json={"email": email, "password": _passwords_del_seed()[email]},
    )
    assert login.status_code == 200, login.text


async def _reponer(api_sembrada, cantidad: int = 2) -> None:
    async with api_sembrada.entrar("admin@example.com") as admin:
        respuesta = await admin.post("/repuestos/3/reponer", json={"cantidad": cantidad})
    assert respuesta.status_code == 200, respuesta.text


def _avisos(caplog) -> list[logging.LogRecord]:
    return [registro for registro in caplog.records if registro.name == LOGGER_AVISOS]


async def test_c12_tras_terminar_queda_el_aviso_en_el_registro_y_despues_de_la_respuesta(
    api_sembrada, caplog,
):
    caplog.set_level(logging.INFO, logger=LOGGER_AVISOS)
    await _reponer(api_sembrada)
    async with _cliente_marcando_respuesta(api_sembrada.app) as (cliente, marcas):
        await _entrar(cliente, "mecanico@example.com")
        marcas.clear()  # sólo la marca de la respuesta de terminar
        respuesta = await cliente.post("/ordenes/2/terminar")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "TERMINADA"

    avisos = _avisos(caplog)
    assert avisos, "la terminación confirmada no dejó ningún aviso en el registro"
    assert "la orden #2 terminó" in avisos[0].getMessage()
    assert avisos[0].created > marcas[0], "el aviso se registró antes de enviar la respuesta"


async def test_c11_terminar_sin_stock_no_deja_aviso(api_sembrada, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_AVISOS)
    async with api_sembrada.entrar("mecanico@example.com") as mecanico:
        respuesta = await mecanico.post("/ordenes/2/terminar")

    assert respuesta.status_code == 409
    await asyncio.sleep(0.7)  # tiempo de que un aviso mal agendado tuviera lugar de aparecer
    assert not _avisos(caplog), "un 409 no debe agendar ningún aviso"


async def test_terminar_una_orden_inexistente_no_deja_aviso(api_sembrada, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_AVISOS)
    async with api_sembrada.entrar("mecanico@example.com") as mecanico:
        respuesta = await mecanico.post("/ordenes/999/terminar")

    assert respuesta.status_code == 404
    await asyncio.sleep(0.7)  # ídem: si algo quedara agendado, tendría tiempo de registrarse
    assert not _avisos(caplog), "un 404 no debe agendar ningún aviso"


async def test_sensibilidad_un_aviso_disparado_sin_confirmar_lo_detecta_el_caso_del_409(
    api_sembrada, caplog, monkeypatch,
):
    """Sensibilidad del 409: con un servicio que avisa sin importar el resultado, el assert fallaría.

    Simula el código malo que este change descarta (avisar dentro del servicio, sin depender de
    que la operación se confirme): envuelve `terminar_orden` para que registre el aviso ANTES de
    delegar, y el mismo test_c11 vería el aviso en el registro. Se anota aquí para que la
    aserción «no hay aviso con 409» nunca sea una afirmación vacía.
    """
    import app.modules.ordenes.router as router_ordenes
    from app.modules.ordenes.avisos import avisar_cliente

    terminar_real = router_ordenes.service.terminar_orden

    async def terminar_avisando_antes(uow, identidad, orden_id):
        await avisar_cliente(orden_id, "Cliente sin confirmar")
        return await terminar_real(uow, identidad, orden_id)

    monkeypatch.setattr(router_ordenes.service, "terminar_orden", terminar_avisando_antes)
    caplog.set_level(logging.INFO, logger=LOGGER_AVISOS)
    async with api_sembrada.entrar("mecanico@example.com") as mecanico:
        respuesta = await mecanico.post("/ordenes/2/terminar")

    assert respuesta.status_code == 409
    await asyncio.sleep(0.7)
    assert _avisos(caplog), "el detector no vería un aviso disparado sin confirmar (afirmación vacía)"
