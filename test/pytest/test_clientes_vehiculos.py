"""Verifica los endpoints de clientes y vehículos (EJ-3, spec clientes-vehiculos).

`POST /clientes` (201/409/422), `GET /clientes/{id}` con vehículos vigentes
(200/404), `POST /clientes/{id}/vehiculos` (201/404/409/422) y
`DELETE /vehiculos/{id}` (204/404/409) con reutilización de patente tras la baja.
Contra la PostgreSQL real de test; el esquema lo crea la fixture `api` de
`conftest.py` (andamio de test, regla A-3) con el catálogo y el admin sembrados.
"""

from sqlalchemy import text


def _cliente_bodies(indice: int = 1) -> dict:
    return {
        "nombre": f"Cliente Prueba {indice}",
        "documento": f"DNI-7000{indice}",
        "telefono": f"11-7000-000{indice}",
    }


def _vehiculo_body(patente: str = "AA111BB") -> dict:
    return {"patente": patente, "marca": "Fiat", "modelo": "Cronos", "anio": 2020}


async def _crear_cliente(api, indice: int = 1) -> dict:
    respuesta = await api.post("/clientes", json=_cliente_bodies(indice))
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _crear_vehiculo(api, cliente_id: int, patente: str = "AA111BB") -> dict:
    respuesta = await api.post(
        f"/clientes/{cliente_id}/vehiculos", json=_vehiculo_body(patente)
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


class TestCrearCliente:
    async def test_crea_cliente_201_sin_password_hash(self, api):
        cliente, _ = api
        respuesta = await cliente.post("/clientes", json=_cliente_bodies())
        assert respuesta.status_code == 201
        cuerpo = respuesta.json()
        assert cuerpo["id"] > 0
        assert cuerpo["documento"] == "DNI-70001"
        assert "password_hash" not in cuerpo

    async def test_documento_duplicado_409_mensaje_propio(self, api):
        cliente, _ = api
        await cliente.post("/clientes", json=_cliente_bodies())
        respuesta = await cliente.post("/clientes", json=_cliente_bodies())
        assert respuesta.status_code == 409
        detalle = respuesta.json()["detail"].lower()
        assert "documento" in detalle
        # Sin texto interno de la base (RN-18).
        for fragmento in ("unique", "constraint", "insert", "asyncpg"):
            assert fragmento not in detalle

    async def test_cuerpo_incompleto_422(self, api):
        cliente, _ = api
        respuesta = await cliente.post("/clientes", json={"nombre": "Sin más"})
        assert respuesta.status_code == 422

    async def test_campo_extra_422(self, api):
        cliente, _ = api
        cuerpo = _cliente_bodies() | {"rol": "ADMIN"}
        respuesta = await cliente.post("/clientes", json=cuerpo)
        assert respuesta.status_code == 422


class TestDetalleCliente:
    async def test_detalle_con_vehiculos_vigentes_200(self, api):
        cliente, _ = api
        creado = await _crear_cliente(cliente)
        await _crear_vehiculo(cliente, creado["id"], patente="AA111BB")
        await _crear_vehiculo(cliente, creado["id"], patente="BB222CC")

        # Baja lógica de uno: no debe aparecer en el detalle.
        vehiculos = (await cliente.get(f"/clientes/{creado['id']}")).json()["vehiculos"]
        id_baja = next(v["id"] for v in vehiculos if v["patente"] == "AA111BB")
        assert (await cliente.delete(f"/vehiculos/{id_baja}")).status_code == 204

        respuesta = await cliente.get(f"/clientes/{creado['id']}")
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["nombre"] == "Cliente Prueba 1"
        patentes = [v["patente"] for v in cuerpo["vehiculos"]]
        assert patentes == ["BB222CC"]

    async def test_cliente_inexistente_404(self, api):
        cliente, _ = api
        respuesta = await cliente.get("/clientes/999999")
        assert respuesta.status_code == 404

    async def test_id_no_entero_422_sin_ejecutar_el_handler(self, api):
        cliente, _ = api
        respuesta = await cliente.get("/clientes/abc")
        assert respuesta.status_code == 422


class TestCrearVehiculo:
    async def test_crea_vehiculo_201(self, api):
        cliente, _ = api
        creado = await _crear_cliente(cliente)
        respuesta = await cliente.post(
            f"/clientes/{creado['id']}/vehiculos", json=_vehiculo_body()
        )
        assert respuesta.status_code == 201
        cuerpo = respuesta.json()
        assert cuerpo["cliente_id"] == creado["id"]
        assert cuerpo["patente"] == "AA111BB"

    async def test_cliente_de_la_ruta_inexistente_404(self, api):
        cliente, _ = api
        respuesta = await cliente.post(
            "/clientes/999999/vehiculos", json=_vehiculo_body()
        )
        assert respuesta.status_code == 404

    async def test_patente_vigente_repetida_409(self, api):
        cliente, _ = api
        primero = await _crear_cliente(cliente, indice=1)
        segundo = await _crear_cliente(cliente, indice=2)
        await _crear_vehiculo(cliente, primero["id"], patente="AC456EF")
        respuesta = await cliente.post(
            f"/clientes/{segundo['id']}/vehiculos", json=_vehiculo_body("AC456EF")
        )
        assert respuesta.status_code == 409
        assert "patente" in respuesta.json()["detail"].lower()

    async def test_anio_fuera_de_rango_422(self, api):
        cliente, _ = api
        creado = await _crear_cliente(cliente)
        cuerpo = _vehiculo_body() | {"anio": 1800}
        respuesta = await cliente.post(
            f"/clientes/{creado['id']}/vehiculos", json=cuerpo
        )
        assert respuesta.status_code == 422

    async def test_campo_extra_422(self, api):
        cliente, _ = api
        creado = await _crear_cliente(cliente)
        cuerpo = _vehiculo_body() | {"id": 99}
        respuesta = await cliente.post(
            f"/clientes/{creado['id']}/vehiculos", json=cuerpo
        )
        assert respuesta.status_code == 422


class TestBorrarVehiculo:
    async def test_baja_logica_204_y_doble_baja_404(self, api):
        cliente, _ = api
        creado = await _crear_cliente(cliente)
        vehiculo = await _crear_vehiculo(cliente, creado["id"])

        assert (await cliente.delete(f"/vehiculos/{vehiculo['id']}")).status_code == 204

        # Doble baja → 404 (DD-22) y el dato se conserva.
        segunda = await cliente.delete(f"/vehiculos/{vehiculo['id']}")
        assert segunda.status_code == 404

        motor = api[1]
        async with motor.connect() as conn:
            fila = (
                await conn.execute(
                    text("SELECT borrado_en IS NOT NULL FROM vehiculo WHERE id = :id"),
                    {"id": vehiculo["id"]},
                )
            ).scalar_one()
        assert fila is True

    async def test_vehiculo_inexistente_404(self, api):
        cliente, _ = api
        assert (await cliente.delete("/vehiculos/999999")).status_code == 404

    async def test_vehiculo_con_orden_abierta_409(self, api):
        cliente, motor = api
        creado = await _crear_cliente(cliente)
        vehiculo = await _crear_vehiculo(cliente, creado["id"])

        # Orden PENDIENTE (es_final = false en el catálogo) — sin API de órdenes aún.
        async with motor.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO orden_trabajo (vehiculo_id, estado, falla, creada_en, total) "
                    "VALUES (:v, 'PENDIENTE', 'Ruido al frenar', now(), 100.00)"
                ),
                {"v": vehiculo["id"]},
            )

        respuesta = await cliente.delete(f"/vehiculos/{vehiculo['id']}")
        assert respuesta.status_code == 409
        assert "abierta" in respuesta.json()["detail"].lower()

        # Sigue vigente.
        assert (await cliente.get(f"/clientes/{creado['id']}")).status_code == 200

    async def test_con_orden_final_si_se_puede_dar_de_baja(self, api):
        cliente, motor = api
        creado = await _crear_cliente(cliente)
        vehiculo = await _crear_vehiculo(cliente, creado["id"])

        async with motor.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO orden_trabajo (vehiculo_id, estado, falla, creada_en, total) "
                    "VALUES (:v, 'TERMINADA', 'Cambio de aceite', now(), 100.00)"
                ),
                {"v": vehiculo["id"]},
            )

        assert (await cliente.delete(f"/vehiculos/{vehiculo['id']}")).status_code == 204

    async def test_patente_reutilizable_tras_la_baja_201(self, api):
        cliente, _ = api
        primero = await _crear_cliente(cliente, indice=1)
        segundo = await _crear_cliente(cliente, indice=2)
        vehiculo = await _crear_vehiculo(cliente, primero["id"], patente="ZZ999YY")
        assert (await cliente.delete(f"/vehiculos/{vehiculo['id']}")).status_code == 204

        respuesta = await cliente.post(
            f"/clientes/{segundo['id']}/vehiculos", json=_vehiculo_body("ZZ999YY")
        )
        assert respuesta.status_code == 201
