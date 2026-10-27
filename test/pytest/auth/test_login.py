"""Login HTTP con bcrypt y PostgreSQL/Alembic reales; auditoría desde otra sesión."""

import json
import secrets
import threading
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from time import perf_counter

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlmodel import select

from app.core import security
from app.core.unit_of_work import UnitOfWork
from app.modules.usuarios import router, service
from app.modules.usuarios.models import AsignacionRol
from app.modules.usuarios.unit_of_work import UnitOfWorkIntentoAcceso, UnitOfWorkUsuario

from .test_registro import api_auth as api_auth
from .test_registro import estado_guardado


@pytest.mark.parametrize("pendiente,segura", [(False, False), (True, True)])
async def test_login_confirma_intento_roles_y_cookie_sin_conexion_durante_bcrypt(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch, pendiente, segura,
):
    app = aplicacion_auth
    usuario, password = await crear_usuario_auth(
        email="login@example.com", roles=("CLIENTE", "MECANICO", "ADMIN"),
        debe_cambiar_password=pendiente,
    )
    async with app.state.fabrica_sesiones() as sesion, UnitOfWork(sesion):
        roles = (await sesion.scalars(select(AsignacionRol))).all()
        for rol in roles:
            if rol.rol == "ADMIN":
                rol.revocada_en = datetime.now(UTC)
            elif rol.rol == "MECANICO":
                rol.vence_en = datetime.now(UTC) - timedelta(seconds=1)
    app.state.settings.cookie_secure = segura
    app.state.settings.access_token_expire_seconds = 97
    antes = await estado_guardado(app)
    real = security.verificar_password
    verificaciones = []

    async def verificar(texto, hash_guardado):
        assert app.state.motor.pool.checkedout() == 0
        verificaciones.append(hash_guardado)
        return await real(texto, hash_guardado)

    monkeypatch.setattr(security, "verificar_password", verificar)
    inicio = datetime.now(UTC)
    respuesta = await api_auth.post("/auth/login", json={"email": usuario.email, "password": password})
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "mensaje": "Sesión iniciada", "debe_cambiar_password": pendiente,
        "expira_en_segundos": 97,
    }
    assert verificaciones == [usuario.password_hash]
    assert len(respuesta.headers.get_list("set-cookie")) == 1
    cookie = SimpleCookie(respuesta.headers["set-cookie"])["access_token"]
    assert cookie["httponly"] and cookie["samesite"].lower() == "lax"
    assert cookie["path"] == "/" and cookie["domain"] == "" and cookie["max-age"] == "97"
    assert bool(cookie["secure"]) is segura
    claims = security.verificar_token(cookie.value, app.state.settings)
    assert claims["sub"] == str(usuario.id) and claims["roles"] == ["CLIENTE"]
    assert isinstance(claims["iat"], float) and claims["exp"] - claims["iat"] == 97
    despues = await estado_guardado(app)
    assert despues[:4] == antes[:4]  # Sin evento duplicado ni otras escrituras.
    assert len(despues[4]) == 1
    intento = despues[4][0]
    assert (intento["email"], intento["ip"], intento["exito"]) == (usuario.email, "127.0.0.1", True)
    assert inicio <= intento["cuando"] <= datetime.now(UTC)


