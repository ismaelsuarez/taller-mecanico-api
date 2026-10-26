"""Verifica el helper de paginación (EJ-3, spec listados-paginados).

Envoltorio `{items, total, page, size, pages}` (RT-PG-05): `page ≥ 1`, `size` 1..100
(def. 20), `pages = max(1, ceil(total / size))`, página fuera de rango → 422 con
«La página N no existe: hay M» y cero resultados con una página vacía.
El comportamiento HTTP completo (inyección en `q`, `total` con filtros) se prueba
contra `GET /repuestos` en `test_repuestos.py`.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.paginacion import Pagina, ParametrosPagina, pagina


class TestParametrosPagina:
    def test_defaults(self):
        params = ParametrosPagina.model_validate({})
        assert params.page == 1
        assert params.size == 20

    def test_page_cero_rechazada(self):
        with pytest.raises(ValidationError):
            ParametrosPagina.model_validate({"page": 0})

    def test_page_negativa_rechazada(self):
        with pytest.raises(ValidationError):
            ParametrosPagina.model_validate({"page": -1})

    def test_size_cero_rechazado(self):
        with pytest.raises(ValidationError):
            ParametrosPagina.model_validate({"size": 0})

    def test_size_mayor_a_100_rechazado(self):
        with pytest.raises(ValidationError):
            ParametrosPagina.model_validate({"size": 101})

    def test_limites_aceptados(self):
        params = ParametrosPagina.model_validate({"page": 1, "size": 100})
        assert params.page == 1 and params.size == 100
        params = ParametrosPagina.model_validate({"size": 1})
        assert params.size == 1


class TestCalculoDePaginas:
    def test_dos_paginas(self):
        assert pagina(items=[], total=4, page=1, size=2).pages == 2

    def test_cero_resultados_es_una_pagina(self):
        resultado = pagina(items=[], total=0, page=1, size=20)
        assert resultado.pages == 1
        assert resultado.items == []
        assert resultado.total == 0

    def test_redondeo_hacia_arriba(self):
        assert pagina(items=[], total=5, page=1, size=2).pages == 3

    def test_una_sola_pagina(self):
        assert pagina(items=[], total=3, page=1, size=20).pages == 1


class TestEnvoltorio:
    def test_campos_del_envoltorio(self):
        resultado = pagina(items=[1, 2], total=4, page=1, size=2)
        assert resultado.model_dump() == {
            "items": [1, 2],
            "total": 4,
            "page": 1,
            "size": 2,
            "pages": 2,
        }

    def test_ultima_pagina_es_valida(self):
        resultado = pagina(items=[3, 4], total=4, page=2, size=2)
        assert resultado.page == 2

    def test_pagina_fuera_de_rango_da_422_con_mensaje(self):
        with pytest.raises(HTTPException) as capturado:
            pagina(items=[], total=4, page=3, size=2)
        assert capturado.value.status_code == 422
        assert capturado.value.detail == "La página 3 no existe: hay 2"

    def test_pagina_cero_resultados_consulta_primera(self):
        """Con total 0 sólo existe la página 1: pedirla no es error."""
        resultado = pagina(items=[], total=0, page=1, size=20)
        assert resultado.page == 1
