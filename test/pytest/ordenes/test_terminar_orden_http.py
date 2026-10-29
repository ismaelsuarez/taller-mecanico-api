"""`POST /ordenes/{id}/terminar` (8.1-8.3, RN-13, RN-14, RT-TX-04, D2, D5, D7): por HTTP sobre el seed real.

Datos del seed: orden 2 `EN_REPARACION` (mecánico 4) con 4 bujías (repuesto 3, stock 2). Repuestos:
1 Filtro de aceite (stock 10), 2 Pastillas (4), 3 Bujía (2), 4 Aceite 5W30 (20). Usuarios: admin=1,
recepcion=3, mecanico=4, mecanico2=5, cliente=6, nuevo=7 (MECANICO con cambio pendiente).
"""

import pytest

from ordenes._apoyo import crear_orden, instantanea, linea_nueva, poner_estado

CLAVES_DEL_DETALLE = {
    "id", "estado", "patente", "total", "creada_en", "mecanico_id", "falla", "cliente", "items", "historial",
}
MOTIVO_ORDEN_2 = "Salida por orden de trabajo #2"


async def _reponer(entorno, repuesto_id: int, cantidad: int) -> None:
    async with entorno.entrar("admin@example.com") as admin:
        respuesta = await admin.post(f"/repuestos/{repuesto_id}/reponer", json={"cantidad": cantidad})
    assert respuesta.status_code == 200, respuesta.text


async def _orden_en_reparacion(entorno, items: list[dict], mecanico: str = "mecanico@example.com") -> int:
    """Una orden nueva creada por la recepción e iniciada por `mecanico` (queda asignada a él)."""
    orden = await crear_orden(
        entorno, "recepcion@example.com", {"vehiculo_id": 2, "falla": "Revisión general", "items": items},
    )
    async with entorno.entrar(mecanico) as sesion:
        iniciada = await sesion.post(f"/ordenes/{orden}/iniciar")
    assert iniciada.status_code == 200, iniciada.text
    return orden


class TestStockInsuficienteC11:
    async def test_c11_terminar_la_orden_2_sin_bujias_suficientes_responde_409_y_no_cambia_nada(self, api_sembrada):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/2/terminar")

        assert respuesta.status_code == 409
        assert respuesta.json() == {
            "detail": "No hay stock suficiente de Bujía de encendido (BUJ-014): hay 2 y se necesitan 4."
        }
        assert await instantanea(api_sembrada) == antes  # estado, stock, movimientos e historial idénticos
        assert antes["ordenes"][1][1:3] == ("EN_REPARACION", 4)

    async def test_el_mensaje_no_expone_nombres_internos_de_la_base(self, api_sembrada):
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/2/terminar")

        assert respuesta.status_code == 409
        texto = respuesta.text.lower()
        assert not any(palabra in texto for palabra in ("repuesto_stock", "ck_", "constraint", "violates", "traceback"))

    async def test_triangulacion_solo_el_ultimo_item_no_alcanza_y_ningun_stock_cambia(self, api_sembrada):
        # Filtro (stock 10) x2 alcanza; la bujía (stock 2) x5 no: es el último ítem de la orden
        orden = await _orden_en_reparacion(api_sembrada, [
            {"repuesto_id": 1, "cantidad": 2}, {"repuesto_id": 4, "cantidad": 3}, {"repuesto_id": 3, "cantidad": 5},
        ])
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post(f"/ordenes/{orden}/terminar")

        assert respuesta.status_code == 409
        assert respuesta.json() == {
            "detail": "No hay stock suficiente de Bujía de encendido (BUJ-014): hay 2 y se necesitan 5."
        }
        despues = await instantanea(api_sembrada)
        assert despues == antes
        assert dict(despues["stock"])[1] == 10 and dict(despues["stock"])[4] == 20  # los ítems previos intactos

    async def test_triangulacion_falta_en_el_primer_item_tampoco_cambia_nada(self, api_sembrada):
        orden = await _orden_en_reparacion(api_sembrada, [
            {"repuesto_id": 3, "cantidad": 3}, {"repuesto_id": 1, "cantidad": 1},
        ])
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post(f"/ordenes/{orden}/terminar")

        assert respuesta.status_code == 409
        assert "hay 2 y se necesitan 3" in respuesta.json()["detail"]
        assert await instantanea(api_sembrada) == antes