async def test_inexistente_e_incorrecta_mismo_401_trabajo_y_auditoria(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch,
):
    app = aplicacion_auth
    usuario, _ = await crear_usuario_auth(email="conocido@example.com")
    antes = await estado_guardado(app)
    real = security.bcrypt.checkpw
    hilo_bucle = threading.get_ident()
    muestras = {usuario.password_hash: [], app.state.hash_ficticio: []}

    def medir(texto, hash_guardado):
        assert threading.get_ident() != hilo_bucle
        assert app.state.motor.pool.checkedout() == 0
        inicio = perf_counter()
        resultado = real(texto, hash_guardado)
        muestras[hash_guardado.decode()].append(perf_counter() - inicio)
        return resultado

    monkeypatch.setattr(security.bcrypt, "checkpw", medir)
    for _ in range(3):
        for correo in (usuario.email, "inexistente@example.com"):
            respuesta = await api_auth.post("/auth/login", json={
                "email": correo, "password": secrets.token_hex(16),
            })
            assert respuesta.status_code == 401
            assert respuesta.json() == {"detail": "El correo o la contraseña no son correctos."}
            assert "set-cookie" not in respuesta.headers and "retry-after" not in respuesta.headers
    assert [len(valores) for valores in muestras.values()] == [3, 3]
    assert {clave.split("$")[2] for clave in muestras} == {"04"}
    print("bcrypt real/ficticio (segundos, tres muestras por camino):", list(muestras.values()))
    despues = await estado_guardado(app)
    assert despues[:4] == antes[:4]
    assert [fila["email"] for fila in despues[4]] == [usuario.email, "inexistente@example.com"] * 3
    assert all(not fila["exito"] and fila["ip"] == "127.0.0.1" for fila in despues[4])


async def test_inactivo_solo_revela_estado_con_password_correcta(
    api_auth, aplicacion_auth, crear_usuario_auth,
):
    usuario, password = await crear_usuario_auth(email="inactivo@example.com", activo=False)
    antes = await estado_guardado(aplicacion_auth)
    for clave, mensaje in (
        (secrets.token_hex(16), "El correo o la contraseña no son correctos."),
        (password, "Tu cuenta está desactivada. Comunicate con el taller para reactivarla."),
    ):
        respuesta = await api_auth.post("/auth/login", json={"email": usuario.email, "password": clave})
        assert respuesta.status_code == 401 and respuesta.json() == {"detail": mensaje}
        assert "set-cookie" not in respuesta.headers
    despues = await estado_guardado(aplicacion_auth)
    assert despues[:4] == antes[:4]
    assert len(despues[4]) == 2 and all(not fila["exito"] for fila in despues[4])


async def test_sexto_bloqueado_sin_buscar_credenciales_ni_bcrypt(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch,
):
    app = aplicacion_auth
    usuario, password = await crear_usuario_auth(email="limite@example.com")
    antes = await estado_guardado(app)
    instante = datetime.now(UTC)

    class Reloj:
        @staticmethod
        def now(zona):
            return instante

    monkeypatch.setattr(service, "datetime", Reloj)
    for _ in range(5):
        respuesta = await api_auth.post("/auth/login", json={
            "email": usuario.email, "password": secrets.token_hex(16),
        })
        assert respuesta.status_code == 401 and "set-cookie" not in respuesta.headers
    instante += timedelta(seconds=0.5)
    consultas = []

    def observar(conn, cursor, sentencia, parametros, contexto, muchos):
        consultas.append(sentencia)

    async def no_verificar(*args):
        pytest.fail("Un bloqueo no debe ejecutar bcrypt")

    monkeypatch.setattr(security, "verificar_password", no_verificar)
    event.listen(app.state.motor.sync_engine, "before_cursor_execute", observar)
    try:
        respuesta = await api_auth.post("/auth/login", json={"email": usuario.email, "password": password})
    finally:
        event.remove(app.state.motor.sync_engine, "before_cursor_execute", observar)
    assert respuesta.status_code == 429
    assert respuesta.json() == {"detail": "Demasiados intentos. Volvé a intentar más tarde."}
    assert respuesta.headers["retry-after"] == "60" and "set-cookie" not in respuesta.headers
    assert not any("FROM usuario" in sql or "FROM asignacion_rol" in sql for sql in consultas)
    despues = await estado_guardado(app)
    assert despues[:3] == antes[:3]
    assert len(despues[4]) == 6 and all(not fila["exito"] for fila in despues[4])
    assert all(fila["email"] == usuario.email and fila["ip"] == "127.0.0.1" for fila in despues[4])
    assert len(despues[3]) == 1
    evento = despues[3][0]
    assert (evento["actor"], evento["accion"], evento["cuando"]) == (
        usuario.email, "Login bloqueado por demasiados intentos", instante,
    )


