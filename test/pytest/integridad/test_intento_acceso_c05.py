"""C-05: los fallos de login quedan en `intento_acceso`, vistos desde otra sesión (EJ-7, spec autenticacion-sesiones).

Caracterización (design D9): el comportamiento ya existe y ya está probado por capas en `auth/`; no
hubo RED previo. Esta prueba lo mira de punta a punta con la API real sobre el seed y con un
observador que NO es la sesión de la API (`entorno.consulta` usa la conexión de la prueba): si la
fila de un intento rechazado se perdiera con el rollback de su petición, el observador no la vería.
Sensibilidad: el observador cuenta filas por correo, IP y orden de llegada, así que un intento
perdido, duplicado o marcado como exitoso cambia el resultado; el segundo caso (otro par
correo/IP) comprueba además que el bloqueo no se filtra a quien no corresponde.
"""

import secrets

import pytest
from httpx import ASGITransport, AsyncClient

from ordenes.conftest import _passwords_del_seed

CORREO = "admin@example.com"
IP_DE_LA_PRUEBA = "127.0.0.1"  # la que ve la API con el transporte ASGI por defecto
OTRA_IP = "192.0.2.2"
EVENTO_DE_BLOQUEO = "Login bloqueado por demasiados intentos"


async def _maximo(entorno, tabla: str) -> int:
    return (await entorno.consulta(f"SELECT coalesce(max(id), 0) FROM {tabla}"))[0][0]


async def _intentos_desde(entorno, previo: int):
    return await entorno.consulta(
        "SELECT email, ip, exito, cuando FROM intento_acceso WHERE id > :previo ORDER BY id", previo=previo,
    )


async def _eventos_desde(entorno, previo: int):
    return await entorno.consulta(
        "SELECT actor, accion FROM evento_seguridad WHERE id > :previo ORDER BY id", previo=previo,
    )


def _cliente_con_ip(app, ip: str) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, client=(ip, 1234)), base_url="http://test")


async def _login_fallido(cliente, email: str = CORREO):
    return await cliente.post("/auth/login", json={"email": email, "password": secrets.token_hex(16)})


@pytest.mark.asyncio
class TestC05IntentosObservables:
    async def test_cinco_fallos_y_el_bloqueo_quedan_en_intento_acceso_desde_otra_sesion(self, api_sembrada):
        intentos_previos = await _maximo(api_sembrada, "intento_acceso")
        eventos_previos = await _maximo(api_sembrada, "evento_seguridad")

        async with api_sembrada.anonimo() as cliente:
            codigos = [(await _login_fallido(cliente)).status_code for _ in range(5)]
            sexto = await _login_fallido(cliente)

        assert codigos == [401] * 5
        assert sexto.status_code == 429
        assert 1 <= int(sexto.headers["Retry-After"]) <= 60

        filas = await _intentos_desde(api_sembrada, intentos_previos)
        assert [(email, ip, exito) for email, ip, exito, _ in filas] == [(CORREO, IP_DE_LA_PRUEBA, False)] * 6
        fechas = [cuando for *_, cuando in filas]
        assert all(fechas) and fechas == sorted(fechas)  # con fecha y en el orden en que llegaron
        # Un único evento por el bloqueo, con el correo intentado como actor; los 401 no generan eventos.
        assert await _eventos_desde(api_sembrada, eventos_previos) == [(CORREO, EVENTO_DE_BLOQUEO)]

    async def test_otro_par_correo_ip_no_se_ve_afectado_por_el_bloqueo(self, api_sembrada):
        passwords = _passwords_del_seed()
        async with api_sembrada.anonimo() as cliente:
            for _ in range(5):
                assert (await _login_fallido(cliente)).status_code == 401
            assert (await _login_fallido(cliente)).status_code == 429
        previo = await _maximo(api_sembrada, "intento_acceso")
        eventos_previos = await _maximo(api_sembrada, "evento_seguridad")

        # Mismo correo desde otra IP: un 401 común, con su propia fila de otra IP (no un 429).
        async with _cliente_con_ip(api_sembrada.app, OTRA_IP) as otra_ip:
            assert (await _login_fallido(otra_ip)).status_code == 401
        # Otro correo desde la IP bloqueada, con su contraseña correcta: entra y anota un éxito.
        async with api_sembrada.anonimo() as cliente:
            entrada = await cliente.post(
                "/auth/login", json={"email": "recepcion@example.com", "password": passwords["recepcion@example.com"]},
            )
        assert entrada.status_code == 200, entrada.text

        filas = await _intentos_desde(api_sembrada, previo)
        assert [(email, ip, exito) for email, ip, exito, _ in filas] == [
            (CORREO, OTRA_IP, False),
            ("recepcion@example.com", IP_DE_LA_PRUEBA, True),
        ]
        assert await _eventos_desde(api_sembrada, eventos_previos) == []