class TestTerminarC12:
    async def test_c12_reponer_y_terminar_la_orden_2_descuenta_el_stock_con_su_movimiento(self, api_sembrada):
        await _reponer(api_sembrada, 3, 2)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/2/terminar")

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert set(cuerpo) == CLAVES_DEL_DETALLE
        assert (cuerpo["id"], cuerpo["estado"], cuerpo["mecanico_id"], cuerpo["total"]) == (
            2, "TERMINADA", 4, "26000.00",
        )
        assert [(h["desde_estado"], h["hasta_estado"], h["usuario_id"]) for h in cuerpo["historial"]] == [
            (None, "PENDIENTE", 3), ("PENDIENTE", "EN_REPARACION", 4), ("EN_REPARACION", "TERMINADA", 4),
        ]
        assert [(i["codigo"], i["cantidad"]) for i in cuerpo["items"]] == [("BUJ-014", 4)]

        despues = await instantanea(api_sembrada)
        assert dict(despues["stock"])[3] == 0
        assert len(despues["movimientos"]) == len(antes["movimientos"]) + 1
        movimientos = await api_sembrada.consulta(
            "SELECT repuesto_id, orden_id, usuario_id, cantidad, motivo FROM movimiento_stock "
            "WHERE orden_id = 2 ORDER BY id"
        )
        assert [tuple(m) for m in movimientos] == [(3, 2, 4, -4, MOTIVO_ORDEN_2)]
        assert [f[1:] for f in linea_nueva(antes, despues)] == [(2, "EN_REPARACION", "TERMINADA", 4)]
        assert despues["ordenes"][1] == (2, "TERMINADA", 4, antes["ordenes"][1][3])

    async def test_los_movimientos_de_la_terminacion_se_leen_por_la_ruta_de_movimientos(self, api_sembrada):
        await _reponer(api_sembrada, 3, 2)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            assert (await mecanico.post("/ordenes/2/terminar")).status_code == 200
        async with api_sembrada.entrar("admin@example.com") as admin:
            movimientos = (await admin.get("/repuestos/3/movimientos")).json()

        assert [(m["cantidad"], m["motivo"]) for m in movimientos][-2:] == [(2, "Reposición"), (-4, MOTIVO_ORDEN_2)]

    async def test_triangulacion_orden_de_varios_items_un_movimiento_por_item(self, api_sembrada):
        orden = await _orden_en_reparacion(api_sembrada, [
            {"repuesto_id": 1, "cantidad": 2}, {"repuesto_id": 4, "cantidad": 3}, {"repuesto_id": 2, "cantidad": 4},
        ])
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post(f"/ordenes/{orden}/terminar")

        assert respuesta.status_code == 200, respuesta.text
        despues = await instantanea(api_sembrada)
        assert dict(despues["stock"]) == {1: 8, 2: 0, 3: 2, 4: 17}  # salida exacta del 2: queda en 0
        nuevos = await api_sembrada.consulta(
            "SELECT repuesto_id, cantidad, motivo, usuario_id FROM movimiento_stock WHERE orden_id = :o ORDER BY id",
            o=orden,
        )
        assert [tuple(m) for m in nuevos] == [
            (1, -2, f"Salida por orden de trabajo #{orden}", 4),
            (4, -3, f"Salida por orden de trabajo #{orden}", 4),
            (2, -4, f"Salida por orden de trabajo #{orden}", 4),
        ]
        assert len(despues["movimientos"]) == len(antes["movimientos"]) + 3

    async def test_el_admin_termina_sin_cambiar_el_mecanico_y_firma_con_su_usuario(self, api_sembrada):
        await _reponer(api_sembrada, 3, 2)
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.post("/ordenes/2/terminar")

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["mecanico_id"] == 4  # DD-31: no se reasigna
        assert respuesta.json()["historial"][-1]["usuario_id"] == 1
        movimientos = await api_sembrada.consulta(
            "SELECT usuario_id FROM movimiento_stock WHERE orden_id = 2"
        )
        assert [tuple(m) for m in movimientos] == [(1,)]
        assert (await instantanea(api_sembrada))["ordenes"][1][2] == 4

    async def test_el_admin_termina_una_orden_de_otro_mecanico_con_stock_propio(self, api_sembrada):
        orden = await _orden_en_reparacion(api_sembrada, [{"repuesto_id": 1, "cantidad": 1}], "mecanico2@example.com")
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.post(f"/ordenes/{orden}/terminar")

        assert respuesta.status_code == 200, respuesta.text
        assert (respuesta.json()["mecanico_id"], respuesta.json()["historial"][-1]["usuario_id"]) == (5, 1)

    async def test_un_repuesto_dado_de_baja_tras_el_alta_igual_se_descuenta(self, api_sembrada):
        await _reponer(api_sembrada, 3, 2)
        async with api_sembrada.entrar("admin@example.com") as admin:
            assert (await admin.delete("/repuestos/3")).status_code == 204
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/2/terminar")

        assert respuesta.status_code == 200, respuesta.text
        assert dict((await instantanea(api_sembrada))["stock"])[3] == 0

    async def test_terminar_dos_veces_descuenta_una_sola_vez(self, api_sembrada):
        await _reponer(api_sembrada, 3, 6)  # alcanzaría para una segunda salida si hubiera doble descuento
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            primera = await mecanico.post("/ordenes/2/terminar")
            despues_de_la_primera = await instantanea(api_sembrada)
            segunda = await mecanico.post("/ordenes/2/terminar")

        assert (primera.status_code, segunda.status_code) == (200, 409)
        assert segunda.json() == {"detail": "La orden ya está terminada: no se puede terminar."}
        assert await instantanea(api_sembrada) == despues_de_la_primera
        assert dict(despues_de_la_primera["stock"])[3] == 4


