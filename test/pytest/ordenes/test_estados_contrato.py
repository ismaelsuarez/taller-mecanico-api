"""Contrato de estados (4.2, spec estados-orden): `EstadoOrdenCodigo` y `EstadoOrdenLectura`.

El enum es el contrato de la API (422); la FK al catálogo es la garantía de la base (DD-02).
Debe coincidir con lo que carga el seed real (`seed.py`), no con una copia en el test.
"""

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.modules.ordenes.models import EstadoOrden
from app.modules.ordenes.schemas import EstadoOrdenCodigo, EstadoOrdenLectura

# Literal de la consigna/seed: fuente independiente del enum que se prueba.
CODIGOS_DE_LA_CONSIGNA = ["PENDIENTE", "EN_REPARACION", "TERMINADA", "CANCELADA"]


class TestEstadoOrdenCodigo:
    def test_declara_los_cuatro_codigos_de_la_consigna(self):
        assert [e.value for e in EstadoOrdenCodigo] == CODIGOS_DE_LA_CONSIGNA

    def test_es_un_str_enum_comparable_con_el_texto_de_la_base(self):
        assert EstadoOrdenCodigo.PENDIENTE == "PENDIENTE"
        assert str(EstadoOrdenCodigo.EN_REPARACION) == "EN_REPARACION"

    @pytest.mark.parametrize("valor", ["PERDIDA", "pendiente", "", "ARCHIVADA"])
    def test_rechaza_un_codigo_que_no_esta_declarado(self, valor):
        with pytest.raises(ValueError):
            EstadoOrdenCodigo(valor)


class TestEstadoOrdenLectura:
    def test_se_arma_desde_la_fila_del_catalogo(self):
        fila = EstadoOrden(codigo="TERMINADA", descripcion="Reparación terminada", posicion=3, es_final=True)

        lectura = EstadoOrdenLectura.model_validate(fila, from_attributes=True)

        assert lectura.model_dump() == {
            "codigo": "TERMINADA", "descripcion": "Reparación terminada", "posicion": 3, "es_final": True,
        }

    def test_otra_fila_da_otros_valores(self):
        fila = EstadoOrden(codigo="PENDIENTE", descripcion="Esperando", posicion=1, es_final=False)

        lectura = EstadoOrdenLectura.model_validate(fila, from_attributes=True)

        assert (lectura.codigo, lectura.posicion, lectura.es_final) == ("PENDIENTE", 1, False)

    def test_no_acepta_campos_de_mas(self):
        with pytest.raises(ValidationError):
            EstadoOrdenLectura(codigo="PENDIENTE", descripcion="x", posicion=1, es_final=False, extra=1)


async def test_el_contrato_coincide_con_el_catalogo_sembrado(base_sembrada):
    async with base_sembrada.connect() as conn:
        filas = (await conn.execute(text("SELECT codigo FROM estado_orden ORDER BY posicion"))).all()

    sembrados = [fila[0] for fila in filas]
    assert sembrados == [e.value for e in EstadoOrdenCodigo]
