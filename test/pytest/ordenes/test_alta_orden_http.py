"""`POST /ordenes` (6.2, C-10, RN-10, D6): alta en un solo bloque, por HTTP sobre el seed real."""

from datetime import UTC, datetime, timedelta

import pytest

TABLAS = ("orden_trabajo", "item_orden", "historial_estado_orden")
ALTA_C10 = {
    "vehiculo_id": 2, "falla": "Ruido al frenar",
    "items": [{"repuesto_id": 2, "cantidad": 1}, {"repuesto_id": 4, "cantidad": 3}],
}
# Tope de NUMERIC(12,2) menos un centavo de margen: 9 999 999 999.99
PRECIO_ALTO = "99999999.99"


async def _repuesto_caro(entorno, codigo: str = "CARO-01") -> int:
    async with entorno.entrar("admin@example.com") as admin:
        respuesta = await admin.post("/repuestos", json={
            "codigo": codigo, "descripcion": "Repuesto de precio máximo",
            "precio": PRECIO_ALTO, "stock_inicial": 0,
        })
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


class TestAltaExitosa:
    async def test_c10_la_recepcion_crea_la_orden_con_precios_copiados_y_total(self, api_sembrada):
        antes = await api_sembrada.contar(*TABLAS)
        ahora = datetime.now(UTC)
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            respuesta = await recepcion.post("/ordenes", json=ALTA_C10)

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        creada_en = datetime.fromisoformat(cuerpo.pop("creada_en"))
        cuando = datetime.fromisoformat(cuerpo["historial"][0].pop("cuando"))
        assert abs(creada_en - ahora) < timedelta(minutes=2)
        assert abs(cuando - ahora) < timedelta(minutes=2)
        assert cuerpo == {
            "id": 3, "estado": "PENDIENTE", "patente": "AC456EF", "total": "68000.00",
            "mecanico_id": None, "falla": "Ruido al frenar", "cliente": "Laura Cliente",
            "items": [
                {"repuesto_id": 2, "codigo": "FRE-010", "descripcion": "Pastillas de freno delanteras",
                 "cantidad": 1, "precio_unitario": "32000.00", "subtotal": "32000.00"},
                {"repuesto_id": 4, "codigo": "ACE-530", "descripcion": "Aceite 5W30 por litro",
                 "cantidad": 3, "precio_unitario": "12000.00", "subtotal": "36000.00"},
            ],
            "historial": [{"desde_estado": None, "hasta_estado": "PENDIENTE", "usuario_id": 3}],
        }
        despues = await api_sembrada.contar(*TABLAS)
        assert [d - a for a, d in zip(antes, despues)] == [1, 2, 1]

    async def test_el_alta_no_descuenta_stock(self, api_sembrada):
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            creada = await recepcion.post("/ordenes", json=ALTA_C10)

        assert creada.status_code == 201, creada.text
        filas = await api_sembrada.consulta("SELECT id, stock FROM repuesto ORDER BY id")
        assert [tuple(f) for f in filas] == [(1, 10), (2, 4), (3, 2), (4, 20)]

    async def test_el_administrador_tambien_crea_y_firma_el_historial_con_su_usuario(self, api_sembrada):
        cuerpo = {
            "vehiculo_id": 1, "falla": "Cambio de bujías",
            "items": [{"repuesto_id": 1, "cantidad": 2}, {"repuesto_id": 3, "cantidad": 1}],
        }
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.post("/ordenes", json=cuerpo)

        assert respuesta.status_code == 201, respuesta.text
        detalle = respuesta.json()
        assert (detalle["id"], detalle["patente"], detalle["total"]) == (3, "AA111BB", "23500.00")
        assert [i["subtotal"] for i in detalle["items"]] == ["17000.00", "6500.00"]
        assert [h["usuario_id"] for h in detalle["historial"]] == [1]

    async def test_la_segunda_orden_recibe_el_id_siguiente(self, api_sembrada):
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            primera = await recepcion.post("/ordenes", json=ALTA_C10)
            segunda = await recepcion.post("/ordenes", json={**ALTA_C10, "falla": "Otra falla"})

        assert (primera.json()["id"], segunda.json()["id"]) == (3, 4)

    @pytest.mark.parametrize(
        ("repuesto_id", "precio_nuevo", "total_final"),
        [(2, "40000.00", "68000.00"), (4, "1.00", "68000.00")],
    )
    async def test_el_precio_del_item_no_cambia_si_despues_cambia_el_repuesto(
        self, api_sembrada, repuesto_id, precio_nuevo, total_final,
    ):
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            creada = await recepcion.post("/ordenes", json=ALTA_C10)
        async with api_sembrada.entrar("admin@example.com") as admin:
            cambio = await admin.patch(f"/repuestos/{repuesto_id}", json={"precio": precio_nuevo})
            assert cambio.status_code == 200, cambio.text

        orden_id = creada.json()["id"]
        items = await api_sembrada.consulta(
            "SELECT repuesto_id, precio_unitario FROM item_orden WHERE orden_id = :o ORDER BY id",
            o=orden_id,
        )
        total = await api_sembrada.consulta("SELECT total FROM orden_trabajo WHERE id = :o", o=orden_id)
        assert [(i[0], str(i[1])) for i in items] == [(2, "32000.00"), (4, "12000.00")]
        assert str(total[0][0]) == total_final

    async def test_el_limite_exacto_del_total_se_acepta(self, api_sembrada):
        caro = await _repuesto_caro(api_sembrada)
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            respuesta = await recepcion.post("/ordenes", json={
                "vehiculo_id": 1, "falla": "Límite", "items": [{"repuesto_id": caro, "cantidad": 100}],
            })

        assert respuesta.status_code == 201, respuesta.text
        assert respuesta.json()["total"] == "9999999999.00"


