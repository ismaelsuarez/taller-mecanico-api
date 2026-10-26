"""Verifica los contratos estrictos de entrada y salida (EJ-3, spec contratos-estrictos).

Contratos separados de los modelos de tabla (RT-PG-02), `extra="forbid"` en toda
entrada (RT-PG-01), salidas sin `password_hash`, PATCH con `exclude_unset` (RT-PG-03)
y tipos correctos: dinero Decimal, nunca float (S-1).
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.clientes.schemas import (
    ClienteCrear,
    ClienteDetalle,
    ClienteLectura,
    VehiculoCrear,
    VehiculoLectura,
)
from app.modules.repuestos.schemas import (
    RepuestoActualizar,
    RepuestoCrear,
    RepuestoLectura,
    RepuestoReponer,
)


class TestEntradaExtraForbidden:
    def test_cliente_rechaza_campos_no_declarados(self):
        with pytest.raises(ValidationError):
            ClienteCrear.model_validate(
                {"nombre": "Ana", "documento": "DNI-1", "telefono": "11-1", "rol": "ADMIN"}
            )

    def test_vehiculo_rechaza_campos_no_declarados(self):
        with pytest.raises(ValidationError):
            VehiculoCrear.model_validate(
                {"patente": "AA111BB", "marca": "Fiat", "modelo": "Cronos", "anio": 2020, "cliente_id": 1}
            )

    def test_repuesto_crear_rechaza_stock_directo(self):
        """Nadie edita el stock por contrato: sólo `stock_inicial` en el alta (RN-14)."""
        with pytest.raises(ValidationError):
            RepuestoCrear.model_validate(
                {"codigo": "X-1", "descripcion": "Pieza", "precio": "100.00", "stock": 5}
            )

    def test_repuesto_actualizar_rechaza_stock(self):
        with pytest.raises(ValidationError):
            RepuestoActualizar.model_validate({"stock": 10})

    def test_repuesto_actualizar_rechaza_codigo(self):
        with pytest.raises(ValidationError):
            RepuestoActualizar.model_validate({"codigo": "OTRO-1"})


class TestTiposYValidacionDeEntrada:
    def test_repuesto_crear_stock_inicial_default_cero(self):
        datos = RepuestoCrear.model_validate(
            {"codigo": "X-1", "descripcion": "Pieza", "precio": "100.00"}
        )
        assert datos.stock_inicial == 0

    def test_repuesto_crear_stock_inicial_negativo_rechazado(self):
        with pytest.raises(ValidationError):
            RepuestoCrear.model_validate(
                {"codigo": "X-1", "descripcion": "Pieza", "precio": "100.00", "stock_inicial": -1}
            )

    def test_repuesto_precio_cero_rechazado(self):
        with pytest.raises(ValidationError):
            RepuestoCrear.model_validate({"codigo": "X-1", "descripcion": "Pieza", "precio": "0"})

    def test_repuesto_precio_es_decimal(self):
        datos = RepuestoCrear.model_validate(
            {"codigo": "X-1", "descripcion": "Pieza", "precio": "8500.00"}
        )
        assert isinstance(datos.precio, Decimal)

    def test_reponer_cantidad_no_positiva_rechazada(self):
        with pytest.raises(ValidationError):
            RepuestoReponer.model_validate({"cantidad": 0})
        with pytest.raises(ValidationError):
            RepuestoReponer.model_validate({"cantidad": -3})

    def test_reponer_motivo_largo_rechazado(self):
        with pytest.raises(ValidationError):
            RepuestoReponer.model_validate({"cantidad": 1, "motivo": "x" * 121})

    def test_reponer_motivo_default(self):
        datos = RepuestoReponer.model_validate({"cantidad": 5})
        assert datos.motivo == "Reposición"

    def test_vehiculo_anio_fuera_de_rango_rechazado(self):
        with pytest.raises(ValidationError):
            VehiculoCrear.model_validate(
                {"patente": "AA111BB", "marca": "Fiat", "modelo": "Cronos", "anio": 1949}
            )
        with pytest.raises(ValidationError):
            VehiculoCrear.model_validate(
                {"patente": "AA111BB", "marca": "Fiat", "modelo": "Cronos", "anio": 2101}
            )


class TestPatchExcludeUnset:
    def test_solo_precio_no_setea_descripcion(self):
        datos = RepuestoActualizar.model_validate({"precio": "9000.00"})
        assert "precio" in datos.model_fields_set
        assert "descripcion" not in datos.model_fields_set

    def test_solo_descripcion_no_setea_precio(self):
        datos = RepuestoActualizar.model_validate({"descripcion": "Nueva pieza"})
        assert "descripcion" in datos.model_fields_set
        assert "precio" not in datos.model_fields_set

    def test_cuerpo_vacio_es_valido(self):
        datos = RepuestoActualizar.model_validate({})
        assert datos.model_fields_set == set()


class TestSalidasSinPasswordHash:
    def test_cliente_lectura_no_declara_password_hash(self):
        assert "password_hash" not in ClienteLectura.model_fields

    def test_cliente_detalle_no_declara_password_hash(self):
        assert "password_hash" not in ClienteDetalle.model_fields

    def test_vehiculo_lectura_no_declara_password_hash(self):
        assert "password_hash" not in VehiculoLectura.model_fields

    def test_repuesto_lectura_no_declara_password_hash(self):
        assert "password_hash" not in RepuestoLectura.model_fields

    def test_cliente_lectura_serializa_esperado(self):
        cliente = ClienteLectura.model_validate(
            {"id": 1, "nombre": "Laura Cliente", "documento": "DNI-30111222", "telefono": "11-5555-0001"}
        )
        assert cliente.model_dump() == {
            "id": 1,
            "nombre": "Laura Cliente",
            "documento": "DNI-30111222",
            "telefono": "11-5555-0001",
        }

    def test_repuesto_lectura_dinero_decimal(self):
        repuesto = RepuestoLectura.model_validate(
            {"id": 1, "codigo": "FIL-001", "descripcion": "Filtro de aceite", "precio": "8500.00", "stock": 10}
        )
        assert isinstance(repuesto.precio, Decimal)
        assert repuesto.precio == Decimal("8500.00")
        assert "borrado_en" not in RepuestoLectura.model_fields
