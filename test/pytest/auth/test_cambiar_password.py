"""C-09 parcial: HTTP, bcrypt y PostgreSQL/Alembic reales; sin permisos EJ-5."""

import asyncio
import json
import secrets
import threading
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import jwt
import pytest
from sqlmodel import select

from app.core import security
from app.core.unit_of_work import UnitOfWork
from app.modules.usuarios import router, service
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, Usuario
from app.modules.usuarios.unit_of_work import UnitOfWorkUsuario

from .test_registro import api_auth as api_auth
from .test_registro import estado_guardado

RUTA = "/auth/cambiar-password"


async def test_actual_incorrecta_no_cambia_nada(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch,
):
    usuario, _ = await crear_usuario_auth(email="incorrecta@example.com", debe_cambiar_password=True)
    token = security.emitir_token(usuario.id, [], aplicacion_auth.state.settings)
    antes = await estado_guardado(aplicacion_auth)

    async def no_hashear(*args):
        pytest.fail("No calcular un hash nuevo cuando la contraseña actual no es correcta")

    monkeypatch.setattr(security, "hashear_password", no_hashear)
    respuesta = await api_auth.post(RUTA, headers={"Cookie": f"access_token={token}"}, json={
        "password_actual": secrets.token_hex(16), "password_nueva": secrets.token_hex(16),
    })
    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "La contraseña actual no es correcta."}
    assert respuesta.headers["content-type"] == "application/json"
    assert "set-cookie" not in respuesta.headers and "retry-after" not in respuesta.headers
    assert await estado_guardado(aplicacion_auth) == antes


