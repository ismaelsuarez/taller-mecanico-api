"""Verifica los endpoints del catálogo de repuestos (EJ-3, spec catalogo-repuestos).

Listado paginado con `q`, detalle, alta con stock inicial (punto único de escritura),
PATCH con línea de historial en la misma transacción, borrado lógico siempre 204,
reposición y las consultas de movimientos y precios. Contra la PostgreSQL real de
test; el esquema lo crea la fixture `api` de `conftest.py` (andamio, A-3).
"""

from decimal import Decimal

from sqlalchemy import text


def _repuesto_body(**extra) -> dict:
    base = {
        "codigo": "FIL-900",
        "descripcion": "Filtro de aceite nuevo",
        "precio": "8500.00",
    }
    base.update(extra)
    return base


async def _crear_repuesto(api, **extra) -> dict:
    cliente, _ = api
    respuesta = await cliente.post("/repuestos", json=_repuesto_body(**extra))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _movimientos(api, repuesto_id: int) -> list[dict]:
    cliente, _ = api
    respuesta = await cliente.get(f"/repuestos/{repuesto_id}/movimientos")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _precios(api, repuesto_id: int) -> list[dict]:
    cliente, _ = api
    respuesta = await cliente.get(f"/repuestos/{repuesto_id}/precios")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


class TestListarRepuestos:
    async def test_listado_paginado_solo_vigentes(self, api):
        cliente, _ = api
        await _crear_repuesto(api, codigo="FIL-001", descripcion="Filtro de aceite")
        await _crear_repuesto(api, codigo="FRE-010", descripcion="Freno delantero")
        dado_de_baja = await _crear_repuesto(api, codigo="BUJ-014", descripcion="Bujía")
        assert (
            await cliente.delete(f"/repuestos/{dado_de_baja['id']}")
        ).status_code == 204

        respuesta = await cliente.get("/repuestos")
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert set(cuerpo) == {"items", "total", "page", "size", "pages"}
        assert cuerpo["total"] == 2
        assert cuerpo["pages"] == 1
        codigos = [item["codigo"] for item in cuerpo["items"]]
        assert "BUJ-014" not in codigos
        assert "password_hash" not in cuerpo["items"][0]

    async def test_listado_vacio_200_con_una_pagina(self, api):
        cliente, _ = api
        respuesta = await cliente.get("/repuestos")
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo == {"items": [], "total": 0, "page": 1, "size": 20, "pages": 1}

    async def test_busqueda_q_por_descripcion(self, api):
        cliente, _ = api
        await _crear_repuesto(api, codigo="FIL-001", descripcion="Filtro de aceite")
        await _crear_repuesto(api, codigo="FRE-010", descripcion="Freno delantero")

        respuesta = await cliente.get("/repuestos", params={"q": "filtro"})
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["total"] == 1
        assert [item["codigo"] for item in cuerpo["items"]] == ["FIL-001"]

    async def test_q_inyectado_devuelve_vacio_y_no_500(self, api):
        cliente, _ = api
        await _crear_repuesto(api)

        respuesta = await cliente.get("/repuestos", params={"q": "' OR '1'='1"})
        assert respuesta.status_code == 200
        assert respuesta.json()["items"] == []
        assert respuesta.json()["total"] == 0

    async def test_pagina_fuera_de_rango_422_mensaje_propio(self, api):
        cliente, _ = api
        await _crear_repuesto(api)

        respuesta = await cliente.get("/repuestos", params={"page": 5})
        assert respuesta.status_code == 422
        assert respuesta.json()["detail"] == "La página 5 no existe: hay 1"

    async def test_size_invalido_422(self, api):
        cliente, _ = api
        assert (await cliente.get("/repuestos", params={"size": 0})).status_code == 422
        assert (await cliente.get("/repuestos", params={"size": 101})).status_code == 422


