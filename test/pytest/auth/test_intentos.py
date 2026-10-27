"""OPSX 4.1: repositorio/UoW/dependencias públicos sobre PostgreSQL y Alembic."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Request
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.core.database import crear_fabrica_sesiones, get_session
from app.core.unit_of_work import UnitOfWork
from app.modules.usuarios import repository, router
from app.modules.usuarios.models import EventoSeguridad, IntentoAcceso
from app.modules.usuarios.unit_of_work import UnitOfWorkIntentoAcceso

AHORA = datetime(2026, 1, 1, 12, tzinfo=UTC)
CORREO = "intentos@example.com"
IP = "192.0.2.1"


@pytest.fixture
async def fabrica(base_migrada):
    return crear_fabrica_sesiones(base_migrada)


def intento(segundos: float, *, exito=False, email=CORREO, ip=IP):
    return IntentoAcceso(
        cuando=AHORA + timedelta(seconds=segundos), email=email, ip=ip, exito=exito,
    )


async def guardar(fabrica, *filas):
    async with fabrica() as sesion:
        uow = UnitOfWorkIntentoAcceso(sesion)
        async with uow:
            for fila in filas:
                await uow.intentos.add(fila)


async def test_cinco_fallos_en_una_consulta_con_el_mas_antiguo(fabrica, base_migrada):
    await guardar(fabrica, *(intento(s) for s in (-50, -40, -30, -20, -10)))
    consultas = []

    def observar(conn, cursor, sentencia, parametros, contexto, muchos):
        consultas.append(sentencia)

    event.listen(base_migrada.sync_engine, "before_cursor_execute", observar)
    try:
        async with fabrica() as sesion, UnitOfWork(sesion):
            ventana = await repository.IntentoAccesoRepository(sesion).consultar_ventana(
                CORREO, IP, AHORA,
            )
            assert ventana.fallos == 5
            assert ventana.fallo_mas_antiguo == AHORA - timedelta(seconds=50)
            assert len(consultas) == 1
    finally:
        event.remove(base_migrada.sync_engine, "before_cursor_execute", observar)


async def test_ultimo_exito_reinicia_sin_borrar_historia(fabrica):
    filas = [
        intento(-50), intento(-40, exito=True), intento(-30),
        intento(-20, exito=True), intento(-20), intento(-19.999999), intento(-1),
        intento(1, exito=True),  # Un éxito futuro no reinicia la ventana actual.
    ]
    await guardar(fabrica, *filas)
    async with fabrica() as sesion, UnitOfWork(sesion):
        repo = repository.IntentoAccesoRepository(sesion)
        ventana = await repo.consultar_ventana(CORREO, IP, AHORA)
        assert ventana.fallos == 2
        assert ventana.fallo_mas_antiguo == AHORA - timedelta(seconds=19.999999)
        assert {fila.id for fila in await repo.get_all()} == {fila.id for fila in filas}
    await guardar(fabrica, intento(0, exito=True))
    async with fabrica() as sesion, UnitOfWork(sesion):
        repo = repository.IntentoAccesoRepository(sesion)
        ventana = await repo.consultar_ventana(CORREO, IP, AHORA)
        assert ventana.fallos == 0 and ventana.fallo_mas_antiguo is None
        assert await repo.count() == 9


@pytest.mark.parametrize("exito_previo", [None, -120, -60])
async def test_ventana_abierta_en_60s_cerrada_en_ahora(fabrica, exito_previo):
    await guardar(fabrica, *(intento(s) for s in (
        -60.000001, -60, -59.999999, -0.000001, 0, 0.000001,
    )))
    if exito_previo is not None:
        await guardar(fabrica, intento(exito_previo, exito=True))
    async with fabrica() as sesion, UnitOfWork(sesion):
        ventana = await repository.IntentoAccesoRepository(sesion).consultar_ventana(
            CORREO, IP, AHORA,
        )
        assert ventana.fallos == 3
        assert ventana.fallo_mas_antiguo == AHORA - timedelta(seconds=59.999999)


@pytest.mark.parametrize("exito_ajeno", [False, True])
async def test_aislamiento_del_par_tambien_para_el_ultimo_exito(fabrica, exito_ajeno):
    await guardar(
        fabrica, intento(-10),
        *(intento(0, email=CORREO.upper(), exito=exito_ajeno) for _ in range(5)),
        *(intento(0, ip="192.0.2.2", exito=exito_ajeno) for _ in range(5)),
    )
    async with fabrica() as sesion, UnitOfWork(sesion):
        repo = repository.IntentoAccesoRepository(sesion)
        ventana = await repo.consultar_ventana(CORREO, IP, AHORA)
        assert ventana.fallos == 1
        assert ventana.fallo_mas_antiguo == AHORA - timedelta(seconds=10)
        assert await repo.count() == 11


async def test_bloqueado_guardado_como_fallo_cuenta_sin_otro_plazo(fabrica):
    await guardar(fabrica, *(intento(s) for s in (-50, -40, -30, -20, -10)))
    # Representa el resultado bloqueado que guardará 4.2; no ejecuta un login HTTP.
    await guardar(fabrica, intento(0, exito=False))
    async with fabrica() as sesion, UnitOfWork(sesion):
        repo = repository.IntentoAccesoRepository(sesion)
        for avance, cantidad, mas_antiguo in ((0, 6, -50), (10, 5, -40), (20, 4, -30)):
            ventana = await repo.consultar_ventana(
                CORREO, IP, AHORA + timedelta(seconds=avance),
            )
            assert ventana.fallos == cantidad
            assert ventana.fallo_mas_antiguo == AHORA + timedelta(seconds=mas_antiguo)
        assert await repo.count() == 6


async def test_dependencia_independiente_confirma_aunque_peticion_revierta(
    aplicacion_auth, monkeypatch,
):
    app = aplicacion_auth
    request = Request({"type": "http", "app": app})
    cerradas = []
    async with (
        asynccontextmanager(get_session)(request) as normal,
        asynccontextmanager(router.get_session_intentos)(request) as propia,
    ):
        cerrar_real = propia.close

        async def cerrar():
            cerradas.append(True)
            await cerrar_real()

        monkeypatch.setattr(propia, "close", cerrar)
        uow = router.construir_uow_intentos(propia)
        assert propia is not normal and uow.sesion is propia
        assert uow.intentos.sesion is propia
        assert not propia.in_transaction() and not normal.in_transaction()
        normal_uow = router.construir_uow(normal)
        with pytest.raises(RuntimeError, match="petición revertida"):
            async with normal_uow:
                await normal_uow.eventos.add(EventoSeguridad(
                    cuando=AHORA, actor=CORREO, accion="Evento de prueba",
                ))
                async with uow:
                    fila = await uow.intentos.add(intento(0))
                    assert fila.id is not None and await uow.intentos.count() == 1
                    async with app.state.fabrica_sesiones() as observadora:
                        assert await repository.IntentoAccesoRepository(observadora).count() == 0
                assert not propia.in_transaction() and cerradas == []
                raise RuntimeError("petición revertida")
        async with app.state.fabrica_sesiones() as observadora:
            filas = await repository.IntentoAccesoRepository(observadora).get_all()
            assert len(filas) == 1
            assert (filas[0].email, filas[0].ip, filas[0].cuando, filas[0].exito) == (
                CORREO, IP, AHORA, False,
            )
            assert await repository.EventoSeguridadRepository(observadora).count() == 0
    assert cerradas == [True]  # Cierra la dependencia, no el UoW.


@pytest.mark.parametrize("fallo", ["cuerpo", "flush", "commit"])
async def test_fallo_revierte_antes_del_cierre_y_se_propaga(aplicacion_auth, monkeypatch, fallo):
    app = aplicacion_auth
    fabrica = app.state.fabrica_sesiones
    previa = intento(-10)
    await guardar(fabrica, previa)
    cerradas = []
    request = Request({"type": "http", "app": app})
    with pytest.raises(IntegrityError if fallo == "flush" else RuntimeError):
        async with asynccontextmanager(router.get_session_intentos)(request) as sesion:
            cerrar_real = sesion.close

            async def cerrar():
                cerradas.append(True)
                await cerrar_real()

            async def fallar_commit():
                raise RuntimeError("fallo de confirmación")

            monkeypatch.setattr(sesion, "close", cerrar)
            if fallo == "commit":
                monkeypatch.setattr(sesion, "commit", fallar_commit)
            uow = router.construir_uow_intentos(sesion)
            try:
                async with uow:
                    await uow.intentos.add(intento(0))
                    assert await uow.intentos.count() == 2
                    if fallo == "flush":
                        duplicada = intento(0)
                        duplicada.id = previa.id
                        await uow.intentos.add(duplicada)
                    elif fallo == "cuerpo":
                        raise RuntimeError("fallo de operación")
            finally:
                assert not sesion.in_transaction() and cerradas == []
                async with fabrica() as observadora:
                    filas = await repository.IntentoAccesoRepository(observadora).get_all()
                    assert [fila.model_dump() for fila in filas] == [previa.model_dump()]
    assert cerradas == [True]


async def test_lectura_abre_transaccion_y_uow_libera_conexion_sin_cerrar_sesion(aplicacion_auth):
    app = aplicacion_auth
    request = Request({"type": "http", "app": app})
    async with asynccontextmanager(router.get_session_intentos)(request) as sesion:
        uow = router.construir_uow_intentos(sesion)
        assert not sesion.in_transaction() and app.state.motor.pool.checkedout() == 0
        async with uow:
            assert not sesion.in_transaction()  # __aenter__ no oculta autobegin.
            ventana = await uow.intentos.consultar_ventana(CORREO, IP, AHORA)
            assert ventana.fallos == 0 and ventana.fallo_mas_antiguo is None
            assert sesion.in_transaction() and app.state.motor.pool.checkedout() == 1
        assert not sesion.in_transaction() and app.state.motor.pool.checkedout() == 0
        # Aquí irá bcrypt en 4.2; la sesión sigue disponible para la fase de escritura.
        async with uow:
            await uow.intentos.add(intento(0, exito=True))
        assert not sesion.in_transaction() and app.state.motor.pool.checkedout() == 0