@pytest.mark.parametrize("actual,nueva,segura", [
    ("a" * 72, "ñ" * 36, False), ("ñ" * 36, "b" * 72, True),
])
async def test_cambio_atomico_revoca_en_el_mismo_segundo(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch, actual, nueva, segura,
):
    app = aplicacion_auth
    usuario, _ = await crear_usuario_auth(
        email="cambio@example.com", roles=("CLIENTE", "ADMIN", "MECANICO"),
        debe_cambiar_password=True,
    )
    password_hash = await security.hashear_password(actual, 4)
    async with app.state.fabrica_sesiones() as sesion, UnitOfWork(sesion):
        guardado = await sesion.get(Usuario, usuario.id)
        guardado.password_hash = password_hash
    instante = datetime.now(UTC).replace(microsecond=100000)

    class Reloj:
        @staticmethod
        def now(zona):
            return instante

    monkeypatch.setattr(service, "datetime", Reloj)
    monkeypatch.setattr(security, "datetime", Reloj)
    app.state.settings.access_token_expire_seconds = 97
    app.state.settings.cookie_secure = segura
    login = await api_auth.post("/auth/login", json={"email": usuario.email, "password": actual})
    assert login.status_code == 200
    assert login.json() == {"mensaje": "Sesión iniciada", "debe_cambiar_password": True,
                            "expira_en_segundos": 97}
    vieja = SimpleCookie(login.headers["set-cookie"])["access_token"].value
    instante += timedelta(microseconds=500000)
    async with app.state.fabrica_sesiones() as sesion, UnitOfWork(sesion):
        for rol in (await sesion.scalars(select(AsignacionRol))).all():
            if rol.rol == "ADMIN":
                rol.revocada_en = instante
            elif rol.rol == "MECANICO":
                rol.vence_en = instante
    antes = await estado_guardado(app)
    api_auth.cookies.clear()
    respuesta = await api_auth.post(RUTA, json={"password_actual": actual, "password_nueva": nueva},
                                    headers={"Cookie": f"access_token={vieja}"})
    assert respuesta.status_code == 200
    assert respuesta.json() == {"mensaje": "Contraseña actualizada", "debe_cambiar_password": False,
                                "expira_en_segundos": 97}
    assert respuesta.headers["content-type"] == "application/json"
    assert "retry-after" not in respuesta.headers
    assert len(respuesta.headers.get_list("set-cookie")) == 1
    cookie = SimpleCookie(respuesta.headers["set-cookie"])["access_token"]
    assert cookie["httponly"] and cookie["samesite"].lower() == "lax"
    assert (cookie["max-age"], cookie["path"], cookie["domain"]) == ("97", "/", "")
    assert bool(cookie["secure"]) is segura and cookie.value != vieja
    claims = security.verificar_token(cookie.value, app.state.settings)
    assert claims == {"sub": str(usuario.id), "iat": instante.timestamp(),
                      "exp": instante.timestamp() + 97, "roles": ["CLIENTE"]}
    assert int(security.verificar_token(vieja, app.state.settings)["iat"]) == int(claims["iat"])
    despues = await estado_guardado(app)
    cambiado = despues[0][0]
    assert cambiado == {**antes[0][0], "password_hash": cambiado["password_hash"],
                       "password_cambiada_en": instante, "debe_cambiar_password": False}
    assert cambiado["password_hash"] != password_hash
    assert await security.verificar_password(nueva, cambiado["password_hash"])
    assert not await security.verificar_password(actual, cambiado["password_hash"])
    assert despues[1:3] == antes[1:3] and despues[4] == antes[4]
    assert despues[3] == [{"id": despues[3][0]["id"], "cuando": instante,
                          "actor": usuario.email, "accion": "Cambio de contraseña"}]
    for token, codigo in ((vieja, 401), (cookie.value, 200)):
        api_auth.cookies.clear()
        identidad = await api_auth.get("/auth/yo", headers={"Cookie": f"access_token={token}"})
        assert identidad.status_code == codigo
        assert identidad.json() == ({"detail": "La sesión no es válida. Volvé a iniciar sesión."}
            if codigo == 401 else {"usuario": {"id": usuario.id, "email": usuario.email,
                "nombre": usuario.nombre, "debe_cambiar_password": False},
                "roles_vigentes": ["CLIENTE"], "roles_token": ["CLIENTE"]})
        assert "set-cookie" not in identidad.headers
    assert await estado_guardado(app) == despues
    for clave, codigo in ((actual, 401), (nueva, 200)):
        ingreso = await api_auth.post("/auth/login", json={"email": usuario.email, "password": clave})
        assert ingreso.status_code == codigo
        assert ingreso.json() == ({"detail": "El correo o la contraseña no son correctos."}
            if codigo == 401 else {"mensaje": "Sesión iniciada", "debe_cambiar_password": False,
                                   "expira_en_segundos": 97})
        assert ("set-cookie" in ingreso.headers) is (codigo == 200)
    final = await estado_guardado(app)
    assert final[:4] == despues[:4]
    assert [fila["exito"] for fila in final[4]] == [True, False, True]


@pytest.mark.parametrize("campo", ["password_actual", "password_nueva"])
@pytest.mark.parametrize("caso", ["73ascii", "37ñ", "ausente", "tipo", "extra", "json"])
async def test_entrada_invalida_sin_eco_bcrypt_ni_escrituras(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch, campo, caso,
):
    usuario, password = await crear_usuario_auth(email="entrada@example.com", debe_cambiar_password=True)
    token = security.emitir_token(usuario.id, [], aplicacion_auth.state.settings)
    antes = await estado_guardado(aplicacion_auth)
    datos = {"password_actual": password, "password_nueva": secrets.token_hex(16)}
    mensaje = "Revisá los datos enviados: hay un valor no válido."
    if caso in ("73ascii", "37ñ", "tipo"):
        datos[campo] = {"73ascii": "x" * 73, "37ñ": "ñ" * 37, "tipo": {"secreto": password}}[caso]
    elif caso == "ausente":
        datos.pop(campo)
    elif caso == "extra":
        datos["rol"] = password
        mensaje = "Enviá sólo los datos permitidos para esta operación."
    cuerpo = json.dumps(datos)
    if caso == "json":
        cuerpo = cuerpo[:-1]
        mensaje = "No pudimos leer los datos enviados. Revisá el formato y volvé a intentar."

    def no_bcrypt(*args, **kwargs):
        pytest.fail("Una entrada inválida no debe llegar a bcrypt")

    for operacion in ("checkpw", "hashpw", "gensalt"):
        monkeypatch.setattr(security.bcrypt, operacion, no_bcrypt)
    respuesta = await api_auth.post(RUTA, content=cuerpo, headers={
        "Cookie": f"access_token={token}", "Content-Type": "application/json",
    })
    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": [{"msg": mensaje}]}
    assert respuesta.headers["content-type"] == "application/json"
    assert "set-cookie" not in respuesta.headers and "retry-after" not in respuesta.headers
    assert await estado_guardado(aplicacion_auth) == antes


