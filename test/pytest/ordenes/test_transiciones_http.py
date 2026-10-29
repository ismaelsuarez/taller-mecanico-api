"""`POST /ordenes/{id}/iniciar` y `/cancelar` (7.1, 7.2, RN-11, RN-12, D2, D7): por HTTP sobre el seed real.

Datos del seed: orden 1 `PENDIENTE` (vehículo 1 de Laura, `cliente@example.com`), orden 2
`EN_REPARACION` (vehículo 3 de Jorge, mecánico 4). Usuarios: admin=1, recepcion=3, mecanico=4,
mecanico2=5, cliente=6, nuevo=7 (MECANICO con cambio de contraseña pendiente).
"""

from datetime import UTC, datetime, timedelta

import pytest

from ordenes._apoyo import crear_orden, instantanea, linea_nueva, poner_estado

CLAVES_DEL_DETALLE = {
    "id", "estado", "patente", "total", "creada_en", "mecanico_id", "falla", "cliente", "items", "historial",
}
ALTA_PARA_LAURA = {"vehiculo_id": 2, "falla": "Ruido al frenar", "items": [{"repuesto_id": 2, "cantidad": 1}]}
ALTA_PARA_JORGE = {"vehiculo_id": 3, "falla": "No arranca", "items": [{"repuesto_id": 1, "cantidad": 2}]}
SIN_ESCRITURAS_ESTADOS = ["EN_REPARACION", "TERMINADA", "CANCELADA"]


