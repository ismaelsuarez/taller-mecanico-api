"""Límites persistibles de repuestos: HTTP contra PostgreSQL real (S1/RN-18)."""

from decimal import Decimal

import pytest
from httpx import AsyncClient


async def _crear(cliente: AsyncClient, **cambios) -> dict:
    datos = {
        "codigo": "LIM-001",
        "descripcion": "Repuesto de prueba",
        "precio": "8500.00",
        "stock_inicial": 7,
    }
    datos.update(cambios)
    respuesta = await cliente.post("/repuestos", json=datos)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _estado(cliente: AsyncClient, repuesto_id: int) -> dict:
    """Observa datos y auditoría persistidos mediante sus lecturas públicas."""
    estado = {}
    for ruta in (
        "/repuestos",
        f"/repuestos/{repuesto_id}",
        f"/repuestos/{repuesto_id}/precios",
        f"/repuestos/{repuesto_id}/movimientos",
    ):
        respuesta = await cliente.get(ruta)
        assert respuesta.status_code == 200, respuesta.text
        estado[ruta] = respuesta.json()
    return estado


@pytest.fixture
async def repuesto_con_historial(api):
    cliente, _ = api
    repuesto = await _crear(cliente)
    respuesta = await cliente.patch(
        f"/repuestos/{repuesto['id']}", json={"precio": "9200.00"}
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


@pytest.mark.parametrize("operacion", ["alta", "patch"])
@pytest.mark.parametrize(
    "precio",
    [
        "0.001", "100000000", "0", "-0.01", "1.234", "99999999.999",
        "NaN", "sNaN", "Infinity", "-Infinity", "1e1000",
        "1.000000000000000000000000000001",
    ],
)
async def test_precio_no_representable_422_sin_cambios(
    api, repuesto_con_historial, operacion, precio
):
    cliente, _ = api
    repuesto_id = repuesto_con_historial["id"]
    antes = await _estado(cliente, repuesto_id)
    datos = {"precio": precio, "descripcion": "No debe guardarse"}
    if operacion == "alta":
        datos.update(codigo="LIM-INVALIDO", stock_inicial=3)
        respuesta = await cliente.post("/repuestos", json=datos)
    else:
        respuesta = await cliente.patch(f"/repuestos/{repuesto_id}", json=datos)

    assert respuesta.status_code == 422, respuesta.text
    assert await _estado(cliente, repuesto_id) == antes


@pytest.mark.parametrize("operacion", ["alta", "reponer"])
@pytest.mark.parametrize(
    "cantidad", [2147483648, 9223372036854775808, -1, 1.5, "NaN", "Infinity"]
)
async def test_cantidad_invalida_422_sin_cambios(
    api, repuesto_con_historial, operacion, cantidad
):
    cliente, _ = api
    repuesto_id = repuesto_con_historial["id"]
    antes = await _estado(cliente, repuesto_id)
    if operacion == "alta":
        respuesta = await cliente.post(
            "/repuestos",
            json={
                "codigo": "LIM-INVALIDO",
                "descripcion": "No debe guardarse",
                "precio": "12.50",
                "stock_inicial": cantidad,
            },
        )
    else:
        respuesta = await cliente.post(
            f"/repuestos/{repuesto_id}/reponer", json={"cantidad": cantidad}
        )

    assert respuesta.status_code == 422, respuesta.text
    assert await _estado(cliente, repuesto_id) == antes


@pytest.mark.parametrize(
    ("stock", "cantidad"), [(2147483647, 1), (2147483646, 2), (7, 2147483647)]
)
async def test_reposicion_acumulada_fuera_de_integer_409_sin_cambios(
    api, stock, cantidad
):
    cliente, _ = api
    repuesto = await _crear(cliente, stock_inicial=stock)
    repuesto_id = repuesto["id"]
    antes = await _estado(cliente, repuesto_id)

    respuesta = await cliente.post(
        f"/repuestos/{repuesto_id}/reponer", json={"cantidad": cantidad}
    )

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json() == {
        "detail": "La reposición supera el máximo de existencias permitido."
    }
    assert await _estado(cliente, repuesto_id) == antes


@pytest.mark.parametrize("operacion", ["alta", "patch"])
@pytest.mark.parametrize(
    ("precio", "esperado"),
    [
        ("0.01", "0.01"),
        ("99999999.99", "99999999.99"),
        ("8500.00", "8500.00"),
        ("12.3400", "12.34"),
        ("99999999.9900", "99999999.99"),
        ("1E+2", "100.00"),
        ("1E-2", "0.01"),
    ],
)
async def test_precio_representable_se_guarda_sin_redondear(
    api, repuesto_con_historial, operacion, precio, esperado
):
    cliente, _ = api
    if operacion == "alta":
        repuesto = await _crear(cliente, codigo="LIM-VALIDO", precio=precio)
    else:
        repuesto = repuesto_con_historial
        respuesta = await cliente.patch(
            f"/repuestos/{repuesto['id']}", json={"precio": precio}
        )
        assert respuesta.status_code == 200, respuesta.text
        repuesto = respuesta.json()
    assert Decimal(repuesto["precio"]) == Decimal(esperado)

    ruta = f"/repuestos/{repuesto['id']}"
    guardado = await cliente.get(ruta)
    assert guardado.status_code == 200
    assert Decimal(guardado.json()["precio"]) == Decimal(esperado)
    historial = await cliente.get(f"{ruta}/precios")
    assert historial.status_code == 200
    lineas = historial.json()
    if operacion == "alta":
        assert lineas == []
    else:
        assert len(lineas) == 2
        assert Decimal(lineas[-1]["precio_anterior"]) == Decimal("9200.00")
        assert Decimal(lineas[-1]["precio_nuevo"]) == Decimal(esperado)


async def test_precio_equivalente_con_ceros_finales_no_agrega_historial(
    api, repuesto_con_historial
):
    cliente, _ = api
    repuesto_id = repuesto_con_historial["id"]
    antes = await _estado(cliente, repuesto_id)

    respuesta = await cliente.patch(
        f"/repuestos/{repuesto_id}", json={"precio": "9200.0000"}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert await _estado(cliente, repuesto_id) == antes


@pytest.mark.parametrize("stock", [0, 1, 2147483647])
async def test_stock_inicial_en_limites_y_movimientos(api, stock):
    cliente, _ = api
    repuesto = await _crear(cliente, stock_inicial=stock)
    ruta = f"/repuestos/{repuesto['id']}"
    guardado = await cliente.get(ruta)
    assert guardado.status_code == 200
    assert guardado.json()["stock"] == stock
    movimientos = await cliente.get(f"{ruta}/movimientos")
    assert movimientos.status_code == 200
    cantidades = [movimiento["cantidad"] for movimiento in movimientos.json()]
    assert cantidades == ([] if stock == 0 else [stock])


@pytest.mark.parametrize(
    ("stock", "cantidad", "esperado"),
    [(0, 2147483647, 2147483647), (2147483646, 1, 2147483647), (7, 5, 12)],
)
async def test_reposicion_representable_conserva_su_movimiento(
    api, stock, cantidad, esperado
):
    cliente, _ = api
    repuesto = await _crear(cliente, stock_inicial=stock)
    ruta = f"/repuestos/{repuesto['id']}"
    antes = await _estado(cliente, repuesto["id"])

    respuesta = await cliente.post(f"{ruta}/reponer", json={"cantidad": cantidad})

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["stock"] == esperado
    despues = await _estado(cliente, repuesto["id"])
    assert despues[ruta]["stock"] == esperado
    assert despues[f"{ruta}/precios"] == antes[f"{ruta}/precios"]
    movimientos = despues[f"{ruta}/movimientos"]
    assert movimientos[:-1] == antes[f"{ruta}/movimientos"]
    assert movimientos[-1]["cantidad"] == cantidad
    assert movimientos[-1]["motivo"] == "Reposición"


async def test_reposicion_cero_422_sin_cambios(api, repuesto_con_historial):
    cliente, _ = api
    repuesto_id = repuesto_con_historial["id"]
    antes = await _estado(cliente, repuesto_id)
    respuesta = await cliente.post(
        f"/repuestos/{repuesto_id}/reponer", json={"cantidad": 0}
    )
    assert respuesta.status_code == 422, respuesta.text
    assert await _estado(cliente, repuesto_id) == antes


async def test_codigo_duplicado_sigue_siendo_409_sin_cambios(api, repuesto_con_historial):
    cliente, _ = api
    repuesto_id = repuesto_con_historial["id"]
    antes = await _estado(cliente, repuesto_id)
    respuesta = await cliente.post(
        "/repuestos",
        json={
            "codigo": repuesto_con_historial["codigo"],
            "descripcion": "No debe guardarse",
            "precio": "12.50",
            "stock_inicial": 1,
        },
    )
    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json() == {"detail": "Ya existe un repuesto con ese código."}
    assert await _estado(cliente, repuesto_id) == antes
