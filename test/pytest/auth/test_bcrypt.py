"""Primitivas públicas con bcrypt real; la instrumentación sólo observa ejecución."""

import asyncio
import secrets
import threading

import bcrypt
import pytest

from app.core import security


async def test_generar_sal_no_bloquea_el_bucle(monkeypatch):
    hilo_bucle = threading.get_ident()
    generar_sal = bcrypt.gensalt
    hilos = []

    def observar_sal(*args, **kwargs):
        hilos.append(threading.get_ident())
        return generar_sal(*args, **kwargs)

    monkeypatch.setattr(bcrypt, "gensalt", observar_sal)
    security.configurar_semaforo_bcrypt(1)
    password = secrets.token_hex(16)
    resultado = await security.hashear_password(password, rondas=4)

    assert hilos and hilo_bucle not in hilos
    assert await asyncio.to_thread(bcrypt.checkpw, password.encode(), resultado.encode())


async def test_verificar_password_real_y_hash_ficticio(aplicacion_auth, crear_usuario_auth):
    usuario, password = await crear_usuario_auth(email="bcrypt@example.com")
    ficticio = aplicacion_auth.state.hash_ficticio

    assert await security.verificar_password(password, usuario.password_hash) is True
    assert await security.verificar_password(password + "x", usuario.password_hash) is False
    assert await security.verificar_password(password, ficticio) is False
    assert aplicacion_auth.state.hash_ficticio == ficticio


@pytest.mark.parametrize("limite", [1, 2])
async def test_bcrypt_comparte_limite_y_deja_responder_salud(api_auth, monkeypatch, limite):
    security.configurar_semaforo_bcrypt(limite)
    password = secrets.token_hex(16)
    password_hash = await security.hashear_password(password, rondas=7)
    hilo_bucle = threading.get_ident()
    cerrojo = threading.Lock()
    activos = maximos = 0
    hilos = []
    operaciones = []

    def observar(nombre):
        original = getattr(bcrypt, nombre)

        def ejecutar(*args, **kwargs):
            nonlocal activos, maximos
            with cerrojo:
                activos += 1
                maximos = max(maximos, activos)
                hilos.append(threading.get_ident())
                operaciones.append(nombre)
            try:
                return original(*args, **kwargs)  # Nunca se reemplaza el resultado criptográfico.
            finally:
                with cerrojo:
                    activos -= 1

        monkeypatch.setattr(bcrypt, nombre, ejecutar)

    for nombre in ("gensalt", "hashpw", "checkpw"):
        observar(nombre)
    trabajos = asyncio.gather(*[
        operacion
        for _ in range(4)
        for operacion in (
            security.hashear_password(password, rondas=7),
            security.verificar_password(password, password_hash),
        )
    ])
    avances = 0
    while not trabajos.done():
        with cerrojo:
            en_curso = activos > 0
        if en_curso:
            respuesta = await api_auth.get("/health/live")
            assert respuesta.status_code == 200
            avances += 1
        await asyncio.sleep(0)
    resultados = await trabajos

    assert avances > 0
    assert maximos == limite
    assert hilo_bucle not in hilos
    assert {nombre: operaciones.count(nombre) for nombre in set(operaciones)} == {
        "gensalt": 4, "hashpw": 4, "checkpw": 4,
    }
    assert resultados[1::2] == [True] * 4
    for resultado in resultados[::2]:
        assert isinstance(resultado, str)
        assert await security.verificar_password(password, resultado)