class TestReferenciasInvalidas:
    async def _intentar(self, entorno, cuerpo=ALTA_C10, usuario="recepcion@example.com"):
        antes = await entorno.contar(*TABLAS)
        async with entorno.entrar(usuario) as sesion:
            respuesta = await sesion.post("/ordenes", json=cuerpo)
        return respuesta, antes, await entorno.contar(*TABLAS)

    @pytest.mark.parametrize(
        ("repuestos", "mensaje"),
        [
            ([999], "Estos repuestos no existen o fueron dados de baja: 999."),
            ([2, 777, 888], "Estos repuestos no existen o fueron dados de baja: 777, 888."),
        ],
    )
    async def test_c10_un_repuesto_inexistente_responde_409_y_no_deja_filas(
        self, api_sembrada, repuestos, mensaje,
    ):
        cuerpo = {
            "vehiculo_id": 2, "falla": "Ruido al frenar",
            "items": [{"repuesto_id": r, "cantidad": 1} for r in repuestos],
        }

        respuesta, antes, despues = await self._intentar(api_sembrada, cuerpo)

        assert respuesta.status_code == 409
        assert respuesta.json() == {"detail": mensaje}
        assert despues == antes

    async def test_un_repuesto_dado_de_baja_responde_409_y_no_deja_filas(self, api_sembrada):
        async with api_sembrada.entrar("admin@example.com") as admin:
            assert (await admin.delete("/repuestos/4")).status_code == 204

        respuesta, antes, despues = await self._intentar(api_sembrada)

        assert respuesta.status_code == 409
        assert respuesta.json() == {"detail": "Estos repuestos no existen o fueron dados de baja: 4."}
        assert despues == antes

    @pytest.mark.parametrize("vehiculo_id", [999, 2_147_483_647])
    async def test_un_vehiculo_inexistente_responde_409_y_no_deja_filas(self, api_sembrada, vehiculo_id):
        respuesta, antes, despues = await self._intentar(
            api_sembrada, {**ALTA_C10, "vehiculo_id": vehiculo_id},
        )

        assert respuesta.status_code == 409
        assert respuesta.json() == {"detail": "El vehículo no existe o fue dado de baja."}
        assert despues == antes

    async def test_un_vehiculo_dado_de_baja_responde_409_y_no_deja_filas(self, api_sembrada):
        await api_sembrada.ejecutar("UPDATE vehiculo SET borrado_en = now() WHERE id = 2")

        respuesta, antes, despues = await self._intentar(api_sembrada)

        assert respuesta.status_code == 409
        assert respuesta.json() == {"detail": "El vehículo no existe o fue dado de baja."}
        assert despues == antes

    async def test_con_el_catalogo_vacio_responde_409_propio_y_no_deja_filas(self, api_sembrada):
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            await api_sembrada.ejecutar("TRUNCATE TABLE estado_orden CASCADE")
            respuesta = await recepcion.post("/ordenes", json=ALTA_C10)

        assert respuesta.status_code == 409
        assert respuesta.json() == {
            "detail": "Todavía no se pueden crear órdenes: falta cargar los estados del taller."
        }
        assert await api_sembrada.contar(*TABLAS) == [0, 0, 0]

    async def test_el_catalogo_vacio_se_evalua_antes_que_el_vehiculo(self, api_sembrada):
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            await api_sembrada.ejecutar("TRUNCATE TABLE estado_orden CASCADE")
            respuesta = await recepcion.post("/ordenes", json={**ALTA_C10, "vehiculo_id": 999})

        assert "estados del taller" in respuesta.json()["detail"]

    @pytest.mark.parametrize("cantidad", [101, 2_147_483_647])
    async def test_un_total_fuera_de_rango_responde_409_y_no_500(self, api_sembrada, cantidad):
        caro = await _repuesto_caro(api_sembrada)
        cuerpo = {"vehiculo_id": 1, "falla": "Excede", "items": [{"repuesto_id": caro, "cantidad": cantidad}]}

        respuesta, antes, despues = await self._intentar(api_sembrada, cuerpo)

        assert respuesta.status_code == 409
        assert respuesta.json() == {
            "detail": "El total de la orden supera el máximo permitido: revisá las cantidades."
        }
        assert despues == antes


