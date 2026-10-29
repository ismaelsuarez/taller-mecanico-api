"""`GET /estados-orden` (4.3, C-17, spec estados-orden): catálogo de sólo lectura por HTTP real."""

import pytest
from sqlalchemy import text

ESPERADO = [
    {"codigo": "PENDIENTE", "descripcion": "Esperando ser tomada por un mecánico", "posicion": 1, "es_final": False},
    {"codigo": "EN_REPARACION", "descripcion": "En curso de reparación", "posicion": 2, "es_final": False},
    {"codigo": "TERMINADA", "descripcion": "Reparación terminada", "posicion": 3, "es_final": True},
    {"codigo": "CANCELADA", "descripcion": "Orden cancelada", "posicion": 4, "es_final": True},
]


async def _filas_del_catalogo(motor) -> list[tuple]:
    async with motor.connect() as conn:
        resultado = await conn.execute(
            text("SELECT codigo, descripcion, posicion, es_final FROM estado_orden ORDER BY posicion")
        )
        return [tuple(fila) for fila in resultado.all()]


class TestConsulta:
    @pytest.mark.parametrize("email", ["admin@example.com", "cliente@example.com"])
    async def test_cualquier_usuario_autenticado_ve_los_cuatro_estados_por_posicion(
        self, api_autorizacion, abrir_sesion, email,
    ):
        async with abrir_sesion(email) as sesion:
            respuesta = await sesion.get("/estados-orden")

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json() == ESPERADO

    async def test_la_lista_sigue_el_orden_de_posicion_aunque_el_catalogo_cambie_de_orden_fisico(
        self, api_autorizacion, abrir_sesion,
    ):
        async with api_autorizacion.motor.begin() as conn:
            # Reescribir la fila mueve su posición física en la tabla: el orden debe seguir siendo lógico.
            await conn.execute(text("UPDATE estado_orden SET descripcion = descripcion WHERE codigo = 'PENDIENTE'"))
        async with abrir_sesion("admin@example.com") as sesion:
            respuesta = await sesion.get("/estados-orden")

        assert [e["posicion"] for e in respuesta.json()] == [1, 2, 3, 4]
        assert [e["codigo"] for e in respuesta.json()][0] == "PENDIENTE"

    async def test_sin_sesion_responde_401_sin_devolver_el_catalogo(self, api_autorizacion):
        respuesta = await api_autorizacion.cliente.get("/estados-orden")

        assert respuesta.status_code == 401
        assert "PENDIENTE" not in respuesta.text

    async def test_con_cambio_de_password_pendiente_responde_403(self, api_autorizacion, abrir_sesion):
        async with abrir_sesion("nuevo@example.com") as sesion:
            respuesta = await sesion.get("/estados-orden")

        assert respuesta.status_code == 403
        assert "PENDIENTE" not in respuesta.text


class TestElCatalogoNoSeEdita:
    @pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
    async def test_un_metodo_de_escritura_es_rechazado_y_el_catalogo_no_cambia(
        self, api_autorizacion, abrir_sesion, metodo,
    ):
        antes = await _filas_del_catalogo(api_autorizacion.motor)
        async with abrir_sesion("admin@example.com") as sesion:
            respuesta = await sesion.request(
                metodo, "/estados-orden",
                json={"codigo": "NUEVO", "descripcion": "x", "posicion": 9, "es_final": False},
            )

        assert respuesta.status_code == 405
        assert await _filas_del_catalogo(api_autorizacion.motor) == antes

    async def test_openapi_solo_publica_get_para_el_catalogo(self, api_autorizacion):
        respuesta = await api_autorizacion.cliente.get("/openapi.json")

        rutas = {r: set(ops) for r, ops in respuesta.json()["paths"].items() if r.startswith("/estados-orden")}
        assert rutas == {"/estados-orden": {"get"}}