class TestIniciar:
    async def test_un_mecanico_toma_una_orden_pendiente(self, api_sembrada):
        antes = await instantanea(api_sembrada)
        ahora = datetime.now(UTC)
        async with api_sembrada.entrar("mecanico2@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/1/iniciar")

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert set(cuerpo) == CLAVES_DEL_DETALLE
        assert (cuerpo["id"], cuerpo["estado"], cuerpo["mecanico_id"]) == (1, "EN_REPARACION", 5)
        assert [(h["desde_estado"], h["hasta_estado"], h["usuario_id"]) for h in cuerpo["historial"]] == [
            (None, "PENDIENTE", 3), ("PENDIENTE", "EN_REPARACION", 5),
        ]
        assert abs(datetime.fromisoformat(cuerpo["historial"][-1]["cuando"]) - ahora) < timedelta(minutes=2)
        despues = await instantanea(api_sembrada)
        assert (1, "EN_REPARACION", 5) == despues["ordenes"][0][:3]
        assert [f[1:] for f in linea_nueva(antes, despues)] == [(1, "PENDIENTE", "EN_REPARACION", 5)]
        assert despues["stock"] == antes["stock"] and despues["movimientos"] == antes["movimientos"]

    async def test_otro_mecanico_y_otra_orden_quedan_firmados_por_quien_inicia(self, api_sembrada):
        nueva = await crear_orden(api_sembrada, "recepcion@example.com", ALTA_PARA_LAURA)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post(f"/ordenes/{nueva}/iniciar")

        assert respuesta.status_code == 200, respuesta.text
        assert (respuesta.json()["id"], respuesta.json()["mecanico_id"]) == (nueva, 4)
        assert respuesta.json()["historial"][-1]["usuario_id"] == 4
        # El detalle devuelto ya trae los ítems de la orden (relectura con precarga)
        assert [i["codigo"] for i in respuesta.json()["items"]] == ["FRE-010"]

    async def test_un_admin_con_el_rol_mecanico_tambien_puede_iniciar(self, api_sembrada):
        await api_sembrada.ejecutar(
            "INSERT INTO asignacion_rol (usuario_id, rol, desde) VALUES (1, 'MECANICO', now())"
        )
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.post("/ordenes/1/iniciar")

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["mecanico_id"] == 1

    @pytest.mark.parametrize("estado", SIN_ESCRITURAS_ESTADOS)
    async def test_una_orden_que_no_esta_pendiente_responde_409_sin_escrituras(self, api_sembrada, estado):
        await poner_estado(api_sembrada, 2, estado)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico2@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/2/iniciar")

        assert respuesta.status_code == 409
        detalle = respuesta.json()["detail"]
        assert detalle.startswith("La orden ya está") and "no se puede iniciar" in detalle
        assert await instantanea(api_sembrada) == antes

    async def test_el_mensaje_409_nombra_el_estado_actual(self, api_sembrada):
        async with api_sembrada.entrar("mecanico2@example.com") as mecanico:
            en_reparacion = await mecanico.post("/ordenes/2/iniciar")
            await poner_estado(api_sembrada, 2, "CANCELADA")
            cancelada = await mecanico.post("/ordenes/2/iniciar")

        assert en_reparacion.json() == {"detail": "La orden ya está en reparación: no se puede iniciar."}
        assert cancelada.json() == {"detail": "La orden ya está cancelada: no se puede iniciar."}

    async def test_iniciar_dos_veces_la_misma_orden_responde_409_la_segunda(self, api_sembrada):
        async with api_sembrada.entrar("mecanico2@example.com") as mecanico:
            primera = await mecanico.post("/ordenes/1/iniciar")
            segunda = await mecanico.post("/ordenes/1/iniciar")

        assert (primera.status_code, segunda.status_code) == (200, 409)
        assert (await instantanea(api_sembrada))["ordenes"][0][2] == 5

    @pytest.mark.parametrize("orden_id", [999, 0, 2147483648])
    async def test_una_orden_inexistente_o_fuera_de_rango_responde_404(self, api_sembrada, orden_id):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post(f"/ordenes/{orden_id}/iniciar")

        assert respuesta.status_code == 404
        assert respuesta.json() == {"detail": "Orden no encontrada."}
        assert await instantanea(api_sembrada) == antes

    async def test_un_id_no_entero_responde_422(self, api_sembrada):
        async with api_sembrada.entrar("mecanico@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/abc/iniciar")

        assert respuesta.status_code == 422

    @pytest.mark.parametrize("usuario", ["admin@example.com", "recepcion@example.com", "cliente@example.com"])
    async def test_quien_no_es_mecanico_recibe_403_sin_escrituras(self, api_sembrada, usuario):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar(usuario) as sesion:
            respuesta = await sesion.post("/ordenes/1/iniciar")

        assert respuesta.status_code == 403
        assert respuesta.json() == {"detail": "No tenés permiso para realizar esta acción."}
        assert await instantanea(api_sembrada) == antes

    async def test_el_permiso_por_rol_precede_al_404(self, api_sembrada):
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.post("/ordenes/999/iniciar")

        assert respuesta.status_code == 403

    async def test_el_mecanico_con_cambio_de_password_pendiente_recibe_403(self, api_sembrada):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("nuevo@example.com") as nuevo:
            respuesta = await nuevo.post("/ordenes/1/iniciar")

        assert respuesta.status_code == 403
        assert await instantanea(api_sembrada) == antes

    async def test_sin_sesion_responde_401_sin_escrituras(self, api_sembrada):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.anonimo() as anonimo:
            respuesta = await anonimo.post("/ordenes/1/iniciar")

        assert respuesta.status_code == 401
        assert await instantanea(api_sembrada) == antes

    async def test_el_rol_mecanico_revocado_deja_de_alcanzar_en_la_siguiente_peticion(self, api_sembrada):
        async with api_sembrada.entrar("mecanico2@example.com") as mecanico:
            await api_sembrada.ejecutar(
                "UPDATE asignacion_rol SET revocada_en = now() WHERE usuario_id = 5 AND rol = 'MECANICO'"
            )
            respuesta = await mecanico.post("/ordenes/1/iniciar")

        assert respuesta.status_code == 403
        assert (await instantanea(api_sembrada))["ordenes"][0][1] == "PENDIENTE"

    async def test_una_falla_a_mitad_de_iniciar_no_deja_ninguna_escritura(self, api_sembrada, monkeypatch):
        from app.modules.ordenes.repository import HistorialEstadoOrdenRepository

        async def falla(self, linea):
            raise RuntimeError("falla inyectada")

        monkeypatch.setattr(HistorialEstadoOrdenRepository, "add", falla)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("mecanico2@example.com") as mecanico:
            with pytest.raises(RuntimeError, match="falla inyectada"):
                await mecanico.post("/ordenes/1/iniciar")

        assert await instantanea(api_sembrada) == antes  # ni estado ni mecanico_id ni historial