@pytest.mark.parametrize("caso", ["exito", "401", "429", "evento"])
async def test_persistencia_obligatoria_fallida_no_emite_cookie_y_respeta_independencia(
    api_auth, aplicacion_auth, crear_usuario_auth, monkeypatch, caso,
):
    app = aplicacion_auth
    usuario, password = await crear_usuario_auth(email="fallo@example.com")
    datos = {"email": usuario.email, "password": password}
    if caso != "exito":
        datos["password"] = secrets.token_hex(16)
    if caso in ("429", "evento"):
        for _ in range(5):
            assert (await api_auth.post("/auth/login", json=datos)).status_code == 401
    antes = await estado_guardado(app)
    dependencia = router.construir_uow if caso == "evento" else router.construir_uow_intentos
    clase = UnitOfWorkUsuario if caso == "evento" else UnitOfWorkIntentoAcceso
    async with app.state.fabrica_sesiones() as sesion:
        real = sesion.commit
        confirmaciones = 0

        async def confirmar():
            nonlocal confirmaciones
            confirmaciones += 1
            if confirmaciones == (1 if caso == "evento" else 2):
                raise RuntimeError("detalle privado de persistencia")
            await real()

        monkeypatch.setattr(sesion, "commit", confirmar)
        app.dependency_overrides[dependencia] = lambda: clase(sesion)
        try:
            respuesta = await api_auth.post("/auth/login", json=datos)
            assert confirmaciones == (1 if caso == "evento" else 2)
            assert respuesta.status_code == 500
            assert respuesta.text == "Internal Server Error"  # Nunca el error inyectado.
            assert "set-cookie" not in respuesta.headers
            assert not sesion.in_transaction()
        finally:
            app.dependency_overrides.pop(dependencia)
    despues = await estado_guardado(app)
    assert despues[:4] == antes[:4]  # También revierte el evento ya flusheado.
    if caso == "evento":
        assert despues[4][:-1] == antes[4]
        assert not despues[4][-1]["exito"] and despues[4][-1]["email"] == usuario.email
    else:
        assert despues == antes


@pytest.mark.parametrize("datos", [
    {"email": "rechazo@example.com", "password": "x" * 73},
    {"email": "rechazo@example.com", "password": "ñ" * 37},
    {"email": "rechazo@example.com", "password": {}},
    {"email": "rechazo@example.com"},
    {"email": "rechazo@example.com", "password": "", "rol": "ADMIN"},
])
async def test_entrada_rechazada_no_ejecuta_bcrypt_ni_escribe(
    api_auth, aplicacion_auth, monkeypatch, datos,
):
    async def no_verificar(*args):
        pytest.fail("La validación debe preceder a bcrypt")

    monkeypatch.setattr(security, "verificar_password", no_verificar)
    respuesta = await api_auth.post("/auth/login", json=datos)
    assert respuesta.status_code == 422 and "set-cookie" not in respuesta.headers
    mensaje = ("Enviá sólo los datos permitidos para esta operación." if "rol" in datos
               else "Revisá los datos enviados: hay un valor no válido.")
    assert respuesta.json() == {"detail": [{"msg": mensaje}]}
    assert await estado_guardado(aplicacion_auth) == [[], [], [], [], []]


async def test_openapi_login_documenta_resultados_y_retry_after(api_auth):
    documento = (await api_auth.get("/openapi.json")).json()
    operacion = documento["paths"]["/auth/login"]["post"]
    assert "security" not in operacion
    respuestas = operacion["responses"]
    assert set(respuestas) == {"200", "401", "422", "429"}
    assert respuestas["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SesionLectura",
    }
    assert respuestas["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RespuestaValidacion",
    }
    assert respuestas["429"]["headers"]["Retry-After"]["schema"] == {"type": "integer", "minimum": 1}


@pytest.fixture
def reloj_login(monkeypatch):
    class Reloj:
        instante = datetime.now(UTC)

        @classmethod
        def now(cls, zona):
            return cls.instante

    monkeypatch.setattr(service, "datetime", Reloj)
    return Reloj


