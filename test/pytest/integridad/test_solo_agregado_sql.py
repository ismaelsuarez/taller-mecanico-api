"""Evidencia C-14 (EJ-7, spec migraciones-esquema): la suite ejecuta `test/solo_agregado.sql`.

Seis rechazos del disparador (`UPDATE` y `DELETE` sobre las tres tablas de sólo agregado, SQLSTATE
23001) y uno de la clave foránea del catálogo (alta de orden con estado inexistente, 23503), cada
sentencia en su propia transacción y sin cambiar ningún dato. El archivo es el que se corre a mano
con `psql`; la verificación se hace por SQLSTATE y nombre de restricción, no por el texto del servidor.
"""

import re

import pytest

from integridad._apoyo import (
    FOREIGN_KEY_VIOLATION,
    RESTRICT_VIOLATION,
    RUTA_SQL,
    TABLAS_DE_SOLO_AGREGADO,
    consultar,
    ejecutar,
    es_consulta,
    exigir_precondicion,
    instantanea,
    leer_bloques,
    leer_sentencias,
    tabla_de,
)

SENTENCIAS_MODIFICADORAS = 7
ESPERADO_POR_SENTENCIA = [(i, RESTRICT_VIOLATION) for i in range(6)] + [(6, FOREIGN_KEY_VIOLATION)]


def _sentencias() -> list[str]:
    return leer_sentencias(RUTA_SQL.read_text(encoding="utf-8"))


def _modificadoras() -> list[str]:
    return [s for s in _sentencias() if not es_consulta(s)]


class TestEstructuraDelArchivo:
    """Lo que se puede afirmar sin base de datos."""

    def test_siete_sentencias_modificadoras_y_un_select_final(self):
        sentencias = _sentencias()
        assert len(_modificadoras()) == SENTENCIAS_MODIFICADORAS
        assert es_consulta(sentencias[-1]), "El archivo debe cerrar con el SELECT de conteos."
        assert sum(es_consulta(s) for s in sentencias) == 1

    def test_un_update_y_un_delete_por_cada_tabla_de_solo_agregado(self):
        seis = _modificadoras()[:6]
        pares = {(re.match(r"\w+", s).group(0).upper(), tabla_de(s)) for s in seis}
        esperado = {(verbo, tabla) for tabla in TABLAS_DE_SOLO_AGREGADO for verbo in ("UPDATE", "DELETE")}
        assert pares == esperado

    def test_la_septima_es_el_alta_de_una_orden_con_estado_inexistente(self):
        septima = _modificadoras()[6]
        assert tabla_de(septima) == "orden_trabajo"
        assert septima.upper().startswith("INSERT INTO")
        assert "'INEXISTENTE'" in septima

    def test_cada_sentencia_lleva_su_resultado_esperado_en_un_comentario(self):
        for comentario, sentencia in leer_bloques(RUTA_SQL.read_text(encoding="utf-8")):
            assert "Esperado" in comentario, f"Sin resultado esperado: {sentencia}"

    def test_el_encabezado_declara_precondicion_y_comandos_sin_credenciales(self):
        contenido = RUTA_SQL.read_text(encoding="utf-8")
        for requerido in ("python seed.py", "psql", "docker compose exec", r"\set ON_ERROR_STOP off"):
            assert requerido in contenido, f"Falta en el encabezado: {requerido}"
        assert not re.search(r"(?i)pgpassword\s*=\s*\S", contenido), "El archivo no lleva credenciales (S-6)."

    def test_el_lector_ignora_comentarios_y_metacomandos_y_une_lineas(self):
        contenido = (
            "-- encabezado; con punto y coma\n\\set ON_ERROR_STOP off\n\n"
            "-- Esperado: ok\nUPDATE t\n   SET a = 1\n WHERE id = 1;\n"
            "-- Esperado: otro\nDELETE FROM u WHERE id = 2;\n"
        )
        assert leer_sentencias(contenido) == ["UPDATE t SET a = 1 WHERE id = 1", "DELETE FROM u WHERE id = 2"]
        assert leer_bloques(contenido)[1][0] == "-- Esperado: otro"


@pytest.mark.asyncio
class TestRechazosSobreLaBaseSembrada:
    @pytest.mark.parametrize(("indice", "sqlstate"), ESPERADO_POR_SENTENCIA)
    async def test_cada_sentencia_se_rechaza_con_su_codigo_y_no_cambia_nada(
        self, base_sembrada, indice, sqlstate
    ):
        motor = base_sembrada
        await exigir_precondicion(motor)
        antes = await instantanea(motor)

        resultado = await ejecutar(motor, _modificadoras()[indice])

        assert resultado.sqlstate == sqlstate, resultado
        if sqlstate == RESTRICT_VIOLATION:
            assert "sólo agregado" in resultado.mensaje
        else:
            assert resultado.restriccion == "orden_trabajo_estado_fkey"
        assert await instantanea(motor) == antes

    async def test_el_archivo_completo_es_independiente_y_sin_efectos(self, base_sembrada):
        motor = base_sembrada
        await exigir_precondicion(motor)
        antes = await instantanea(motor)

        resultados = [await ejecutar(motor, s) for s in _modificadoras()]

        assert [r.sqlstate for r in resultados] == [sqlstate for _, sqlstate in ESPERADO_POR_SENTENCIA]
        assert await instantanea(motor) == antes
        conteos = await consultar(motor, _sentencias()[-1])
        assert conteos == tuple(len(antes[tabla]) for tabla in antes)
        assert conteos == (3, 4, 1, 2), "Cantidades del seed: historial de estados, movimientos, precios, órdenes."


@pytest.mark.asyncio
class TestDetectorSinSembrar:
    """Triangulación (2.3): sobre la base migrada SIN sembrar, el archivo no demuestra nada.

    Un `UPDATE`/`DELETE` que no encuentra filas no dispara un trigger FOR EACH ROW: las seis
    sentencias terminan sin error. La prueba lo reporta como precondición incumplida, no como éxito.
    """

    async def test_las_seis_sentencias_no_se_rechazan_y_la_precondicion_lo_dice(self, base_migrada):
        motor = base_migrada

        resultados = [await ejecutar(motor, s) for s in _modificadoras()[:6]]

        assert [r.sqlstate for r in resultados] == [None] * 6
        assert [r.filas for r in resultados] == [0] * 6
        with pytest.raises(AssertionError, match=r"Precondición incumplida.*python seed\.py"):
            await exigir_precondicion(motor)

    async def test_la_precondicion_acusa_la_tabla_que_falta(self, base_sembrada):
        motor = base_sembrada
        await exigir_precondicion(motor)  # sembrada: no falla

        async with motor.begin() as conexion:  # TRUNCATE no dispara el trigger por fila (como el seed)
            await conexion.exec_driver_sql("TRUNCATE movimiento_stock RESTART IDENTITY")

        with pytest.raises(AssertionError, match="movimiento_stock no tiene la fila id = 1"):
            await exigir_precondicion(motor)
