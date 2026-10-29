"""Contratos de órdenes (6.1, D1, RN-10, SU-07, S-4, DD-40, DD-42).

Sin base de datos: validación de los modelos y traducción de sus rechazos a 422 humano
(sin eco de la entrada) sobre una aplicación mínima que monta los mismos contratos.
"""

from datetime import UTC, datetime
from decimal import Decimal

from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.errores import registrar_traductores
from app.modules.ordenes.schemas import (
    EstadoOrdenCodigo,
    HistorialLectura,
    ItemOrdenCrear,
    ItemOrdenLectura,
    OrdenCrear,
    OrdenDetalle,
    ParametrosOrdenes,
)

CUERPO = {
    "vehiculo_id": 2, "falla": "Ruido al frenar",
    "items": [{"repuesto_id": 2, "cantidad": 1}, {"repuesto_id": 4, "cantidad": 3}],
}
MAXIMO_INT4 = 2_147_483_647
GENERICO = "Revisá los datos enviados: hay un valor no válido."


def _cuerpo(**cambios):
    return {**CUERPO, **cambios}


class TestOrdenCrear:
    def test_un_cuerpo_valido_se_acepta(self):
        orden = OrdenCrear.model_validate(CUERPO)

        assert orden.vehiculo_id == 2
        assert [(i.repuesto_id, i.cantidad) for i in orden.items] == [(2, 1), (4, 3)]

    @pytest.mark.parametrize(
        "cuerpo",
        [
            _cuerpo(total="68000.00"),
            _cuerpo(estado="PENDIENTE"),
            _cuerpo(creada_en="2026-01-01T00:00:00Z"),
            _cuerpo(items=[{"repuesto_id": 2, "cantidad": 1, "precio_unitario": "1.00"}]),
        ],
        ids=["total", "estado", "fecha", "precio_en_item"],
    )
    def test_rechaza_campos_no_declarados(self, cuerpo):
        with pytest.raises(ValidationError) as error:
            OrdenCrear.model_validate(cuerpo)
        assert error.value.errors()[0]["type"] == "extra_forbidden"

    def test_exige_al_menos_un_item(self):
        with pytest.raises(ValidationError) as error:
            OrdenCrear.model_validate(_cuerpo(items=[]))
        assert error.value.errors()[0]["type"] == "too_short"

    @pytest.mark.parametrize(
        "items",
        [
            [{"repuesto_id": 2, "cantidad": 1}, {"repuesto_id": 2, "cantidad": 5}],
            [{"repuesto_id": 7, "cantidad": 1}, {"repuesto_id": 8, "cantidad": 1}, {"repuesto_id": 7, "cantidad": 2}],
        ],
    )
    def test_rechaza_un_repuesto_repetido_sin_repetir_la_entrada(self, items):
        with pytest.raises(ValidationError) as error:
            OrdenCrear.model_validate(_cuerpo(items=items))
        assert error.value.errors()[0]["type"] == "items_repetidos"

    def test_los_repuestos_distintos_con_la_misma_cantidad_no_cuentan_como_repetidos(self):
        orden = OrdenCrear.model_validate(
            _cuerpo(items=[{"repuesto_id": 1, "cantidad": 2}, {"repuesto_id": 2, "cantidad": 2}])
        )
        assert len(orden.items) == 2

    @pytest.mark.parametrize("cantidad", [0, -1, MAXIMO_INT4 + 1, 1.5, "tres"])
    def test_la_cantidad_debe_ser_un_entero_positivo_de_postgres(self, cantidad):
        with pytest.raises(ValidationError):
            ItemOrdenCrear.model_validate({"repuesto_id": 2, "cantidad": cantidad})

    @pytest.mark.parametrize("cantidad", [1, 7, MAXIMO_INT4])
    def test_acepta_cantidades_dentro_del_rango(self, cantidad):
        assert ItemOrdenCrear.model_validate({"repuesto_id": 2, "cantidad": cantidad}).cantidad == cantidad

    @pytest.mark.parametrize("falla", ["", "x" * 501])
    def test_la_falla_va_de_1_a_500_caracteres(self, falla):
        with pytest.raises(ValidationError):
            OrdenCrear.model_validate(_cuerpo(falla=falla))

    @pytest.mark.parametrize("falla", ["x", "x" * 500])
    def test_acepta_los_extremos_de_la_falla(self, falla):
        assert OrdenCrear.model_validate(_cuerpo(falla=falla)).falla == falla

    @pytest.mark.parametrize("valor", [0, -3, MAXIMO_INT4 + 1])
    def test_el_vehiculo_debe_ser_positivo_y_caber_en_la_base(self, valor):
        with pytest.raises(ValidationError):
            OrdenCrear.model_validate(_cuerpo(vehiculo_id=valor))

    def test_el_id_del_repuesto_tambien_se_acota(self):
        with pytest.raises(ValidationError):
            ItemOrdenCrear.model_validate({"repuesto_id": MAXIMO_INT4 + 1, "cantidad": 1})


class TestParametrosOrdenes:
    def test_estado_es_opcional_y_hereda_la_paginacion(self):
        parametros = ParametrosOrdenes()

        assert (parametros.page, parametros.size, parametros.estado) == (1, 20, None)

    @pytest.mark.parametrize("estado", list(EstadoOrdenCodigo))
    def test_acepta_los_cuatro_estados(self, estado):
        assert ParametrosOrdenes(estado=estado.value).estado is estado

    @pytest.mark.parametrize("estado", ["ARCHIVADA", "pendiente", ""])
    def test_rechaza_un_estado_no_declarado(self, estado):
        with pytest.raises(ValidationError):
            ParametrosOrdenes(estado=estado)