class TestAtomicidadDelAlta:
    @pytest.mark.parametrize("falla_en", ["items", "historial"])
    async def test_una_falla_a_mitad_del_alta_no_deja_ninguna_fila(self, api_sembrada, monkeypatch, falla_en):
        from app.modules.ordenes.repository import HistorialEstadoOrdenRepository, ItemOrdenRepository

        clase = {"items": ItemOrdenRepository, "historial": HistorialEstadoOrdenRepository}[falla_en]
        original = clase.add
        llamadas = 0

        async def falla_en_la_ultima_escritura(self, entidad):
            nonlocal llamadas
            llamadas += 1
            if falla_en == "historial" or llamadas == 2:  # segundo ítem / línea de historial
                raise RuntimeError("falla inyectada")
            return await original(self, entidad)

        monkeypatch.setattr(clase, "add", falla_en_la_ultima_escritura)
        antes = await api_sembrada.contar(*TABLAS)

        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            with pytest.raises(RuntimeError, match="falla inyectada"):
                await recepcion.post("/ordenes", json=ALTA_C10)

        assert await api_sembrada.contar(*TABLAS) == antes


class TestContratoYPermisos:
    @pytest.mark.parametrize(
        "cuerpo",
        [
            {**ALTA_C10, "total": "1.00"},
            {**ALTA_C10, "estado": "TERMINADA"},
            {**ALTA_C10, "items": [{"repuesto_id": 2, "cantidad": 1, "precio_unitario": "1.00"}]},
            {**ALTA_C10, "items": []},
            {**ALTA_C10, "items": [{"repuesto_id": 2, "cantidad": 1}, {"repuesto_id": 2, "cantidad": 2}]},
            {**ALTA_C10, "items": [{"repuesto_id": 2, "cantidad": 0}]},
            {**ALTA_C10, "items": [{"repuesto_id": 2, "cantidad": -3}]},
            {**ALTA_C10, "falla": ""},
        ],
        ids=["total", "estado", "precio", "sin_items", "repetido", "cantidad_cero",
             "cantidad_negativa", "falla_vacia"],
    )
    async def test_un_cuerpo_invalido_responde_422_y_no_crea_nada(self, api_sembrada, cuerpo):
        antes = await api_sembrada.contar(*TABLAS)
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            respuesta = await recepcion.post("/ordenes", json=cuerpo)

        assert respuesta.status_code == 422
        assert all(set(m) == {"msg"} for m in respuesta.json()["detail"])
        assert await api_sembrada.contar(*TABLAS) == antes

    @pytest.mark.parametrize("usuario", ["mecanico@example.com", "cliente@example.com"])
    async def test_el_mecanico_y_el_cliente_reciben_403_y_no_se_crea_nada(self, api_sembrada, usuario):
        antes = await api_sembrada.contar(*TABLAS)
        async with api_sembrada.entrar(usuario) as sesion:
            respuesta = await sesion.post("/ordenes", json=ALTA_C10)

        assert respuesta.status_code == 403
        assert await api_sembrada.contar(*TABLAS) == antes

    async def test_sin_sesion_responde_401(self, api_sembrada):
        async with api_sembrada.anonimo() as anonimo:
            respuesta = await anonimo.post("/ordenes", json=ALTA_C10)

        assert respuesta.status_code == 401

    async def test_el_permiso_por_rol_se_evalua_antes_que_la_validacion_del_cuerpo(self, api_sembrada):
        async with api_sembrada.entrar("cliente@example.com") as cliente:
            respuesta = await cliente.post("/ordenes", json={"items": []})

        assert respuesta.status_code == 403

    async def test_con_cambio_de_password_pendiente_responde_403(self, api_sembrada):
        async with api_sembrada.entrar("nuevo@example.com") as sesion:
            respuesta = await sesion.post("/ordenes", json=ALTA_C10)

        assert respuesta.status_code == 403