class TestPermisoParaTerminar:
    @pytest.mark.parametrize("usuario", ["mecanico2@example.com", "recepcion@example.com", "cliente@example.com"])
    async def test_quien_no_es_el_asignado_ni_admin_recibe_403_sin_escrituras(self, api_sembrada, usuario):
        await _reponer(api_sembrada, 3, 2)  # con stock suficiente: el 403 no es un 409 disfrazado
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar(usuario) as sesion:
            respuesta = await sesion.post("/ordenes/2/terminar")

        assert respuesta.status_code == 403
        assert await instantanea(api_sembrada) == antes

    async def test_el_mecanico_no_asignado_recibe_el_mensaje_propio_de_terminar(self, api_sembrada):
        async with api_sembrada.entrar("mecanico2@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/2/terminar")

        assert respuesta.json() == {"detail": "No tenés permiso para terminar esta orden."}

    async def test_el_permiso_se_evalua_antes_que_el_estado(self, api_sembrada):
        await poner_estado(api_sembrada, 2, "TERMINADA")
        async with api_sembrada.entrar("mecanico2@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/2/terminar")

        assert respuesta.status_code == 403  # no 409

    async def test_el_asignado_que_perdio_el_rol_mecanico_recibe_403(self, api_sembrada):
        await _reponer(api_sembrada, 3, 2)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            await api_sembrada.ejecutar(
                "UPDATE asignacion_rol SET revocada_en = now() WHERE usuario_id = 4 AND rol = 'MECANICO'"
            )
            antes = await instantanea(api_sembrada)
            respuesta = await mecanico.post("/ordenes/2/terminar")

        assert respuesta.status_code == 403
        assert await instantanea(api_sembrada) == antes

    async def test_un_admin_asignado_como_mecanico_de_la_orden_tambien_termina(self, api_sembrada):
        await _reponer(api_sembrada, 3, 2)
        await api_sembrada.ejecutar("UPDATE orden_trabajo SET mecanico_id = 2 WHERE id = 2")  # admin2 asignado
        async with api_sembrada.entrar("admin2@example.com") as admin2:
            respuesta = await admin2.post("/ordenes/2/terminar")

        assert respuesta.status_code == 200, respuesta.text

    async def test_el_mecanico_con_cambio_de_password_pendiente_recibe_403(self, api_sembrada):
        await api_sembrada.ejecutar("UPDATE orden_trabajo SET mecanico_id = 7 WHERE id = 2")
        await _reponer(api_sembrada, 3, 2)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("nuevo@example.com") as nuevo:
            respuesta = await nuevo.post("/ordenes/2/terminar")

        assert respuesta.status_code == 403
        assert await instantanea(api_sembrada) == antes

    async def test_sin_sesion_responde_401_sin_escrituras(self, api_sembrada):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.anonimo() as anonimo:
            respuesta = await anonimo.post("/ordenes/2/terminar")

        assert respuesta.status_code == 401
        assert await instantanea(api_sembrada) == antes

    @pytest.mark.parametrize("orden_id", [999, 0, 2147483648])
    async def test_una_orden_inexistente_responde_404_a_quien_tiene_rol(self, api_sembrada, orden_id):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post(f"/ordenes/{orden_id}/terminar")

        assert respuesta.status_code == 404
        assert respuesta.json() == {"detail": "Orden no encontrada."}
        assert await instantanea(api_sembrada) == antes

    async def test_el_rol_de_ruta_precede_al_404_para_la_recepcion(self, api_sembrada):
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            respuesta = await recepcion.post("/ordenes/999/terminar")

        assert respuesta.status_code == 403

    async def test_un_admin_recibe_404_ante_una_orden_inexistente(self, api_sembrada):
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.post("/ordenes/999/terminar")

        assert respuesta.status_code == 404

    async def test_un_id_no_entero_responde_422(self, api_sembrada):
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/abc/terminar")

        assert respuesta.status_code == 422


