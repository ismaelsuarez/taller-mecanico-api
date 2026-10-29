"""`GET /ordenes/{id}` (6.4, C-06, DD-21, DD-27, DD-28): detalle y quién lo ve, sobre el seed real."""

import pytest

DETALLE_ORDEN_2 = {
    "id": 2, "estado": "EN_REPARACION", "patente": "ZZ999YY", "total": "26000.00",
    "mecanico_id": 4, "falla": "Falla de encendido", "cliente": "Jorge Sin Cuenta",
    "items": [{
        "repuesto_id": 3, "codigo": "BUJ-014", "descripcion": "Bujía de encendido",
        "cantidad": 4, "precio_unitario": "6500.00", "subtotal": "26000.00",
    }],
    "historial": [
        {"desde_estado": None, "hasta_estado": "PENDIENTE", "usuario_id": 3},
        {"desde_estado": "PENDIENTE", "hasta_estado": "EN_REPARACION", "usuario_id": 4},
    ],
}


def _sin_fechas(cuerpo: dict) -> dict:
    cuerpo = dict(cuerpo)
    assert cuerpo.pop("creada_en")
    assert all(h["cuando"] for h in cuerpo["historial"])
    cuerpo["historial"] = [{k: v for k, v in h.items() if k != "cuando"} for h in cuerpo["historial"]]
    return cuerpo


class TestDetalleCompleto:
    @pytest.mark.parametrize("usuario", ["admin@example.com", "recepcion@example.com", "mecanico2@example.com"])
    async def test_el_personal_ve_la_orden_2_con_items_y_historial_cronologico(self, api_sembrada, usuario):
        async with api_sembrada.entrar(usuario) as sesion:
            respuesta = await sesion.get("/ordenes/2")

        assert respuesta.status_code == 200, respuesta.text
        assert _sin_fechas(respuesta.json()) == DETALLE_ORDEN_2

    async def test_otra_orden_da_otro_detalle(self, api_sembrada):
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.get("/ordenes/1")

        cuerpo = _sin_fechas(respuesta.json())
        assert (cuerpo["id"], cuerpo["estado"], cuerpo["patente"], cuerpo["cliente"]) == (
            1, "PENDIENTE", "AA111BB", "Laura Cliente",
        )
        assert cuerpo["mecanico_id"] is None
        assert [(i["codigo"], i["cantidad"], i["subtotal"]) for i in cuerpo["items"]] == [
            ("FIL-001", 1, "8500.00"), ("ACE-530", 4, "48000.00"),
        ]
        assert cuerpo["total"] == "56500.00"

    async def test_el_historial_sale_en_orden_cronologico_aunque_se_haya_insertado_despues(self, api_sembrada):
        await api_sembrada.ejecutar(
            "INSERT INTO historial_estado_orden (orden_id, desde_estado, hasta_estado, usuario_id, cuando) "
            "VALUES (1, NULL, 'PENDIENTE', 1, now() - interval '2 days')"
        )
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.get("/ordenes/1")

        historial = respuesta.json()["historial"]
        assert [h["usuario_id"] for h in historial] == [1, 3]  # el más viejo primero, no el de menor id

    async def test_con_la_misma_marca_de_tiempo_desempata_por_id(self, api_sembrada):
        await api_sembrada.ejecutar(
            "INSERT INTO historial_estado_orden (orden_id, desde_estado, hasta_estado, usuario_id, cuando) VALUES "
            "(1, 'PENDIENTE', 'EN_REPARACION', 5, '2000-01-01T00:00:00Z'), "
            "(1, 'EN_REPARACION', 'TERMINADA', 4, '2000-01-01T00:00:00Z')"
        )
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.get("/ordenes/1")

        assert [h["usuario_id"] for h in respuesta.json()["historial"]] == [5, 4, 3]

    async def test_un_repuesto_dado_de_baja_sigue_apareciendo_en_el_detalle(self, api_sembrada):
        async with api_sembrada.entrar("admin@example.com") as admin:
            assert (await admin.delete("/repuestos/3")).status_code == 204
            respuesta = await admin.get("/ordenes/2")

        assert respuesta.status_code == 200
        assert respuesta.json()["items"][0]["codigo"] == "BUJ-014"
        assert respuesta.json()["items"][0]["subtotal"] == "26000.00"