class TestCancelar:
    @pytest.mark.parametrize(
        ("usuario", "usuario_id"),
        [("cliente@example.com", 6), ("recepcion@example.com", 3), ("admin@example.com", 1)],
    )
    async def test_cancelan_el_dueno_la_recepcion_y_el_admin_una_orden_pendiente(
        self, api_sembrada, usuario, usuario_id,
    ):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar(usuario) as sesion:
            respuesta = await sesion.post("/ordenes/1/cancelar")

        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert set(cuerpo) == CLAVES_DEL_DETALLE
        assert (cuerpo["id"], cuerpo["estado"], cuerpo["mecanico_id"]) == (1, "CANCELADA", None)
        assert [(h["desde_estado"], h["hasta_estado"], h["usuario_id"]) for h in cuerpo["historial"]] == [
            (None, "PENDIENTE", 3), ("PENDIENTE", "CANCELADA", usuario_id),
        ]
        despues = await instantanea(api_sembrada)
        assert despues["ordenes"][0] == (1, "CANCELADA", None, antes["ordenes"][0][3])
        assert [f[1:] for f in linea_nueva(antes, despues)] == [(1, "PENDIENTE", "CANCELADA", usuario_id)]
        assert despues["stock"] == antes["stock"] and despues["movimientos"] == antes["movimientos"]

    async def test_el_dueno_cancela_su_orden_aunque_el_vehiculo_este_dado_de_baja(self, api_sembrada):
        await api_sembrada.ejecutar("UPDATE vehiculo SET borrado_en = now() WHERE id = 1")
        async with api_sembrada.entrar("cliente@example.com") as laura:
            respuesta = await laura.post("/ordenes/1/cancelar")

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["estado"] == "CANCELADA"

    async def test_cancelar_una_orden_creada_por_la_api_no_toca_el_stock(self, api_sembrada):
        nueva = await crear_orden(api_sembrada, "recepcion@example.com", ALTA_PARA_LAURA)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("cliente@example.com") as laura:
            respuesta = await laura.post(f"/ordenes/{nueva}/cancelar")

        assert respuesta.status_code == 200, respuesta.text
        despues = await instantanea(api_sembrada)
        assert despues["stock"] == antes["stock"] and despues["movimientos"] == antes["movimientos"]

    async def test_c13_el_cliente_sobre_una_orden_ajena_no_pendiente_recibe_403_no_409(self, api_sembrada):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("cliente@example.com") as laura:
            respuesta = await laura.post("/ordenes/2/cancelar")  # de Jorge, EN_REPARACION

        assert respuesta.status_code == 403
        assert respuesta.json() == {"detail": "No tenés permiso para cancelar esta orden."}
        assert await instantanea(api_sembrada) == antes

    async def test_el_cliente_sobre_una_orden_ajena_pendiente_tambien_recibe_403(self, api_sembrada):
        ajena = await crear_orden(api_sembrada, "recepcion@example.com", ALTA_PARA_JORGE)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("cliente@example.com") as laura:
            respuesta = await laura.post(f"/ordenes/{ajena}/cancelar")

        assert respuesta.status_code == 403
        assert await instantanea(api_sembrada) == antes

    @pytest.mark.parametrize("usuario", ["mecanico@example.com", "mecanico2@example.com"])
    async def test_un_mecanico_nunca_cancela_ni_siendo_el_asignado_y_recibe_403_no_409(self, api_sembrada, usuario):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar(usuario) as mecanico:
            pendiente = await mecanico.post("/ordenes/1/cancelar")
            asignada = await mecanico.post("/ordenes/2/cancelar")  # EN_REPARACION: 409 si se evaluara el estado

        assert (pendiente.status_code, asignada.status_code) == (403, 403)
        # El permiso lo decide el servicio (no un `requiere_rol` de ruta): el mensaje es el propio de cancelar
        assert pendiente.json() == {"detail": "No tenés permiso para cancelar esta orden."}
        assert await instantanea(api_sembrada) == antes

    async def test_un_mecanico_con_el_rol_recepcion_vigente_si_cancela(self, api_sembrada):
        await api_sembrada.ejecutar(
            "INSERT INTO asignacion_rol (usuario_id, rol, desde) VALUES (5, 'RECEPCION', now())"
        )
        async with api_sembrada.entrar("mecanico2@example.com") as mecanico:
            respuesta = await mecanico.post("/ordenes/1/cancelar")

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["historial"][-1]["usuario_id"] == 5

    async def test_la_recepcion_con_el_rol_revocado_deja_de_poder_cancelar(self, api_sembrada):
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            await api_sembrada.ejecutar(
                "UPDATE asignacion_rol SET revocada_en = now() WHERE usuario_id = 3 AND rol = 'RECEPCION'"
            )
            respuesta = await recepcion.post("/ordenes/1/cancelar")

        assert respuesta.status_code == 403
        assert (await instantanea(api_sembrada))["ordenes"][0][1] == "PENDIENTE"

    @pytest.mark.parametrize("estado", SIN_ESCRITURAS_ESTADOS)
    async def test_con_permiso_una_orden_no_pendiente_responde_409_sin_escrituras(self, api_sembrada, estado):
        await poner_estado(api_sembrada, 2, estado)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("recepcion@example.com") as recepcion:
            respuesta = await recepcion.post("/ordenes/2/cancelar")

        assert respuesta.status_code == 409
        assert respuesta.json()["detail"].startswith("La orden ya está")
        assert "no se puede cancelar" in respuesta.json()["detail"]
        assert await instantanea(api_sembrada) == antes

    async def test_el_mensaje_409_de_una_orden_terminada(self, api_sembrada):
        await poner_estado(api_sembrada, 2, "TERMINADA")
        async with api_sembrada.entrar("admin@example.com") as admin:
            respuesta = await admin.post("/ordenes/2/cancelar")

        assert respuesta.json() == {"detail": "La orden ya está terminada: no se puede cancelar."}

    async def test_el_dueno_sobre_su_orden_terminada_recibe_409(self, api_sembrada):
        await poner_estado(api_sembrada, 1, "TERMINADA")
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("cliente@example.com") as laura:
            respuesta = await laura.post("/ordenes/1/cancelar")

        assert respuesta.status_code == 409
        assert await instantanea(api_sembrada) == antes

    async def test_cancelar_dos_veces_responde_409_la_segunda(self, api_sembrada):
        async with api_sembrada.entrar("cliente@example.com") as laura:
            primera = await laura.post("/ordenes/1/cancelar")
            segunda = await laura.post("/ordenes/1/cancelar")

        assert (primera.status_code, segunda.status_code) == (200, 409)
        assert len([f for f in (await instantanea(api_sembrada))["historial"] if f[1] == 1]) == 2

    @pytest.mark.parametrize("usuario", ["recepcion@example.com", "cliente@example.com"])
    @pytest.mark.parametrize("orden_id", [999, 0, 2147483648])
    async def test_una_orden_inexistente_responde_404_antes_que_403(self, api_sembrada, usuario, orden_id):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar(usuario) as sesion:
            respuesta = await sesion.post(f"/ordenes/{orden_id}/cancelar")

        assert respuesta.status_code == 404
        assert respuesta.json() == {"detail": "Orden no encontrada."}
        assert await instantanea(api_sembrada) == antes

    async def test_sin_sesion_responde_401_sin_escrituras(self, api_sembrada):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.anonimo() as anonimo:
            respuesta = await anonimo.post("/ordenes/1/cancelar")

        assert respuesta.status_code == 401
        assert await instantanea(api_sembrada) == antes

    async def test_con_cambio_de_password_pendiente_responde_403(self, api_sembrada):
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("nuevo@example.com") as nuevo:
            respuesta = await nuevo.post("/ordenes/1/cancelar")

        assert respuesta.status_code == 403
        assert respuesta.json() == {"detail": "Tenés que cambiar tu contraseña antes de continuar."}
        assert await instantanea(api_sembrada) == antes

    async def test_una_falla_a_mitad_de_cancelar_no_deja_ninguna_escritura(self, api_sembrada, monkeypatch):
        from app.modules.ordenes.repository import HistorialEstadoOrdenRepository

        async def falla(self, linea):
            raise RuntimeError("falla inyectada")

        monkeypatch.setattr(HistorialEstadoOrdenRepository, "add", falla)
        antes = await instantanea(api_sembrada)
        async with api_sembrada.entrar("cliente@example.com") as laura:
            with pytest.raises(RuntimeError, match="falla inyectada"):
                await laura.post("/ordenes/1/cancelar")

        assert await instantanea(api_sembrada) == antes


class TestRutasPublicadas:
    async def test_openapi_publica_iniciar_y_cancelar_como_post_sin_cuerpo(self, api_sembrada):
        paths = api_sembrada.app.openapi()["paths"]

        for accion in ("iniciar", "cancelar"):
            operaciones = paths[f"/ordenes/{{orden_id}}/{accion}"]
            assert set(operaciones) == {"post"}
            assert "requestBody" not in operaciones["post"]
            assert "200" in operaciones["post"]["responses"]
