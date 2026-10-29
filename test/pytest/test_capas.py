"""Inspección de capas (spec persistencia-transaccional, EJ-6, RT-TX-02/05, B-1/B-2/B-8).

Pruebas estáticas sobre el AST del código de `app/`, `main.py` y `seed.py`: no
necesitan base de datos. Miran llamadas reales (no texto), así que los
comentarios y docstrings que nombran `commit()` no cuentan.
"""

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MODULOS_CON_DATOS = ("usuarios", "clientes", "repuestos", "ordenes")
UOW_BASE = RAIZ / "app" / "core" / "unit_of_work.py"
# Métodos de la sesión que ejecutan SQL: sólo los repositorios pueden llamarlos.
METODOS_DE_EJECUCION = {"execute", "scalar", "scalars", "stream"}


def _arboles(rutas: list[Path]) -> list[tuple[Path, ast.AST]]:
    return [(ruta, ast.parse(ruta.read_text(encoding="utf-8"))) for ruta in rutas]


def _archivos_del_codigo() -> list[Path]:
    codigo = sorted((RAIZ / "app").rglob("*.py"))
    return [*codigo, RAIZ / "main.py", RAIZ / "seed.py"]


def _archivos_de_capa(nombre: str) -> list[Path]:
    """`service.py` o `router.py` de los cuatro módulos con datos."""
    return [RAIZ / "app" / "modules" / modulo / nombre for modulo in MODULOS_CON_DATOS]


def _llamadas(arbol: ast.AST):
    return (nodo for nodo in ast.walk(arbol) if isinstance(nodo, ast.Call))


def _relativa(ruta: Path) -> str:
    return ruta.relative_to(RAIZ).as_posix()


def test_la_unica_llamada_a_commit_esta_en_el_unit_of_work_base():
    """B-8: todo commit lo hace el UoW base; ni repositorios, ni servicios, ni seed."""
    con_commit = []
    for ruta, arbol in _arboles(_archivos_del_codigo()):
        for llamada in _llamadas(arbol):
            funcion = llamada.func
            if isinstance(funcion, ast.Attribute) and funcion.attr == "commit":
                con_commit.append(_relativa(ruta))
    assert con_commit == [_relativa(UOW_BASE)]


def test_el_detector_de_commit_ve_una_llamada_real(tmp_path):
    """Triangula el detector: encuentra `await x.commit()` y no confunde el texto."""
    falso = tmp_path / "falso.py"
    falso.write_text(
        '"""Habla de commit() sin llamarlo."""\n'
        "async def f(sesion):\n"
        "    # commit() en un comentario\n"
        "    await sesion.commit()\n",
        encoding="utf-8",
    )
    llamadas = [
        c for _, arbol in _arboles([falso]) for c in _llamadas(arbol)
        if isinstance(c.func, ast.Attribute) and c.func.attr == "commit"
    ]
    assert len(llamadas) == 1


@pytest.mark.parametrize("modulo", MODULOS_CON_DATOS)
def test_ningun_servicio_construye_su_unit_of_work(modulo):
    """B-2/RT-TX-02: el servicio recibe el UoW por parámetro y lo abre con `async with`."""
    ruta = RAIZ / "app" / "modules" / modulo / "service.py"
    construidos = []
    for _, arbol in _arboles([ruta]):
        for llamada in _llamadas(arbol):
            funcion = llamada.func
            nombre = funcion.id if isinstance(funcion, ast.Name) else getattr(funcion, "attr", "")
            if nombre.startswith("UnitOfWork"):
                construidos.append(nombre)
    assert construidos == []


@pytest.mark.parametrize(
    "nombre",
    [
        pytest.param(
            "service.py",
            marks=pytest.mark.xfail(
                strict=True,
                reason="ordenes/service.py::_es_dueno_del_vehiculo ejecuta SQL hasta la tarea 3.2",
            ),
        ),
        "router.py",
    ],
)
def test_servicios_y_routers_no_ejecutan_sql(nombre):
    """RT-TX-05: toda consulta vive en un repositorio (ni `execute` ni `select(...)` aquí)."""
    ofensores = []
    for ruta, arbol in _arboles(_archivos_de_capa(nombre)):
        for llamada in _llamadas(arbol):
            funcion = llamada.func
            if isinstance(funcion, ast.Attribute) and funcion.attr in METODOS_DE_EJECUCION:
                ofensores.append(f"{_relativa(ruta)}:{llamada.lineno} .{funcion.attr}()")
            if isinstance(funcion, ast.Name) and funcion.id == "select":
                ofensores.append(f"{_relativa(ruta)}:{llamada.lineno} select()")
    assert ofensores == []
