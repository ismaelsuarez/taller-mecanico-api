"""Auditoría de carga anticipada (RT-TX-05, T-10, US-023).

Dos inspecciones estáticas sobre el AST (sin base de datos):

1. Ningún `service.py` ni `router.py` ejecuta SQL directo: la única excepción
   permitida es la sonda de preparación de `/health/ready` (SELECT 1 en el
   router, declarado en su propio docstring desde EJ-1).
2. Los métodos de repositorio cuya respuesta SERIALiza relaciones (los de la
   lista, leída del código) declaran `options(...)` con `selectinload` o
   `joinedload` dentro del método (B-4).

La sensibilidad de ambos detectores se prueba sobre archivos temporales.
"""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
MODULOS = ("health", "usuarios", "clientes", "repuestos", "ordenes")
METODOS_DE_EJECUCION = {"execute", "scalar", "scalars", "stream"}
# Única escritura/lectura SQL permitida fuera de un repositorio: la sonda SELECT 1 de /health/ready.
EXCEPCION_SONDA = ("app/modules/health/router.py", "SELECT 1")

# Métodos que devuelven entidades cuya serialización lee relaciones (lista leída del código,
# design D4): cada uno debe declarar options(...) con selectinload/joinedload.
METODOS_CON_RELACIONES = {
    "app/modules/ordenes/repository.py": ["get_detalle_con_items_e_historial"],
    "app/modules/clientes/repository.py": ["get_by_id_con_vehiculos"],
    "app/modules/repuestos/repository.py": ["get_by_id_con_movimientos_y_precios"],
    "app/modules/usuarios/repository.py": ["get_por_id_con_roles", "get_por_email_con_roles"],
}


def _relativa(ruta: Path) -> str:
    return ruta.relative_to(RAIZ).as_posix()


def _arbol(ruta: Path) -> ast.AST:
    return ast.parse(ruta.read_text(encoding="utf-8"))


def _archivos_de_capa() -> list[Path]:
    """`service.py`/`router.py` de los módulos; health no tiene service.py."""
    return [ruta
            for modulo in MODULOS for nombre in ("service.py", "router.py")
            if (ruta := RAIZ / "app" / "modules" / modulo / nombre).exists()]


def _llamadas_de_ejecucion(arbol: ast.AST):
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            if nodo.func.attr in METODOS_DE_EJECUCION:
                yield nodo


def _ejecuciones_fuera_de_repositorio(rutas: list[Path]) -> list[str]:
    """`archivo:línea .método()` de cada ejecución SQL en servicios y routers."""
    ofensores = []
    for ruta in rutas:
        for llamada in _llamadas_de_ejecucion(_arbol(ruta)):
            ofensores.append(f"{_relativa(ruta)}:{llamada.lineno} .{llamada.func.attr}()")
    return ofensores


def test_los_servicios_y_routers_no_ejecutan_sql_directo():
    """RT-TX-05: fuera de la sonda de salud, toda consulta vive en un repositorio."""
    ofensores = [o for o in _ejecuciones_de_todos() if not o.startswith(EXCEPCION_SONDA[0])]
    assert ofensores == []


def _ejecuciones_de_todos() -> list[str]:
    return _ejecuciones_fuera_de_repositorio(_archivos_de_capa())


def test_la_unica_ejecucion_directa_es_la_sonda_de_salud():
    """Caracterización: exactamente un execute() en routers/servicios, el SELECT 1 de /health/ready."""
    assert _ejecuciones_de_todos() == [f"{EXCEPCION_SONDA[0]}:41 .execute()"]
    fuente = (RAIZ / "app" / "modules" / "health" / "router.py").read_text(encoding="utf-8")
    assert EXCEPCION_SONDA[1] in fuente, "la excepción permitida ya no es el SELECT 1 de la sonda"


def test_el_detector_de_ejecucion_acusa_una_consulta_en_un_servicio(tmp_path):
    """Sensibilidad: un service.py con sesion.execute() no pasa desapercibido."""
    falso = tmp_path / "service.py"
    falso.write_text(
        "async def consultar(sesion):\n"
        "    return await sesion.execute('SELECT 1')\n",
        encoding="utf-8",
    )
    # _relativa fallaría con un archivo fuera de RAIZ: se simula con la misma lógica sobre rutas relativas.
    ofensores = []
    for nodo in ast.walk(ast.parse(falso.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in METODOS_DE_EJECUCION:
            ofensores.append(f"service.py:{nodo.lineno} .{nodo.func.attr}()")
    assert ofensores == ["service.py:2 .execute()"]


def _metodo(ruta: Path, nombre: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for nodo in ast.walk(_arbol(ruta)):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"No se encontró {nombre} en {_relativa(ruta)}")


def _declara_precarga(metodo: ast.AST) -> bool:
    """¿El cuerpo llama options(...) con selectinload o joinedload?"""
    for nodo in ast.walk(metodo):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "options":
            nombres = {ast.unparse(arg) for arg in ast.walk(nodo) if isinstance(arg, ast.Call)}
            if any(n.startswith(("selectinload(", "joinedload(")) for n in nombres):
                return True
    return False


def test_los_metodos_que_serializan_relaciones_declaran_su_precarga():
    """B-4/T-10: cada método de la lista precarga dentro de su propio cuerpo."""
    sin_precarga = []
    for archivo, metodos in METODOS_CON_RELACIONES.items():
        ruta = RAIZ / Path(archivo)
        for nombre in metodos:
            if not _declara_precarga(_metodo(ruta, nombre)):
                sin_precarga.append(f"{archivo}::{nombre}")
    assert sin_precarga == []


def test_el_detector_de_precarga_acusa_un_metodo_sin_options(tmp_path):
    """Sensibilidad: un método que devuelve la entidad sin options() no pasa."""
    falso = tmp_path / "repository.py"
    falso.write_text(
        "class Repo:\n"
        "    async def get_con_cosas(self, id_):\n"
        "        resultado = await self.sesion.execute(select(Orden))\n"
        "        return resultado.scalars().first()\n",
        encoding="utf-8",
    )
    ruta = falso
    assert _declara_precarga(_metodo(ruta, "get_con_cosas")) is False
