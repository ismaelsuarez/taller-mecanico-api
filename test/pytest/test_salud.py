"""Spec salud-servicio: sondas de vida y de preparación."""

import asyncio
import socket

import pytest

from conftest import aplicacion_iniciada, cliente_http, leer_variable, requiere_base_de_test

CUERPO_NO_LISTO = {"estado": "no listo", "detalle": "La base de datos no está disponible en este momento."}


def puerto_libre() -> int:
    """Un puerto local donde no escucha nadie (simula una base inalcanzable)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ProxyTCP:
    """Proxy entre la app y la PostgreSQL real: apagarlo simula una base caída y prenderlo, que vuelve."""

    def __init__(self, host_destino: str, puerto_destino: int) -> None:
        self.host_destino = host_destino
        self.puerto_destino = puerto_destino
        self.puerto = puerto_libre()
        self._servidor: asyncio.Server | None = None
        self._conexiones: set[asyncio.StreamWriter] = set()

    async def prender(self) -> None:
        self._servidor = await asyncio.start_server(self._atender, "127.0.0.1", self.puerto)

    async def apagar(self) -> None:
        self._servidor.close()
        for escritor in list(self._conexiones):
            escritor.close()
        await self._servidor.wait_closed()

    async def _atender(self, lector_cliente, escritor_cliente) -> None:
        lector_base, escritor_base = await asyncio.open_connection(self.host_destino, self.puerto_destino)
        self._conexiones.update({escritor_cliente, escritor_base})

        async def copiar(lector, escritor):
            try:
                while datos := await lector.read(65536):
                    escritor.write(datos)
                    await escritor.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                escritor.close()

        await asyncio.gather(copiar(lector_cliente, escritor_base), copiar(lector_base, escritor_cliente))


@pytest.fixture
def base_inalcanzable(configurar_entorno):
    configurar_entorno(POSTGRES_HOST="127.0.0.1", POSTGRES_PORT=str(puerto_libre()))


@pytest.fixture
def base_disponible(configurar_entorno):
    requiere_base_de_test()
    configurar_entorno()


async def test_live_responde_200_con_la_base_disponible(base_disponible):
    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        respuesta = await cliente.get("/health/live")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "vivo"}


async def test_live_responde_200_con_la_base_caida(base_inalcanzable):
    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        respuesta = await cliente.get("/health/live")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "vivo"}


async def test_ready_responde_200_con_la_base_disponible(base_disponible):
    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        respuesta = await cliente.get("/health/ready")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "listo"}


async def test_ready_responde_503_con_la_base_inalcanzable(base_inalcanzable):
    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        respuesta = await cliente.get("/health/ready")

    assert respuesta.status_code == 503
    assert respuesta.json() == CUERPO_NO_LISTO


async def test_el_503_no_expone_informacion_interna(configurar_entorno):
    puerto = puerto_libre()
    configurar_entorno(POSTGRES_HOST="127.0.0.1", POSTGRES_PORT=str(puerto), POSTGRES_PASSWORD="pass-que-no-debe-verse")

    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        respuesta = await cliente.get("/health/ready")

    assert respuesta.status_code == 503
    texto = respuesta.text.lower()
    for fragmento in ("pass-que-no-debe-verse", str(puerto), "127.0.0.1", "postgresql", "asyncpg", "connect", "error"):
        assert fragmento not in texto


async def test_ready_repetido_mas_veces_que_el_pool_no_lo_agota(configurar_entorno):
    requiere_base_de_test()
    configurar_entorno(DB_POOL_SIZE="1")

    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        codigos = [(await cliente.get("/health/ready")).status_code for _ in range(15)]

    assert codigos == [200] * 15


async def test_ready_se_recupera_cuando_la_base_vuelve(configurar_entorno):
    requiere_base_de_test()
    proxy = ProxyTCP(leer_variable("POSTGRES_HOST") or "localhost", int(leer_variable("POSTGRES_PORT") or 5432))
    await proxy.prender()
    configurar_entorno(POSTGRES_HOST="127.0.0.1", POSTGRES_PORT=str(proxy.puerto), DB_POOL_SIZE="1")

    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        assert (await cliente.get("/health/ready")).status_code == 200

        await proxy.apagar()
        caida = [(await cliente.get("/health/ready")).status_code for _ in range(5)]

        await proxy.prender()
        recuperada = (await cliente.get("/health/ready")).status_code

    await proxy.apagar()
    assert caida == [503] * 5
    assert recuperada == 200


async def test_ready_responde_200_tras_un_reinicio_de_la_base_sin_peticiones_en_el_medio(configurar_entorno):
    """La conexión que quedó en el pool murió con el reinicio; la primera petición no debe fallar por eso."""
    requiere_base_de_test()
    proxy = ProxyTCP(leer_variable("POSTGRES_HOST") or "localhost", int(leer_variable("POSTGRES_PORT") or 5432))
    await proxy.prender()
    configurar_entorno(POSTGRES_HOST="127.0.0.1", POSTGRES_PORT=str(proxy.puerto), DB_POOL_SIZE="1")

    async with aplicacion_iniciada() as app, cliente_http(app) as cliente:
        assert (await cliente.get("/health/ready")).status_code == 200

        await proxy.apagar()
        await proxy.prender()
        despues_del_reinicio = (await cliente.get("/health/ready")).status_code

    await proxy.apagar()
    assert despues_del_reinicio == 200
