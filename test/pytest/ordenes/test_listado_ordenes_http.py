"""`GET /ordenes` (6.3, C-17, RT-PG-08): listado paginado y filtrable por estado, sobre el seed real."""

import pytest

PERSONAL = ["admin@example.com", "recepcion@example.com", "mecanico@example.com"]
ALTA = {"vehiculo_id": 1, "falla": "Otra falla", "items": [{"repuesto_id": 1, "cantidad": 1}]}


def _resumen(cuerpo: dict) -> list[tuple[int, str]]:
    return [(o["id"], o["estado"]) for o in cuerpo["items"]]


async def _crear_ordenes(entorno, cantidad: int) -> None:
    async with entorno.entrar("recepcion@example.com") as recepcion:
        for numero in range(cantidad):
            respuesta = await recepcion.post("/ordenes", json={**ALTA, "falla": f"Falla {numero}"})
            assert respuesta.status_code == 201, respuesta.text


class TestListado:
    @pytest.mark.parametrize("usuario", PERSONAL)
    async def test_el_personal_ve_las_dos_ordenes_del_seed_ordenadas_por_id(self, api_sembrada, usuario):
        async with api_sembrada.entrar(usuario) as sesion:
            respuesta = await sesion.get("/ordenes")

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert _resumen(cuerpo) == [(1, "PENDIENTE"), (2, "EN_REPARACION")]
        assert (cuerpo["total"], cuerpo["page"], cuerpo["size"], cuerpo["pages"]) == (2, 1, 20, 1)
        primera = cuerpo["items"][0]
        assert set(primera) == {"id", "vehiculo_id", "estado", "falla", "creada_en", "mecanico_id", "total"}
        assert (primera["vehiculo_id"], primera["falla"], primera["total"]) == (
            1, "Cambio de aceite y filtro", "56500.00",
        )
        assert cuerpo["items"][1]["mecanico_id"] == 4

    async def test_el_listado_incluye_las_ordenes_nuevas(self, api_sembrada):
        await _crear_ordenes(api_sembrada, 2)
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.get("/ordenes")

        assert [o["id"] for o in respuesta.json()["items"]] == [1, 2, 3, 4]
        assert respuesta.json()["total"] == 4


class TestFiltroPorEstado:
    @pytest.mark.parametrize(
        ("estado", "esperado"),
        [
            ("PENDIENTE", [(1, "PENDIENTE")]),
            ("EN_REPARACION", [(2, "EN_REPARACION")]),
            ("TERMINADA", []),
            ("CANCELADA", []),
        ],
    )
    async def test_cada_estado_filtra_y_total_cuenta_con_el_mismo_filtro(
        self, api_sembrada, estado, esperado,
    ):
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            respuesta = await recepcion.get("/ordenes", params={"estado": estado})

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert _resumen(cuerpo) == esperado
        assert cuerpo["total"] == len(esperado)
        assert cuerpo["pages"] == 1

    async def test_el_total_y_las_paginas_siguen_el_filtro_aunque_haya_mas_ordenes(self, api_sembrada):
        await _crear_ordenes(api_sembrada, 3)  # ahora hay 4 PENDIENTE (1, 3, 4, 5) y 1 EN_REPARACION
        async with api_sembrada.entrar("admin@example.com") as admin:
            primera = await admin.get("/ordenes", params={"estado": "PENDIENTE", "size": 2, "page": 1})
            segunda = await admin.get("/ordenes", params={"estado": "PENDIENTE", "size": 2, "page": 2})

        assert [o["id"] for o in primera.json()["items"]] == [1, 3]
        assert [o["id"] for o in segunda.json()["items"]] == [4, 5]
        assert (primera.json()["total"], primera.json()["pages"]) == (4, 2)

    async def test_sin_filtro_la_paginacion_cuenta_todas(self, api_sembrada):
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.get("/ordenes", params={"size": 1, "page": 2})

        assert _resumen(respuesta.json()) == [(2, "EN_REPARACION")]
        assert (respuesta.json()["total"], respuesta.json()["pages"]) == (2, 2)

    async def test_una_pagina_que_no_existe_responde_422(self, api_sembrada):
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.get("/ordenes", params={"page": 3, "size": 1})

        assert respuesta.status_code == 422
        assert respuesta.json() == {"detail": "La página 3 no existe: hay 2"}

    @pytest.mark.parametrize("estado", ["ARCHIVADA", "PERDIDA", "pendiente", "EN REPARACION"])
    async def test_c17_un_estado_no_declarado_responde_422_humano_sin_eco(self, api_sembrada, estado):
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            respuesta = await recepcion.get("/ordenes", params={"estado": estado})

        assert respuesta.status_code == 422
        assert respuesta.json() == {"detail": [{"msg": "Elegí un valor válido para el estado."}]}
        assert estado not in respuesta.text


class TestPermisos:
    async def test_el_cliente_recibe_403(self, api_sembrada):
        async with api_sembrada.entrar("cliente@example.com") as cliente:
            respuesta = await cliente.get("/ordenes")

        assert respuesta.status_code == 403
        assert "items" not in respuesta.json()

    async def test_sin_sesion_responde_401(self, api_sembrada):
        async with api_sembrada.anonimo() as anonimo:
            respuesta = await anonimo.get("/ordenes")

        assert respuesta.status_code == 401

    async def test_con_cambio_de_password_pendiente_responde_403(self, api_sembrada):
        async with api_sembrada.entrar("nuevo@example.com") as sesion:
            respuesta = await sesion.get("/ordenes")

        assert respuesta.status_code == 403

    async def test_mis_ordenes_conserva_su_contrato(self, api_sembrada):
        async with api_sembrada.entrar("cliente@example.com") as cliente:
            respuesta = await cliente.get("/mis-ordenes")

        assert respuesta.status_code == 200
        assert _resumen(respuesta.json()) == [(1, "PENDIENTE")]
        assert respuesta.json()["total"] == 1
