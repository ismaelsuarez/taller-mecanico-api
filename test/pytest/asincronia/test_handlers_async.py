"""Handlers asíncronos sin llamadas bloqueantes (RT-TX-07, US-023/024).

Detector AST sobre `app/modules/*/router.py` y `app/`:

(a) toda función decorada con `@router.get/post/patch/put/delete` (o el router
    de administración) está declarada `async def`;
(b) en `app/` no aparecen `time.sleep`, módulos HTTP síncronos (`requests`) ni
    lectura/escritura de archivos dentro de los handlers.

La sensibilidad se prueba sobre archivos temporales (mismo patrón que el
detector de `commit()` de `test_capas.py`), para que el `[]` no sea vacío.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
DECORADORES_DE_RUTA = {"get", "post", "patch", "put", "delete"}
MODULOS = ("health", "usuarios", "clientes", "repuestos", "ordenes")


def _routers() -> list[Path]:
    return [RAIZ / "app" / "modules" / modulo / "router.py" for modulo in MODULOS]


def _handlers_de(ruta: Path) -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    """Funciones decoradas con un verbo HTTP, sea `router` o `router_administracion`."""
    handlers = []
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorador in nodo.decorator_list:
            llamada = decorador if isinstance(decorador, ast.Call) else None
            atributo = llamada.func if llamada else decorador
            if isinstance(atributo, ast.Attribute) and atributo.attr in DECORADORES_DE_RUTA:
                handlers.append(nodo)
                break
    return handlers


def test_todos_los_handlers_estan_declarados_async_def():
    """RT-TX-07: ni un solo handler `def`; la API no puede bloquear el bucle de eventos."""
    sincronos = [
        f"{ruta.relative_to(RAIZ).as_posix()}:{handler.lineno} {handler.name}"
        for ruta in _routers()
        for handler in _handlers_de(ruta)
        if not isinstance(handler, ast.AsyncFunctionDef)
    ]
    assert sincronos == []
    assert all(_handlers_de(ruta) for ruta in _routers()), "algún router quedó sin handlers"


def _archivos_de_app() -> list[Path]:
    return sorted((RAIZ / "app").rglob("*.py"))


def _llamadas_prohibidas(arbol: ast.AST) -> list[str]:
    """`time.sleep(...)`, `requests.*` y `open(...)` (leer o escribir archivos)."""
    encontradas = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            if nodo.func.attr == "sleep" and ast.unparse(nodo.func.value) == "time":
                encontradas.append(f"time.sleep (línea {nodo.lineno})")
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
            if nodo.func.id == "open":
                encontradas.append(f"open (línea {nodo.lineno})")
    return encontradas


def _imports_sincronos_de_http(arbol: ast.AST) -> list[str]:
    return [
        f"import {ast.unparse(nodo)}"
        for nodo in ast.walk(arbol)
        if isinstance(nodo, (ast.Import, ast.ImportFrom))
        and (any(alias.name == "requests" for alias in nodo.names)
             or (isinstance(nodo, ast.ImportFrom) and nodo.module == "requests"))
    ]


def test_en_app_no_hay_llamadas_bloqueantes():
    """`time.sleep`, `requests` y `open` no existen en `app/`: nada bloquea el bucle."""
    ofensores = []
    for ruta in _archivos_de_app():
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        rel = ruta.relative_to(RAIZ).as_posix()
        ofensores += [f"{rel}: {o}" for o in _llamadas_prohibidas(arbol)]
        ofensores += [f"{rel}: {o}" for o in _imports_sincronos_de_http(arbol)]
    assert ofensores == []


def test_el_detector_de_handlers_acusa_un_def_y_un_time_sleep(tmp_path):
    """Sensibilidad (a): un handler `def` y un `time.sleep` en el código de la app."""
    router_falso = tmp_path / "router.py"
    router_falso.write_text(
        'from fastapi import APIRouter\n'
        "router = APIRouter()\n"
        '@router.get("/falsa")\n'
        "def sincrona():\n"
        "    return {'estado': 'malo'}\n",
        encoding="utf-8",
    )
    handler = _handlers_de(router_falso)[0]
    assert isinstance(handler, ast.FunctionDef), "el detector no acusó el handler `def`"

    codigo_falso = tmp_path / "service.py"
    codigo_falso.write_text(
        "import time\n\n"
        "def tardar():\n"
        "    time.sleep(0.5)\n",
        encoding="utf-8",
    )
    arbol = ast.parse(codigo_falso.read_text(encoding="utf-8"))
    assert _llamadas_prohibidas(arbol) == ["time.sleep (línea 4)"]