@pytest.mark.parametrize("caso", [
    "ausente", "bearer", "malformado", "firma", "expirado", "revocado", "inactivo",
    "inexistente", "sin_sub", "sin_iat", "sin_exp", "sin_roles", "iat_texto",
])
async def test_identidad_y_cambio_rechazan_sesiones_invalidas(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch, caso,
):
    app = aplicacion_auth
    usuario, password = await crear_usuario_auth(email="sesion@example.com", activo=caso != "inactivo")
    ahora = datetime.now(UTC)
    if caso == "revocado":
        async with app.state.fabrica_sesiones() as sesion, UnitOfWork(sesion):
            guardado = await sesion.get(Usuario, usuario.id)
            guardado.password_cambiada_en = ahora
    claims = {"sub": str(usuario.id), "iat": ahora.timestamp() - 1,
              "exp": ahora.timestamp() + 60, "roles": ["ADMIN"]}
    if caso.startswith("sin_"):
        claims.pop(caso.removeprefix("sin_"))
    elif caso == "expirado":
        claims["exp"] = ahora.timestamp() - 1
    elif caso == "inexistente":
        claims["sub"] = "2147483647"
    elif caso == "iat_texto":
        claims["iat"] = str(ahora.timestamp())
    clave = secrets.token_hex(32) if caso == "firma" else app.state.settings.jwt_secret.get_secret_value()
    token = jwt.encode(claims, clave, algorithm=app.state.settings.jwt_algorithm)
    if caso == "malformado":
        token = secrets.token_hex(16)
    encabezados = {} if caso == "ausente" else {"Cookie": f"access_token={token}"}
    if caso == "bearer":
        encabezados = {"Authorization": f"Bearer {token}"}
    antes = await estado_guardado(app)

    async def no_bcrypt(*args):
        pytest.fail("Una sesión rechazada no debe ejecutar bcrypt")

    monkeypatch.setattr(security, "verificar_password", no_bcrypt)
    monkeypatch.setattr(security, "hashear_password", no_bcrypt)
    for metodo, ruta, datos in (("GET", "/auth/yo", None), ("POST", RUTA, {
        "password_actual": password, "password_nueva": secrets.token_hex(16),
    })):
        respuesta = await api_auth.request(metodo, ruta, headers=encabezados, json=datos)
        assert respuesta.status_code == 401
        assert respuesta.json() == {"detail": "La sesión no es válida. Volvé a iniciar sesión."}
        assert respuesta.headers["content-type"] == "application/json"
        assert "set-cookie" not in respuesta.headers and "retry-after" not in respuesta.headers
        assert await estado_guardado(app) == antes