class TestDetalleRepuesto:
    async def test_detalle_200(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        respuesta = await cliente.get(f"/repuestos/{creado['id']}")
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["codigo"] == "FIL-900"
        assert Decimal(str(cuerpo["precio"])) == Decimal("8500.00")
        assert cuerpo["stock"] == 0

    async def test_repuesto_inexistente_404(self, api):
        cliente, _ = api
        assert (await cliente.get("/repuestos/999999")).status_code == 404

    async def test_repuesto_dado_de_baja_404(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        assert (await cliente.delete(f"/repuestos/{creado['id']}")).status_code == 204
        assert (await cliente.get(f"/repuestos/{creado['id']}")).status_code == 404

    async def test_id_no_entero_422(self, api):
        cliente, _ = api
        assert (await cliente.get("/repuestos/abc")).status_code == 422


class TestCrearRepuesto:
    async def test_alta_con_stock_inicial_201_con_movimiento(self, api):
        cliente, _ = api
        respuesta = await cliente.post(
            "/repuestos", json=_repuesto_body(stock_inicial=5)
        )
        assert respuesta.status_code == 201
        assert respuesta.json()["stock"] == 5

        movimientos = await _movimientos(api, respuesta.json()["id"])
        assert len(movimientos) == 1
        assert movimientos[0]["motivo"] == "Stock inicial"
        assert movimientos[0]["cantidad"] == 5

    async def test_alta_sin_stock_201_sin_movimiento(self, api):
        cliente, _ = api
        respuesta = await cliente.post("/repuestos", json=_repuesto_body())
        assert respuesta.status_code == 201
        assert respuesta.json()["stock"] == 0
        assert await _movimientos(api, respuesta.json()["id"]) == []

    async def test_stock_inicial_negativo_422_y_no_se_crea(self, api):
        cliente, _ = api
        respuesta = await cliente.post(
            "/repuestos", json=_repuesto_body(stock_inicial=-1)
        )
        assert respuesta.status_code == 422
        assert (await cliente.get("/repuestos")).json()["total"] == 0

    async def test_precio_cero_422(self, api):
        cliente, _ = api
        respuesta = await cliente.post(
            "/repuestos", json=_repuesto_body(precio="0")
        )
        assert respuesta.status_code == 422

    async def test_codigo_vigente_repetido_409_mensaje_propio(self, api):
        cliente, _ = api
        await _crear_repuesto(api, codigo="FIL-001")
        respuesta = await cliente.post(
            "/repuestos", json=_repuesto_body(codigo="FIL-001")
        )
        assert respuesta.status_code == 409
        detalle = respuesta.json()["detail"].lower()
        assert "código" in detalle
        for fragmento in ("unique", "constraint", "insert", "asyncpg"):
            assert fragmento not in detalle

    async def test_codigo_reutilizable_tras_la_baja_201(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api, codigo="FIL-001")
        assert (await cliente.delete(f"/repuestos/{creado['id']}")).status_code == 204
        respuesta = await cliente.post(
            "/repuestos", json=_repuesto_body(codigo="FIL-001")
        )
        assert respuesta.status_code == 201

    async def test_campo_extra_422(self, api):
        cliente, _ = api
        respuesta = await cliente.post(
            "/repuestos", json=_repuesto_body(stock=10)
        )
        assert respuesta.status_code == 422


class TestActualizarRepuesto:
    async def test_precio_nuevo_con_linea_de_historial_200(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)

        respuesta = await cliente.patch(
            f"/repuestos/{creado['id']}", json={"precio": "9200.00"}
        )
        assert respuesta.status_code == 200
        assert Decimal(str(respuesta.json()["precio"])) == Decimal("9200.00")

        historial = await _precios(api, creado["id"])
        assert len(historial) == 1
        assert Decimal(str(historial[0]["precio_anterior"])) == Decimal("8500.00")
        assert Decimal(str(historial[0]["precio_nuevo"])) == Decimal("9200.00")

    async def test_precio_igual_no_deja_linea(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)

        respuesta = await cliente.patch(
            f"/repuestos/{creado['id']}",
            json={"precio": "8500.00", "descripcion": "Otra descripción"},
        )
        assert respuesta.status_code == 200
        assert respuesta.json()["descripcion"] == "Otra descripción"
        assert await _precios(api, creado["id"]) == []

    async def test_solo_descripcion_no_toca_el_precio(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)

        respuesta = await cliente.patch(
            f"/repuestos/{creado['id']}", json={"descripcion": "Filtro reemplazo"}
        )
        assert respuesta.status_code == 200
        assert respuesta.json()["descripcion"] == "Filtro reemplazo"
        assert Decimal(str(respuesta.json()["precio"])) == Decimal("8500.00")
        assert await _precios(api, creado["id"]) == []

    async def test_repuesto_inexistente_404(self, api):
        cliente, _ = api
        respuesta = await cliente.patch(
            "/repuestos/999999", json={"precio": "100.00"}
        )
        assert respuesta.status_code == 404

    async def test_stock_en_patch_422(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        respuesta = await cliente.patch(
            f"/repuestos/{creado['id']}", json={"stock": 99}
        )
        assert respuesta.status_code == 422
        detalle = await cliente.get(f"/repuestos/{creado['id']}")
        assert detalle.json()["stock"] == 0

    async def test_precio_nulo_422_nunca_500(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        respuesta = await cliente.patch(
            f"/repuestos/{creado['id']}", json={"precio": None}
        )
        assert respuesta.status_code == 422
        assert (await cliente.get(f"/repuestos/{creado['id']}")).status_code == 200


class TestBorrarRepuesto:
    async def test_baja_204_incluso_con_orden_abierta(self, api):
        cliente, motor = api
        creado = await _crear_repuesto(api)

        # Cliente + vehículo + orden PENDIENTE que usa el repuesto (item_orden).
        vehiculo = (
            await cliente.post(
                "/clientes",
                json={
                    "nombre": "Cliente Orden",
                    "documento": "DNI-80001",
                    "telefono": "11-8000-1111",
                },
            )
        ).json()["id"]
        auto = (
            await cliente.post(
                f"/clientes/{vehiculo}/vehiculos",
                json={"patente": "ORD111AA", "marca": "Ford", "modelo": "Ka", "anio": 2018},
            )
        ).json()["id"]
        async with motor.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO orden_trabajo (vehiculo_id, estado, falla, creada_en, total) "
                    "VALUES (:v, 'PENDIENTE', 'Ruido', now(), 50.00)"
                ),
                {"v": auto},
            )
            await conn.execute(
                text(
                    "INSERT INTO item_orden (orden_id, repuesto_id, cantidad, precio_unitario) "
                    "VALUES ((SELECT max(id) FROM orden_trabajo), :r, 1, 8500.00)"
                ),
                {"r": creado["id"]},
            )

        assert (
            await cliente.delete(f"/repuestos/{creado['id']}")
        ).status_code == 204
        assert (await cliente.get(f"/repuestos/{creado['id']}")).status_code == 404

    async def test_doble_baja_404(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        assert (await cliente.delete(f"/repuestos/{creado['id']}")).status_code == 204
        assert (await cliente.delete(f"/repuestos/{creado['id']}")).status_code == 404

    async def test_repuesto_inexistente_404(self, api):
        cliente, _ = api
        assert (await cliente.delete("/repuestos/999999")).status_code == 404


class TestReponerRepuesto:
    async def test_reposicion_200_con_movimiento_positivo(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api, stock_inicial=10)

        respuesta = await cliente.post(
            f"/repuestos/{creado['id']}/reponer", json={"cantidad": 10}
        )
        assert respuesta.status_code == 200
        assert respuesta.json()["stock"] == 20

        movimientos = await _movimientos(api, creado["id"])
        assert len(movimientos) == 2
        ultimo = movimientos[-1]
        assert ultimo["motivo"] == "Reposición"
        assert ultimo["cantidad"] == 10
        assert ultimo["usuario_id"] == 1  # actor temporal (T-4)

    async def test_motivo_propio(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)

        respuesta = await cliente.post(
            f"/repuestos/{creado['id']}/reponer",
            json={"cantidad": 5, "motivo": "Compra al proveedor"},
        )
        assert respuesta.status_code == 200
        movimientos = await _movimientos(api, creado["id"])
        assert movimientos[-1]["motivo"] == "Compra al proveedor"

    async def test_cantidad_cero_422_y_stock_intacto(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api, stock_inicial=7)
        respuesta = await cliente.post(
            f"/repuestos/{creado['id']}/reponer", json={"cantidad": 0}
        )
        assert respuesta.status_code == 422
        detalle = await cliente.get(f"/repuestos/{creado['id']}")
        assert detalle.json()["stock"] == 7
        assert len(await _movimientos(api, creado["id"])) == 1

    async def test_cantidad_negativa_422(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        respuesta = await cliente.post(
            f"/repuestos/{creado['id']}/reponer", json={"cantidad": -3}
        )
        assert respuesta.status_code == 422

    async def test_motivo_demasiado_largo_422(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        respuesta = await cliente.post(
            f"/repuestos/{creado['id']}/reponer",
            json={"cantidad": 1, "motivo": "x" * 121},
        )
        assert respuesta.status_code == 422

    async def test_repuesto_dado_de_baja_404(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        assert (await cliente.delete(f"/repuestos/{creado['id']}")).status_code == 204
        respuesta = await cliente.post(
            f"/repuestos/{creado['id']}/reponer", json={"cantidad": 1}
        )
        assert respuesta.status_code == 404

    async def test_repuesto_inexistente_404(self, api):
        cliente, _ = api
        respuesta = await cliente.post(
            "/repuestos/999999/reponer", json={"cantidad": 1}
        )
        assert respuesta.status_code == 404


class TestMovimientosYPrecios:
    async def test_movimientos_cronologicos_200(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api, stock_inicial=5)
        await cliente.post(
            f"/repuestos/{creado['id']}/reponer", json={"cantidad": 3}
        )

        movimientos = await _movimientos(api, creado["id"])
        assert [m["motivo"] for m in movimientos] == ["Stock inicial", "Reposición"]
        assert [m["cantidad"] for m in movimientos] == [5, 3]
        assert movimientos[0]["cuando"] <= movimientos[1]["cuando"]

    async def test_precios_con_linea_200(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        await cliente.patch(f"/repuestos/{creado['id']}", json={"precio": "9900.00"})

        historial = await _precios(api, creado["id"])
        assert len(historial) == 1
        assert Decimal(str(historial[0]["precio_nuevo"])) == Decimal("9900.00")

    async def test_movimientos_de_repuesto_inexistente_404(self, api):
        cliente, _ = api
        assert (await cliente.get("/repuestos/999999/movimientos")).status_code == 404

    async def test_precios_de_repuesto_dado_de_baja_404(self, api):
        cliente, _ = api
        creado = await _crear_repuesto(api)
        await cliente.patch(f"/repuestos/{creado['id']}", json={"precio": "9900.00"})
        assert (await cliente.delete(f"/repuestos/{creado['id']}")).status_code == 204
        assert (await cliente.get(f"/repuestos/{creado['id']}/precios")).status_code == 404
