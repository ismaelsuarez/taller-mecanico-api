"""Apoyo de las pruebas de integridad (EJ-7): lectura de `test/solo_agregado.sql` y ejecución de sus sentencias.

La suite ejecuta el MISMO archivo que se corre a mano con `psql`, así la evidencia manual y la
automática no pueden divergir (design D3). Regla del archivo para que este lector simple alcance:
los comentarios ocupan líneas enteras (`--`), los metacomandos de psql empiezan con una barra
invertida, no hay `;` dentro de literales y cada sentencia termina en `;`.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

RAIZ = Path(__file__).resolve().parents[3]
RUTA_SQL = RAIZ / "test" / "solo_agregado.sql"
TABLAS_DE_SOLO_AGREGADO = ("historial_estado_orden", "movimiento_stock", "historial_precio_repuesto")
TABLAS_DE_LA_EVIDENCIA = (*TABLAS_DE_SOLO_AGREGADO, "orden_trabajo")
RESTRICT_VIOLATION = "23001"
FOREIGN_KEY_VIOLATION = "23503"


def leer_bloques(contenido: str) -> list[tuple[str, str]]:
    """Pares `(comentario previo, sentencia)`; la sentencia queda en una sola línea, sin el `;`."""
    bloques: list[tuple[str, str]] = []
    comentarios: list[str] = []
    sentencia: list[str] = []
    for linea in contenido.splitlines():
        limpia = linea.strip()
        if not sentencia and (not limpia or limpia.startswith("\\")):
            continue
        if not sentencia and limpia.startswith("--"):
            comentarios.append(limpia)
            continue
        sentencia.append(limpia)
        if limpia.endswith(";"):
            bloques.append(("\n".join(comentarios), " ".join(" ".join(sentencia).rstrip(";").split())))
            comentarios, sentencia = [], []
    assert not sentencia, f"Sentencia sin `;` final: {' '.join(sentencia)}"
    return bloques


def leer_sentencias(contenido: str) -> list[str]:
    return [sentencia for _, sentencia in leer_bloques(contenido)]


def es_consulta(sentencia: str) -> bool:
    return sentencia.upper().startswith("SELECT")


def tabla_de(sentencia: str) -> str | None:
    """Tabla destino de un UPDATE / DELETE FROM / INSERT INTO; `None` si es otra cosa."""
    encontrada = re.match(r"(?i)(?:UPDATE|DELETE FROM|INSERT INTO)\s+(\w+)", sentencia)
    return encontrada.group(1) if encontrada else None


@dataclass(frozen=True)
class Resultado:
    """Desenlace de una sentencia ejecutada en su propia transacción."""

    sqlstate: str | None = None
    restriccion: str | None = None
    mensaje: str = ""
    filas: int | None = None


def _atributo(error: DBAPIError, nombre: str):
    """Atributo del error de PostgreSQL: el adaptador de SQLAlchemy y la excepción de asyncpg que envuelve."""
    orig = error.orig
    for candidata in (orig, getattr(orig, "__cause__", None)):
        valor = getattr(candidata, nombre, None)
        if valor:
            return valor
    return None


async def ejecutar(motor, sentencia: str) -> Resultado:
    """Ejecuta una sentencia en su propia transacción (como el autocommit de psql)."""
    try:
        async with motor.begin() as conexion:
            resultado = await conexion.exec_driver_sql(sentencia)
            return Resultado(filas=resultado.rowcount)
    except DBAPIError as error:
        return Resultado(
            sqlstate=_atributo(error, "sqlstate"),
            restriccion=_atributo(error, "constraint_name"),
            mensaje=str(error.orig),
        )


async def consultar(motor, sentencia: str) -> tuple:
    """Primera fila de una consulta (el SELECT de conteos de cierre)."""
    async with motor.connect() as conexion:
        return tuple((await conexion.exec_driver_sql(sentencia)).one())


async def instantanea(motor) -> dict[str, list]:
    """Contenido completo de las cuatro tablas de la evidencia, ordenado por id."""
    datos = {}
    async with motor.connect() as conexion:
        for tabla in TABLAS_DE_LA_EVIDENCIA:  # nombres fijos de este módulo, nunca de un usuario
            datos[tabla] = (await conexion.execute(text(f"SELECT * FROM {tabla} ORDER BY id"))).all()
    return datos


async def exigir_precondicion(motor) -> None:
    """La evidencia sólo vale con la base sembrada: un UPDATE/DELETE sin filas no dispara el trigger."""
    async with motor.connect() as conexion:
        for tabla in TABLAS_DE_SOLO_AGREGADO:
            hay = (await conexion.execute(text(f"SELECT count(*) FROM {tabla} WHERE id = 1"))).scalar_one()
            assert hay == 1, (
                f"Precondición incumplida: {tabla} no tiene la fila id = 1. "
                "Corré `python seed.py` antes de test/solo_agregado.sql."
            )