@pytest.mark.parametrize("limite", ["flush", "commit"])
async def test_fallo_revierte_hash_fecha_bandera_evento_sin_cookie(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch, limite,
):
    app = aplicacion_auth
    usuario, password = await crear_usuario_auth(email="rollback@example.com", debe_cambiar_password=True)
    token = security.emitir_token(usuario.id, [], app.state.settings)
    antes = await estado_guardado(app)
    cookie_emitida = False
    emitir_real = router.poner_cookie_sesion

    def emitir(*args, **kwargs):
        nonlocal cookie_emitida
        cookie_emitida = True
        return emitir_real(*args, **kwargs)

    monkeypatch.setattr(router, "poner_cookie_sesion", emitir)
    async with app.state.fabrica_sesiones() as sesion:
        real = getattr(sesion, limite)
        fallo_observado = False

        async def fallar(*args, **kwargs):
            nonlocal fallo_observado
            # Las lecturas confirman normalmente; fallar sólo después del UPDATE real.
            if limite == "flush":
                await real(*args, **kwargs)
            if sesion.in_transaction():
                actual = await sesion.get(Usuario, usuario.id)
                if actual is not None and not actual.debe_cambiar_password:
                    fallo_observado = True
                    assert actual.password_hash != antes[0][0]["password_hash"]
                    assert actual.password_cambiada_en is not None
                    if limite == "commit":
                        eventos = (await sesion.scalars(select(EventoSeguridad))).all()
                        assert [(e.actor, e.accion) for e in eventos] == [
                            (usuario.email, "Cambio de contraseña"),
                        ]
                    assert await estado_guardado(app) == antes  # Otra conexión no ve los flush.
                    raise RuntimeError("detalle privado de persistencia")
            if limite == "commit":
                await real(*args, **kwargs)

        monkeypatch.setattr(sesion, limite, fallar)
        app.dependency_overrides[router.construir_uow] = lambda: UnitOfWorkUsuario(sesion)
        try:
            respuesta = await api_auth.post(RUTA, headers={"Cookie": f"access_token={token}"}, json={
                "password_actual": password, "password_nueva": secrets.token_hex(16),
            })
            assert fallo_observado and respuesta.status_code == 500
            assert respuesta.text == "Internal Server Error"
            assert respuesta.headers["content-type"] == "text/plain; charset=utf-8"
            assert "set-cookie" not in respuesta.headers and not sesion.in_transaction()
            assert not cookie_emitida
            assert await estado_guardado(app) == antes
        finally:
            app.dependency_overrides.pop(router.construir_uow)


async def test_bcrypt_real_fuera_del_bucle_sin_conexion_y_salud_disponible(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch,
):
    app = aplicacion_auth
    usuario, password = await crear_usuario_auth(email="asincronia@example.com")
    token = security.emitir_token(usuario.id, [], app.state.settings)
    hilo_bucle = threading.get_ident()
    bucle = asyncio.get_running_loop()
    observadas = []

    def observar(nombre, real):
        def ejecutar(*args, **kwargs):
            assert threading.get_ident() != hilo_bucle
            assert app.state.motor.pool.checkedout() == 0
            # El hilo espera una sonda real: bloquear el bucle impediría contestarla.
            salud = asyncio.run_coroutine_threadsafe(api_auth.get("/health/live"), bucle).result(2)
            assert salud.status_code == 200 and salud.json() == {"estado": "vivo"}
            observadas.append(nombre)
            return real(*args, **kwargs)
        return ejecutar

    for nombre in ("checkpw", "gensalt", "hashpw"):
        monkeypatch.setattr(security.bcrypt, nombre, observar(nombre, getattr(security.bcrypt, nombre)))
    respuesta = await api_auth.post(RUTA, headers={"Cookie": f"access_token={token}"}, json={
        "password_actual": password, "password_nueva": secrets.token_hex(16),
    })
    assert respuesta.status_code == 200
    assert observadas == ["checkpw", "gensalt", "hashpw"]


async def test_openapi_cambio(api_auth):
    documento = (await api_auth.get("/openapi.json")).json()
    operacion = documento["paths"][RUTA]["post"]
    assert set(operacion["responses"]) == {"200", "401", "422"}
    assert "security" not in operacion  # No esquema Bearer.
    assert operacion["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CambioPasswordEntrada",
    }
    for codigo, esquema in (("200", "SesionLectura"), ("401", "RespuestaAutenticacion"),
                             ("422", "RespuestaValidacion")):
        assert operacion["responses"][codigo]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{esquema}",
        }