class TestOrdenDetalle:
    def test_tiene_la_forma_del_ejemplo_de_la_consigna(self):
        detalle = OrdenDetalle(
            id=3, estado="PENDIENTE", patente="AC456EF", total=Decimal("68000.00"),
            creada_en=datetime(2026, 10, 23, 2, 18, 54, tzinfo=UTC), mecanico_id=None,
            falla="Ruido al frenar", cliente="Laura Cliente",
            items=[ItemOrdenLectura(
                repuesto_id=2, codigo="FRE-010", descripcion="Pastillas de freno delanteras",
                cantidad=1, precio_unitario=Decimal("32000.00"), subtotal=Decimal("32000.00"),
            )],
            historial=[HistorialLectura(
                desde_estado=None, hasta_estado="PENDIENTE", usuario_id=3,
                cuando=datetime(2026, 10, 23, 2, 18, 54, tzinfo=UTC),
            )],
        )

        publico = detalle.model_dump(mode="json")

        assert list(publico) == [
            "id", "estado", "patente", "total", "creada_en", "mecanico_id", "falla",
            "cliente", "items", "historial",
        ]
        assert publico["total"] == "68000.00"
        assert publico["creada_en"] == "2026-10-23T02:18:54Z"
        assert publico["items"][0] == {
            "repuesto_id": 2, "codigo": "FRE-010", "descripcion": "Pastillas de freno delanteras",
            "cantidad": 1, "precio_unitario": "32000.00", "subtotal": "32000.00",
        }
        assert publico["historial"][0] == {
            "desde_estado": None, "hasta_estado": "PENDIENTE", "usuario_id": 3,
            "cuando": "2026-10-23T02:18:54Z",
        }


@pytest.fixture
async def aplicacion_minima():
    """Mismos contratos montados sin base: sólo el traductor de validación es el real."""
    app = FastAPI()
    registrar_traductores(app)

    @app.post("/ordenes")
    async def crear(datos: OrdenCrear) -> dict:
        return {"ok": True}

    @app.get("/ordenes")
    async def listar(params: Annotated[ParametrosOrdenes, Query()]) -> dict:
        return {"ok": True}

    @app.get("/ordenes/{orden_id}")
    async def detalle(orden_id: int) -> dict:
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cliente:
        yield cliente


class TestTraduccion422:
    @pytest.mark.parametrize(
        ("cuerpo", "mensajes"),
        [
            (_cuerpo(items=[]), ["Agregá al menos un ítem a la orden."]),
            (
                _cuerpo(items=[{"repuesto_id": 2, "cantidad": 1}, {"repuesto_id": 2, "cantidad": 2}]),
                ["No repitas el mismo repuesto en la orden: sumá las cantidades en un solo ítem."],
            ),
            (_cuerpo(falla=""), ["Completá la falla con un texto más largo."]),
            (_cuerpo(falla="x" * 501), ["Usá un texto más corto para la falla."]),
            (_cuerpo(total="1.00"), ["Enviá sólo los datos permitidos para esta operación."]),
            (_cuerpo(items=[{"repuesto_id": 2, "cantidad": 0}]), [GENERICO]),
            (_cuerpo(items=[{"repuesto_id": 2, "cantidad": 1, "precio_unitario": "9"}]),
             ["Enviá sólo los datos permitidos para esta operación."]),
            ({"vehiculo_id": 2, "items": CUERPO["items"]}, ["Completá la falla."]),
            (_cuerpo(items="mucho"), ["Revisá los datos enviados: hay un valor no válido."]),
        ],
        ids=["sin_items", "repetido", "falla_vacia", "falla_larga", "total", "cantidad_cero",
             "precio_en_item", "falta_falla", "items_no_lista"],
    )
    async def test_el_alta_invalida_responde_422_humano_sin_eco(self, aplicacion_minima, cuerpo, mensajes):
        respuesta = await aplicacion_minima.post("/ordenes", json=cuerpo)

        assert respuesta.status_code == 422
        assert respuesta.json() == {"detail": [{"msg": m} for m in mensajes]}

    async def test_el_estado_no_declarado_pide_un_valor_valido_sin_repetirlo(self, aplicacion_minima):
        respuesta = await aplicacion_minima.get("/ordenes", params={"estado": "ARCHIVADA"})

        assert respuesta.status_code == 422
        assert respuesta.json() == {"detail": [{"msg": "Elegí un valor válido para el estado."}]}
        assert "ARCHIVADA" not in respuesta.text

    async def test_otro_estado_inventado_recibe_el_mismo_mensaje(self, aplicacion_minima):
        respuesta = await aplicacion_minima.get("/ordenes", params={"estado": "PERDIDA"})

        assert respuesta.json() == {"detail": [{"msg": "Elegí un valor válido para el estado."}]}

    async def test_un_id_no_entero_en_la_ruta_responde_422_humano(self, aplicacion_minima):
        respuesta = await aplicacion_minima.get("/ordenes/abc")

        assert respuesta.status_code == 422
        assert respuesta.json() == {
            "detail": [{"msg": "Ingresá un número entero para la orden seleccionada."}]
        }
