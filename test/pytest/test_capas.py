"""Inspección de capas (spec persistencia-transaccional, EJ-6, RT-TX-02/05, B-1/B-2/B-8).

Pruebas estáticas sobre el AST del código de `app/`, `main.py` y `seed.py`: no
necesitan base de datos. Miran llamadas reales (no texto), así que los
comentarios y docstrings que nombran `commit()` no cuentan.
"""

import ast
from pathlib import Path

import pytest

from app.core.repository import BaseRepository
from app.modules.ordenes.repository import HistorialEstadoOrdenRepository
from app.modules.repuestos.repository import HistorialPrecioRepository, MovimientoStockRepository

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


@pytest.mark.parametrize("nombre", ["service.py", "router.py"])
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


# --- RN-15 en la capa de aplicación (EJ-7, spec persistencia-transaccional, design D8) -------------

REPOSITORIOS_DE_SOLO_AGREGADO = (
    HistorialEstadoOrdenRepository, MovimientoStockRepository, HistorialPrecioRepository,
)
PREFIJOS_DE_MODIFICACION = ("update", "delete", "soft_delete", "remove", "actualizar", "modificar", "borrar", "eliminar")


def _ofensas_de_solo_agregado(clase: type) -> list[str]:
    """Todo lo que permitiría modificar o borrar: herencia del repositorio genérico o métodos de escritura."""
    ofensas = ["hereda de BaseRepository (trae update y delete)"] if issubclass(clase, BaseRepository) else []
    ofensas += [
        f"expone {nombre}()" for nombre in dir(clase)
        if nombre.lower().startswith(PREFIJOS_DE_MODIFICACION) and callable(getattr(clase, nombre))
    ]
    return ofensas


@pytest.mark.parametrize("repositorio", REPOSITORIOS_DE_SOLO_AGREGADO, ids=lambda clase: clase.__name__)
def test_los_repositorios_de_solo_agregado_no_modifican_ni_borran(repositorio):
    """Caracterización: ya era así; la prueba lo fija. El alta sigue disponible."""
    assert _ofensas_de_solo_agregado(repositorio) == []
    assert callable(repositorio.add)


def test_el_detector_de_solo_agregado_ve_un_update_propio_y_la_herencia_del_repositorio_generico():
    """Sensibilidad: el detector falla con clases que sí modifican, así que su `[]` no es vacío."""

    class ConUpdate:
        async def add(self, linea): ...
        async def update(self, linea): ...

    class ConSoftDelete:
        async def soft_delete(self, linea): ...

    class Heredado(BaseRepository):
        pass

    assert _ofensas_de_solo_agregado(ConUpdate) == ["expone update()"]
    assert _ofensas_de_solo_agregado(ConSoftDelete) == ["expone soft_delete()"]
    assert "hereda de BaseRepository (trae update y delete)" in _ofensas_de_solo_agregado(Heredado)
    assert {"expone update()", "expone delete()"} <= set(_ofensas_de_solo_agregado(Heredado))


# --- intento_acceso: la excepción declarada en el código (EJ-7, spec autenticacion-sesiones, design D5) ---

SERVICIO_USUARIOS = RAIZ / "app" / "modules" / "usuarios" / "service.py"
ROUTER_USUARIOS = RAIZ / "app" / "modules" / "usuarios" / "router.py"
UOW_USUARIOS = RAIZ / "app" / "modules" / "usuarios" / "unit_of_work.py"
# Frases de la consigna (Ej. 7, RT-SE-09): qué es, por qué existe y cuál es su costo.
FRASES_DE_LA_EXCEPCION = (
    "única escritura del sistema que no comparte la transacción de su petición",
    "el fallo que se quiere contar es el mismo que revierte la petición",
    "deja filas aunque la petición falle",
)


def _normalizar(texto: str) -> str:
    """Minúsculas, sin `#` ni comillas de docstring y con los saltos de línea colapsados."""
    sin_marcas = (linea.strip().lstrip("#").strip() for linea in texto.splitlines())
    return " ".join(" ".join(sin_marcas).replace('"""', " ").lower().split())


def _frases_que_faltan(texto: str) -> list[str]:
    normalizado = _normalizar(texto)
    return [frase for frase in FRASES_DE_LA_EXCEPCION if frase not in normalizado]


def _definicion(ruta: Path, nombre: str) -> tuple[ast.AST, list[str]]:
    texto = ruta.read_text(encoding="utf-8")
    for nodo in ast.walk(ast.parse(texto)):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and nodo.name == nombre:
            return nodo, texto.splitlines()
    raise AssertionError(f"No se encontró {nombre} en {_relativa(ruta)}")