class TestQuienLaVe:
    async def test_c06_el_cliente_ve_su_orden_y_no_la_ajena(self, api_sembrada):
        async with api_sembrada.entrar("cliente@example.com") as laura:
            propia = await laura.get("/ordenes/1")
            ajena = await laura.get("/ordenes/2")

        assert propia.status_code == 200
        assert propia.json()["cliente"] == "Laura Cliente"
        assert ajena.status_code == 403
        assert ajena.json() == {"detail": "No tenés permiso para ver esta orden."}

    async def test_el_dueno_sigue_viendo_la_orden_si_el_vehiculo_fue_dado_de_baja(self, api_sembrada):
        await api_sembrada.ejecutar("UPDATE vehiculo SET borrado_en = now() WHERE id = 1")
        async with api_sembrada.entrar("cliente@example.com") as laura:
            respuesta = await laura.get("/ordenes/1")

        assert respuesta.status_code == 200
        assert respuesta.json()["patente"] == "AA111BB"

    async def test_un_usuario_cliente_sin_ficha_recibe_403(self, api_sembrada):
        import seed

        await api_sembrada.ejecutar(
            "INSERT INTO usuario (email, nombre, password_hash, activo, debe_cambiar_password) "
            "SELECT 'sinficha@example.com', 'Sin Ficha', password_hash, true, false "
            "FROM usuario WHERE email = 'cliente@example.com'"
        )
        await api_sembrada.ejecutar(
            "INSERT INTO asignacion_rol (usuario_id, rol, desde) "
            "SELECT id, 'CLIENTE', now() FROM usuario WHERE email = 'sinficha@example.com'"
        )
        async with api_sembrada.anonimo() as sesion:
            login = await sesion.post(
                "/auth/login", json={"email": "sinficha@example.com", "password": seed.PASSWORD_CLIENTE},
            )
            assert login.status_code == 200, login.text
            respuesta = await sesion.get("/ordenes/1")

        assert respuesta.status_code == 403

    async def test_sin_sesion_responde_401(self, api_sembrada):
        async with api_sembrada.anonimo() as anonimo:
            respuesta = await anonimo.get("/ordenes/1")

        assert respuesta.status_code == 401

    async def test_con_cambio_de_password_pendiente_responde_403(self, api_sembrada):
        async with api_sembrada.entrar("nuevo@example.com") as sesion:
            respuesta = await sesion.get("/ordenes/1")

        assert respuesta.status_code == 403


class TestErrores:
    @pytest.mark.parametrize("orden_id", [999, 0, -1, 2_147_483_648, 99_999_999_999])
    async def test_una_orden_inexistente_responde_404_humano(self, api_sembrada, orden_id):
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.get(f"/ordenes/{orden_id}")

        assert respuesta.status_code == 404
        assert respuesta.json() == {"detail": "Orden no encontrada."}

    @pytest.mark.parametrize("orden_id", ["abc", "1.5"])
    async def test_un_id_no_entero_responde_422(self, api_sembrada, orden_id):
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.get(f"/ordenes/{orden_id}")

        assert respuesta.status_code == 422
        assert respuesta.json() == {
            "detail": [{"msg": "Ingresá un número entero para la orden seleccionada."}]
        }

    async def test_el_404_precede_al_403_para_un_cliente(self, api_sembrada):
        async with api_sembrada.entrar("cliente@example.com") as laura:
            respuesta = await laura.get("/ordenes/999")

        assert respuesta.status_code == 404