class TestEstadoParaTerminar:
    @pytest.mark.parametrize(
        ("usuario", "orden_id", "estado", "frase"),
        [
            ("mecanico@example.com", 2, "TERMINADA", "ya está terminada"),
            ("mecanico@example.com", 2, "CANCELADA", "ya está cancelada"),
            ("admin@example.com", 1, "PENDIENTE", "todavía está pendiente"),
            ("admin@example.com", 2, "CANCELADA", "ya está cancelada"),
        ],
    )
    async def test_una_orden_que_no_esta_en_reparacion_responde_409_sin_escrituras(
        self, api_sembrada, usuario, orden_id, estado, frase,
    ):
        await _reponer(api_sembrada, 3, 2)  # hay stock: el 409 es por el estado, no por el stock
        await poner_estado(api_sembrada, orden_id, estado)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar(usuario) as sesion:
            respuesta = await sesion.post(f"/ordenes/{orden_id}/terminar")

        assert respuesta.status_code == 409
        assert respuesta.json() == {"detail": f"La orden {frase}: no se puede terminar."}
        assert await instantanea(api_sembrada) == antes

    async def test_un_mecanico_sobre_una_orden_pendiente_sin_asignar_recibe_403_no_409(self, api_sembrada):
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/1/terminar")  # PENDIENTE, mecanico_id nulo

        assert respuesta.status_code == 403


class TestAtomicidadDeLaTerminacion:
    """RN-13 y RT-TX-04: una falla en cualquier escritura de la terminación no deja ninguna de las cuatro."""

    async def test_una_falla_en_el_historial_deshace_el_stock_los_movimientos_y_el_estado(
        self, api_sembrada, monkeypatch,
    ):
        from app.modules.ordenes.repository import HistorialEstadoOrdenRepository

        async def falla(self, linea):
            raise RuntimeError("falla inyectada")

        await _reponer(api_sembrada, 3, 2)
        antes = await instantanea(api_sembrada)
        monkeypatch.setattr(HistorialEstadoOrdenRepository, "add", falla)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            with pytest.raises(RuntimeError, match="falla inyectada"):
                await mecanico.post("/ordenes/2/terminar")

        assert await instantanea(api_sembrada) == antes
        assert dict(antes["stock"])[3] == 4  # la salida ya se había escrito en la sesión y se revirtió

    async def test_una_falla_en_el_segundo_movimiento_deshace_tambien_el_primero(self, api_sembrada, monkeypatch):
        from app.modules.repuestos.repository import RepuestoRepository

        orden = await _orden_en_reparacion(api_sembrada, [
            {"repuesto_id": 1, "cantidad": 2}, {"repuesto_id": 4, "cantidad": 3},
        ])
        antes = await instantanea(api_sembrada)
        original = RepuestoRepository.registrar_movimiento
        llamadas = 0

        async def falla_en_la_segunda(self, *args, **kwargs):
            nonlocal llamadas
            llamadas += 1
            if llamadas == 2:
                raise RuntimeError("falla inyectada")
            return await original(self, *args, **kwargs)

        monkeypatch.setattr(RepuestoRepository, "registrar_movimiento", falla_en_la_segunda)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            with pytest.raises(RuntimeError, match="falla inyectada"):
                await mecanico.post(f"/ordenes/{orden}/terminar")

        assert llamadas == 2  # la primera salida llegó a escribirse antes de la falla
        assert await instantanea(api_sembrada) == antes

    async def test_una_falla_al_actualizar_el_estado_deshace_los_movimientos(self, api_sembrada, monkeypatch):
        from app.modules.ordenes.repository import OrdenRepository

        async def falla(self, entidad):
            raise RuntimeError("falla inyectada")

        await _reponer(api_sembrada, 3, 2)
        antes = await instantanea(api_sembrada)
        monkeypatch.setattr(OrdenRepository, "update", falla)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            with pytest.raises(RuntimeError, match="falla inyectada"):
                await mecanico.post("/ordenes/2/terminar")

        assert await instantanea(api_sembrada) == antes

    async def test_el_control_sin_falla_si_confirma_las_cuatro_escrituras(self, api_sembrada):
        await _reponer(api_sembrada, 3, 2)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/2/terminar")

        assert respuesta.status_code == 200
        despues = await instantanea(api_sembrada)
        assert despues["ordenes"] != antes["ordenes"]
        assert despues["stock"] != antes["stock"]
        assert len(despues["movimientos"]) == len(antes["movimientos"]) + 1
        assert len(despues["historial"]) == len(antes["historial"]) + 1


class TestRutaPublicada:
    async def test_openapi_publica_terminar_como_post_sin_cuerpo(self, api_sembrada):
        operaciones = api_sembrada.app.openapi()["paths"]["/ordenes/{orden_id}/terminar"]

        assert set(operaciones) == {"post"}
        assert "requestBody" not in operaciones["post"]
        assert "200" in operaciones["post"]["responses"]