def _comentarios_y_docstring(ruta: Path, nombre: str) -> str:
    """El docstring y los comentarios de línea entera que contiene la definición."""
    nodo, lineas = _definicion(ruta, nombre)
    cuerpo = lineas[nodo.lineno - 1 : nodo.end_lineno]
    comentarios = [linea for linea in cuerpo if linea.strip().startswith("#")]
    return "\n".join([ast.get_docstring(nodo) or "", *comentarios])


def _comentarios_de_los_intentos_de_iniciar_sesion() -> list[str]:
    """El bloque de comentarios pegado a cada `async with intentos:` que escribe un intento."""
    nodo, lineas = _definicion(SERVICIO_USUARIOS, "iniciar_sesion")
    bloques = []
    for sub in ast.walk(nodo):
        escribe = isinstance(sub, ast.AsyncWith) and any(
            isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "add"
            for item in sub.body for c in ast.walk(item)
        )
        if not (escribe and isinstance(sub.items[0].context_expr, ast.Name) and sub.items[0].context_expr.id == "intentos"):
            continue
        previas, indice = [], sub.lineno - 2
        while indice >= 0 and lineas[indice].strip().startswith("#"):
            previas.insert(0, lineas[indice])
            indice -= 1
        bloques.append((sub.lineno, "\n".join(previas)))
    return [texto for _, texto in sorted(bloques)]


def _lugares_que_declaran_la_excepcion() -> dict[str, str]:
    lugares = {
        "get_session_intentos": _comentarios_y_docstring(ROUTER_USUARIOS, "get_session_intentos"),
        "UnitOfWorkIntentoAcceso": _comentarios_y_docstring(UOW_USUARIOS, "UnitOfWorkIntentoAcceso"),
    }
    for posicion, texto in enumerate(_comentarios_de_los_intentos_de_iniciar_sesion(), start=1):
        lugares[f"iniciar_sesion, escritura {posicion}"] = texto
    return lugares


def test_iniciar_sesion_escribe_el_intento_en_dos_puntos():
    """El bloqueo (429) y el resultado del login: si cambia la forma, esta prueba lo avisa a la vez que la de comentarios."""
    assert len(_comentarios_de_los_intentos_de_iniciar_sesion()) == 2


@pytest.mark.parametrize("lugar", list(_lugares_que_declaran_la_excepcion()))
def test_el_codigo_declara_la_excepcion_y_su_costo(lugar):
    """D5: sesión propia de los intentos, UoW dedicado y punto de confirmación dicen qué es, por qué y su costo."""
    assert _frases_que_faltan(_lugares_que_declaran_la_excepcion()[lugar]) == []


def test_el_detector_de_la_excepcion_acepta_frases_partidas_en_lineas_y_acusa_las_ausentes():
    """Sensibilidad: con el texto completo (partido en comentarios) no falta nada; con uno parcial falta lo demás."""
    completo = (
        "# Única escritura del sistema que no comparte la transacción\n"
        "# de su petición: el fallo que se quiere contar es el mismo que\n"
        "# revierte la petición. Costo: deja filas aunque la petición falle.\n"
    )
    parcial = "# Única escritura del sistema que no comparte la transacción de su petición.\n"
    assert _frases_que_faltan(completo) == []
    assert _frases_que_faltan(parcial) == list(FRASES_DE_LA_EXCEPCION[1:])
    assert _frases_que_faltan("# otra sesión/transacción y una conexión adicional") == list(FRASES_DE_LA_EXCEPCION)


# --- La fábrica de sesiones sólo se abre en dos lugares (EJ-7, spec autenticacion-sesiones, design D5/D9) ---

def _archivos_de_la_aplicacion() -> list[Path]:
    """`app/` y `main.py`; `seed.py` es un script con su propio motor y queda fuera."""
    return [*sorted((RAIZ / "app").rglob("*.py")), RAIZ / "main.py"]


def _nombre(ruta: Path) -> str:
    """Ruta relativa a la raíz del proyecto; sólo el nombre del archivo si es uno temporal de una prueba."""
    return _relativa(ruta) if RAIZ in ruta.parents else ruta.name


class _Aperturas(ast.NodeVisitor):
    """Función (la más interna) desde la que se lee o llama `fabrica_sesiones`; la asignación en el lifespan no cuenta."""

    def __init__(self) -> None:
        self.funciones: list[str] = []
        self.encontradas: list[str] = []

    def _visitar_funcion(self, nodo) -> None:
        self.funciones.append(nodo.name)
        self.generic_visit(nodo)
        self.funciones.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _visitar_funcion

    def visit_Attribute(self, nodo: ast.Attribute) -> None:
        if nodo.attr == "fabrica_sesiones" and isinstance(nodo.ctx, ast.Load):
            self.encontradas.append(self.funciones[-1] if self.funciones else "<módulo>")
        self.generic_visit(nodo)


