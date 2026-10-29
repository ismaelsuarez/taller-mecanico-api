"""Sólo agregado sobre filas creadas por la API (EJ-7, spec migraciones-esquema, design D8/D9).

Caracterización: el disparador ya existe y ya rechaza; estas pruebas no tuvieron un RED previo
(design D9). Su sensibilidad se prueba con la contraparte: quitado el disparador de una tabla, el
mismo `UPDATE` sobre la fila de la API es admitido, así que la afirmación «rechazado» puede fallar.

La actividad usa la API real sobre la base sembrada: cambio de precio, reposición, alta e inicio de
una orden (grupo 1) y la terminación exitosa de la orden 2 tras reponer las bujías, C-12 (grupo 2).
Después se intenta modificar y borrar por SQL cada línea nueva de las tres tablas de sólo agregado.
"""

import pytest

from integridad._apoyo import (
    RESTRICT_VIOLATION,
    TABLAS_DE_SOLO_AGREGADO,
    ejecutar,
    instantanea,
)

MODIFICACIONES = {
    "historial_estado_orden": "UPDATE historial_estado_orden SET hasta_estado = 'CANCELADA' WHERE id = {id}",
    "movimiento_stock": "UPDATE movimiento_stock SET cantidad = 99 WHERE id = {id}",
    "historial_precio_repuesto": "UPDATE historial_precio_repuesto SET precio_nuevo = 1 WHERE id = {id}",
}
BORRADO = "DELETE FROM {tabla} WHERE id = {id}"


async def _ultimos_ids(entorno) -> dict[str, int]:
    return {
        tabla: (await entorno.consulta(f"SELECT max(id) FROM {tabla}"))[0][0]
        for tabla in TABLAS_DE_SOLO_AGREGADO
    }


async def _filas_nuevas(entorno, previos: dict[str, int]) -> dict[str, list[int]]:
    return {
        tabla: [f[0] for f in await entorno.consulta(f"SELECT id FROM {tabla} WHERE id > {previos[tabla]} ORDER BY id")]
        for tabla in TABLAS_DE_SOLO_AGREGADO
    }


async def _precio_reposicion_y_orden_iniciada(entorno) -> None:
    async with entorno.entrar("admin@example.com") as admin:
        assert (await admin.patch("/repuestos/1", json={"precio": "9000.00"})).status_code == 200
        assert (await admin.post("/repuestos/1/reponer", json={"cantidad": 5})).status_code == 200
    async with entorno.entrar("recepcion@example.com") as recepcion:
        alta = await recepcion.post(
            "/ordenes", json={"vehiculo_id": 2, "falla": "Revisión general", "items": [{"repuesto_id": 1, "cantidad": 1}]},
        )
    assert alta.status_code == 201, alta.text
    async with entorno.entrar("mecanico@example.com") as mecanico:
        assert (await mecanico.post(f"/ordenes/{alta.json()['id']}/iniciar")).status_code == 200


async def _reponer_y_terminar_la_orden_2(entorno) -> None:
    async with entorno.entrar("admin@example.com") as admin:
        assert (await admin.post("/repuestos/3/reponer", json={"cantidad": 2})).status_code == 200
    async with entorno.entrar("mecanico@example.com") as mecanico:
        assert (await mecanico.post("/ordenes/2/terminar")).status_code == 200


async def _intentar_modificar_y_borrar(entorno, nuevas: dict[str, list[int]]) -> list[str]:
    """Los intentos que NO terminaron en `restrict_violation` (lista vacía = todos rechazados)."""
    sin_rechazo = []
    for tabla, ids in nuevas.items():
        for id_ in ids:
            for verbo, sql in (("UPDATE", MODIFICACIONES[tabla]), ("DELETE", BORRADO)):
                resultado = await ejecutar(entorno.motor, sql.format(tabla=tabla, id=id_))
                if resultado.sqlstate != RESTRICT_VIOLATION:
                    sin_rechazo.append(f"{verbo} {tabla} id={id_}: {resultado}")
    return sin_rechazo


@pytest.mark.asyncio
class TestFilasEscritasPorLaApi:
    async def test_precio_reposicion_y_orden_iniciada_no_se_pueden_modificar_ni_borrar(self, api_sembrada):
        previos = await _ultimos_ids(api_sembrada)

        await _precio_reposicion_y_orden_iniciada(api_sembrada)

        nuevas = await _filas_nuevas(api_sembrada, previos)
        assert {tabla: len(ids) for tabla, ids in nuevas.items()} == {
            "historial_estado_orden": 2,  # alta (None → PENDIENTE) e inicio (PENDIENTE → EN_REPARACION)
            "movimiento_stock": 1,  # reposición
            "historial_precio_repuesto": 1,  # 8500 → 9000
        }
        antes = await instantanea(api_sembrada.motor)

        assert await _intentar_modificar_y_borrar(api_sembrada, nuevas) == []
        assert await instantanea(api_sembrada.motor) == antes

    async def test_la_terminacion_exitosa_c12_tampoco_se_puede_modificar_ni_borrar(self, api_sembrada):
        previos = await _ultimos_ids(api_sembrada)

        await _reponer_y_terminar_la_orden_2(api_sembrada)

        nuevas = await _filas_nuevas(api_sembrada, previos)
        assert {tabla: len(ids) for tabla, ids in nuevas.items()} == {
            "historial_estado_orden": 1,  # EN_REPARACION → TERMINADA
            "movimiento_stock": 2,  # reposición de las bujías y su salida por la orden
            "historial_precio_repuesto": 0,
        }
        antes = await instantanea(api_sembrada.motor)

        assert await _intentar_modificar_y_borrar(api_sembrada, nuevas) == []
        assert await instantanea(api_sembrada.motor) == antes


@pytest.mark.asyncio
class TestSensibilidadSinElDisparador:
    """Contraparte: sin el disparador de la tabla, el mismo UPDATE sobre la fila de la API se admite."""

    @pytest.mark.parametrize("tabla", TABLAS_DE_SOLO_AGREGADO)
    async def test_quitado_el_disparador_la_modificacion_se_admite_y_el_detector_lo_ve(self, api_sembrada, tabla):
        previos = await _ultimos_ids(api_sembrada)
        await _precio_reposicion_y_orden_iniciada(api_sembrada)
        nuevas = await _filas_nuevas(api_sembrada, previos)
        id_ = nuevas[tabla][0]
        await api_sembrada.ejecutar(f"DROP TRIGGER trg_{tabla}_solo_agregado ON {tabla}")

        resultado = await ejecutar(api_sembrada.motor, MODIFICACIONES[tabla].format(id=id_))

        assert (resultado.sqlstate, resultado.filas) == (None, 1)
        sin_rechazo = await _intentar_modificar_y_borrar(api_sembrada, {tabla: [id_]})
        assert sin_rechazo and all(tabla in linea for linea in sin_rechazo)