async def comprobar_login(cliente, app, datos, codigo, cuando, *, espera=None, ip="127.0.0.1"):
    """Observa cada petición y su delta completo desde otra sesión real."""
    antes = await estado_guardado(app)
    respuesta = await cliente.post("/auth/login", json=datos)
    assert respuesta.status_code == codigo
    assert respuesta.headers["content-type"] == "application/json"
    if codigo == 200:
        assert respuesta.json() == {
            "mensaje": "Sesión iniciada", "debe_cambiar_password": False,
            "expira_en_segundos": app.state.settings.access_token_expire_seconds,
        }
        cookie = SimpleCookie(respuesta.headers["set-cookie"])["access_token"]
        claims = security.verificar_token(cookie.value, app.state.settings)
        usuario = next(fila for fila in antes[0] if fila["email"] == datos["email"])
        assert claims["sub"] == str(usuario["id"]) and claims["roles"] == ["CLIENTE"]
    else:
        mensaje = ("Demasiados intentos. Volvé a intentar más tarde." if codigo == 429
                   else "El correo o la contraseña no son correctos.")
        assert respuesta.json() == {"detail": mensaje}
        assert "set-cookie" not in respuesta.headers
    assert respuesta.headers.get("retry-after") == (str(espera) if espera is not None else None)
    despues = await estado_guardado(app)
    assert despues[:3] == antes[:3]
    assert despues[4][:-1] == antes[4]
    assert despues[4][-1] == {
        "id": despues[4][-1]["id"], "email": datos["email"], "ip": ip,
        "cuando": cuando, "exito": codigo == 200,
    }
    if codigo == 429:
        assert despues[3][:-1] == antes[3]
        assert despues[3][-1] == {
            "id": despues[3][-1]["id"], "cuando": cuando, "actor": datos["email"],
            "accion": "Login bloqueado por demasiados intentos",
        }
    else:
        assert despues[3] == antes[3]
    return despues


@pytest.mark.parametrize("desfase,codigo,espera", [
    (-60, 401, None), (-59.999999, 429, 1), (0, 429, 60), (0.000001, 401, None),
])
async def test_ventana_http_abierta_en_60_cerrada_en_ahora_sin_fallos_futuros(
    api_auth, aplicacion_auth, reloj_login, desfase, codigo, espera,
):
    ahora = reloj_login.instante
    datos = {"email": "ventana@example.com", "password": secrets.token_hex(16)}
    # Los cinco intentos se crean por HTTP, incluso el fechado un microsegundo después.
    reloj_login.instante = ahora + timedelta(seconds=desfase)
    for _ in range(5):
        await comprobar_login(api_auth, aplicacion_auth, datos, 401, reloj_login.instante)
    reloj_login.instante = ahora
    filas = await comprobar_login(api_auth, aplicacion_auth, datos, codigo, ahora, espera=espera)
    assert len(filas[4]) == 6 and all(not fila["exito"] for fila in filas[4])


async def test_429_cuenta_y_retry_after_no_promete_desbloqueo(
    api_auth, aplicacion_auth, reloj_login,
):
    ahora = reloj_login.instante
    datos = {"email": "conteo@example.com", "password": secrets.token_hex(16)}
    for segundos in (-50, -40, -30, -20, -10):
        reloj_login.instante = ahora + timedelta(seconds=segundos)
        await comprobar_login(api_auth, aplicacion_auth, datos, 401, reloj_login.instante)
    for segundos, codigo, espera in ((0, 429, 10), (10, 429, 10), (60, 401, None)):
        reloj_login.instante = ahora + timedelta(seconds=segundos)
        filas = await comprobar_login(
            api_auth, aplicacion_auth, datos, codigo, reloj_login.instante, espera=espera,
        )
    assert len(filas[4]) == 8 and len(filas[3]) == 2