def _aperturas_de_la_fabrica(rutas: list[Path]) -> list[tuple[str, str]]:
    aperturas = []
    for ruta, arbol in _arboles(rutas):
        visitante = _Aperturas()
        visitante.visit(arbol)
        aperturas += [(_nombre(ruta), funcion) for funcion in visitante.encontradas]
    return sorted(aperturas)


def _usos_de_la_sesion_de_intentos(rutas: list[Path]) -> dict[str, list[str]]:
    """Por cada función que recibe `SesionIntentosDep`: en qué se usa ese parámetro (llamadas a las que se pasa u otro uso)."""
    consumidores: dict[str, list[str]] = {}
    for _, arbol in _arboles(rutas):
        padres = {hijo: padre for padre in ast.walk(arbol) for hijo in ast.iter_child_nodes(padre)}
        for funcion in ast.walk(arbol):
            if not isinstance(funcion, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            parametros = [a.arg for a in funcion.args.args + funcion.args.kwonlyargs
                          if a.annotation is not None and ast.unparse(a.annotation) == "SesionIntentosDep"]
            for parametro in parametros:
                usos = []
                for nodo in ast.walk(funcion):
                    if isinstance(nodo, ast.Name) and nodo.id == parametro and isinstance(nodo.ctx, ast.Load):
                        padre = padres[nodo]
                        if isinstance(padre, ast.Call) and nodo in padre.args and isinstance(padre.func, ast.Name):
                            usos.append(padre.func.id)
                        else:
                            usos.append(f"otro uso: {ast.unparse(padre)}")
                consumidores[funcion.name] = sorted(usos)
    return consumidores


def _referencias(rutas: list[Path], nombre: str) -> list[str]:
    return sorted(
        _nombre(ruta) for ruta, arbol in _arboles(rutas)
        for nodo in ast.walk(arbol) if isinstance(nodo, ast.Name) and nodo.id == nombre
    )


def test_la_fabrica_de_sesiones_solo_se_abre_en_dos_lugares():
    """Caracterización: la sesión por petición y la de los intentos de acceso son las únicas aperturas."""
    assert _aperturas_de_la_fabrica(_archivos_de_la_aplicacion()) == [
        ("app/core/database.py", "get_session"),
        ("app/modules/usuarios/router.py", "get_session_intentos"),
    ]


def test_la_sesion_de_intentos_solo_alimenta_al_uow_de_intentos():
    """Caracterización: `get_session_intentos` llega a un único consumidor y éste sólo construye `UnitOfWorkIntentoAcceso`."""
    archivos = _archivos_de_la_aplicacion()
    assert _referencias(archivos, "get_session_intentos") == ["app/modules/usuarios/router.py"]
    assert _referencias(archivos, "SesionIntentosDep") == ["app/modules/usuarios/router.py"] * 2  # alias + anotación
    assert _usos_de_la_sesion_de_intentos(archivos) == {"construir_uow_intentos": ["UnitOfWorkIntentoAcceso"]}


def test_los_detectores_de_la_fabrica_ven_una_tercera_apertura_y_un_uso_ajeno(tmp_path):
    """Sensibilidad (D9): sobre archivos con una tercera apertura y un uso ajeno, los detectores dejan de dar lo esperado."""
    tercera = tmp_path / "tercera.py"
    tercera.write_text(
        "async def tercera(request):\n"
        "    async with request.app.state.fabrica_sesiones() as sesion:\n"
        "        yield sesion\n"
        "\n"
        "def indirecta(app):\n"
        "    fabrica = app.state.fabrica_sesiones\n"
        "    return fabrica()\n"
        "\n"
        "def lifespan(app, motor):\n"
        "    app.state.fabrica_sesiones = crear(motor)\n",
        encoding="utf-8",
    )
    ajeno = tmp_path / "ajeno.py"
    ajeno.write_text(
        "def construir(sesion: SesionIntentosDep):\n"
        "    return UnitOfWorkUsuario(sesion)\n"
        "\n"
        "async def directo(sesion: SesionIntentosDep):\n"
        "    return await sesion.execute(1)\n",
        encoding="utf-8",
    )
    assert _aperturas_de_la_fabrica([tercera]) == [("tercera.py", "indirecta"), ("tercera.py", "tercera")]
    assert _usos_de_la_sesion_de_intentos([ajeno]) == {
        "construir": ["UnitOfWorkUsuario"],
        "directo": ["otro uso: sesion.execute"],
    }