async def test_ultimo_exito_http_reinicia_sin_borrar_y_excluye_fallos_con_fecha_igual(
    api_auth, aplicacion_auth, crear_usuario_auth, reloj_login,
):
    usuario, password = await crear_usuario_auth(email="reset@example.com")
    ahora = reloj_login.instante
    correcta = {"email": usuario.email, "password": password}
    incorrecta = correcta | {"password": secrets.token_hex(16)}
    secuencia = [
        (0, 401), (1, 401), (2, 401), (3, 200), (3, 401), (4, 401),
        (5, 200), (5, 401), (6, 401), (7, 401), (8, 401), (9, 401), (10, 401), (11, 429),
    ]
    for segundos, codigo in secuencia:
        reloj_login.instante = ahora + timedelta(seconds=segundos)
        await comprobar_login(
            api_auth, aplicacion_auth, correcta if codigo == 200 else incorrecta,
            codigo, reloj_login.instante, espera=55 if codigo == 429 else None,
        )
    filas = await estado_guardado(aplicacion_auth)
    assert len(filas[4]) == 14 and sum(fila["exito"] for fila in filas[4]) == 2
    assert len(filas[3]) == 1  # Ningún login no bloqueado duplica auditoría.


async def test_aislamiento_http_correo_exacto_ip_y_exitos_ajenos(
    api_auth, aplicacion_auth, crear_usuario_auth, reloj_login,
):
    app = aplicacion_auth
    usuario, password = await crear_usuario_auth(email="par@example.com")
    otro, otra_password = await crear_usuario_auth(email="otro@example.com")
    datos = {"email": usuario.email, "password": secrets.token_hex(16)}
    for _ in range(5):
        await comprobar_login(api_auth, app, datos, 401, reloj_login.instante)
    await comprobar_login(api_auth, app, datos | {"email": usuario.email.upper()}, 401, reloj_login.instante)
    await comprobar_login(api_auth, app, {"email": otro.email, "password": otra_password}, 200, reloj_login.instante)
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("192.0.2.2", 1234)), base_url="http://test",
    ) as otra_ip:
        await comprobar_login(
            otra_ip, app, datos | {"password": password}, 200, reloj_login.instante, ip="192.0.2.2",
        )
    filas = await comprobar_login(api_auth, app, datos, 429, reloj_login.instante, espera=60)
    assert len(filas[4]) == 9 and sum(fila["exito"] for fila in filas[4]) == 2


@pytest.mark.parametrize("multibyte", [False, True])
async def test_login_acepta_password_de_72_bytes(
    api_auth, aplicacion_auth, reloj_login, multibyte,
):
    password = "ñ" * 36 if multibyte else secrets.token_hex(36)
    datos = {"email": "limite-bytes@example.com", "password": password}
    registro = await api_auth.post("/auth/registro", json=datos | {
        "nombre": "Prueba", "documento": "BYTES-72", "telefono": "12345",
    })
    assert registro.status_code == 201
    filas = await comprobar_login(api_auth, aplicacion_auth, datos, 200, reloj_login.instante)
    assert len(filas[4]) == 1


@pytest.mark.parametrize("caso", ["json_malformado", "sin_email"])
async def test_login_rechaza_json_malformado_o_correo_ausente_sin_efectos(
    api_auth, aplicacion_auth, monkeypatch, caso,
):
    async def no_verificar(*args):
        pytest.fail("Una entrada inválida no debe ejecutar bcrypt")

    monkeypatch.setattr(security, "verificar_password", no_verificar)
    cuerpo = json.dumps({"password": secrets.token_hex(16)})
    mensaje = "Revisá los datos enviados: hay un valor no válido."
    if caso == "json_malformado":
        cuerpo = cuerpo[:-1]
        mensaje = "No pudimos leer los datos enviados. Revisá el formato y volvé a intentar."
    respuesta = await api_auth.post("/auth/login", content=cuerpo, headers={"Content-Type": "application/json"})
    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": [{"msg": mensaje}]}
    assert "set-cookie" not in respuesta.headers and "retry-after" not in respuesta.headers
    assert await estado_guardado(aplicacion_auth) == [[], [], [], [], []]
