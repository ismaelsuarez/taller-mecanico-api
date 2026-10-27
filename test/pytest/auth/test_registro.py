"""C-02: HTTP público, PostgreSQL/Alembic y lectura independiente del resultado."""

import json
import secrets
from datetime import UTC, datetime
from http.cookies import SimpleCookie

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlmodel import col, select

from app.core import security
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    Usuario,
)


@pytest.fixture
async def api_auth(aplicacion_auth):
    async with AsyncClient(
        transport=ASGITransport(app=aplicacion_auth, raise_app_exceptions=False),
        base_url="http://test",
    ) as cliente:
        yield cliente


@pytest.fixture
def datos_registro():
    return {
        "email": "registro@example.com", "password": secrets.token_hex(36),
        "nombre": "Cliente de prueba", "documento": "REG-1", "telefono": "12345",
    }


async def estado_guardado(app):
    """Incluye todos los campos: detecta altas parciales y cambios a fichas ajenas."""
    async with app.state.fabrica_sesiones() as sesion:
        return [
            [fila.model_dump() for fila in (await sesion.scalars(select(modelo).order_by(col(modelo.id)))).all()]
            for modelo in (Usuario, AsignacionRol, Cliente, EventoSeguridad, IntentoAcceso)
        ]


@pytest.mark.parametrize("segura,multibyte", [(False, False), (True, True)])
async def test_registro_confirma_todo_antes_de_emitir_cookie(
    api_auth, aplicacion_auth, datos_registro, monkeypatch, segura, multibyte,
):
    app = aplicacion_auth
    settings = app.state.settings
    settings.cookie_secure = segura
    settings.access_token_expire_seconds = 97
    settings.bcrypt_rounds = 5
    if multibyte:
        datos_registro["password"] = "ñ" * 36
    hasheado = False
    consultas = []
    real = security.hashear_password

    async def observar_hash(texto, rondas):
        nonlocal hasheado
        assert consultas == []  # Ni siquiera una lectura/autobegin antes de bcrypt.
        assert rondas == 5
        resultado = await real(texto, rondas)
        hasheado = True
        return resultado

    def observar_sql(conn, cursor, sentencia, parametros, contexto, muchos):
        assert hasheado
        consultas.append(sentencia)

    def observar_inicio(conn):
        assert hasheado  # Incluye BEGIN sin sentencias previas.

    monkeypatch.setattr(security, "hashear_password", observar_hash)
    motor = app.state.motor.sync_engine
    event.listen(motor, "begin", observar_inicio)
    event.listen(motor, "before_cursor_execute", observar_sql)
    inicio = datetime.now(UTC)
    try:
        respuesta = await api_auth.post("/auth/registro", json=datos_registro)
    finally:
        event.remove(motor, "before_cursor_execute", observar_sql)
        event.remove(motor, "begin", observar_inicio)
    assert respuesta.status_code == 201
    assert respuesta.json() == {
        "mensaje": "Registro completado", "debe_cambiar_password": False,
        "expira_en_segundos": 97,
    }
    assert hasheado and not any(sql.lstrip().upper().startswith("SELECT") for sql in consultas)
    assert respuesta.headers["content-type"] == "application/json"
    assert len(respuesta.headers.get_list("set-cookie")) == 1
    cookie = SimpleCookie(respuesta.headers["set-cookie"])["access_token"]
    assert cookie["httponly"] and cookie["samesite"].lower() == "lax"
    assert cookie["max-age"] == "97" and cookie["path"] == "/" and cookie["domain"] == ""
    assert bool(cookie["secure"]) is segura
    claims = security.verificar_token(cookie.value, settings)
    usuarios, roles, clientes, eventos, intentos = await estado_guardado(app)
    assert tuple(map(len, (usuarios, roles, clientes, eventos, intentos))) == (1, 1, 1, 1, 0)
    usuario, rol, cliente, evento = usuarios[0], roles[0], clientes[0], eventos[0]
    assert usuario["email"] == datos_registro["email"]
    assert usuario["nombre"] == cliente["nombre"] == datos_registro["nombre"]
    assert usuario["activo"] and not usuario["debe_cambiar_password"]
    assert usuario["password_cambiada_en"] is None
    assert usuario["password_hash"].split("$")[2] == "05"
    assert await security.verificar_password(datos_registro["password"], usuario["password_hash"])
    assert rol["usuario_id"] == cliente["usuario_id"] == usuario["id"]
    assert rol["rol"] == "CLIENTE" and inicio <= rol["desde"] <= datetime.now(UTC)
    assert rol["vence_en"] is rol["revocada_en"] is rol["otorgada_por"] is None
    assert cliente["documento"] == datos_registro["documento"]
    assert cliente["telefono"] == datos_registro["telefono"]
    assert evento["actor"] == datos_registro["email"]
    assert evento["accion"] == "Alta de usuario cliente (registro)"
    assert inicio <= evento["cuando"] <= datetime.now(UTC)
    assert claims["sub"] == str(usuario["id"]) and claims["roles"] == ["CLIENTE"]
    assert isinstance(claims["iat"], float) and claims["iat"] >= evento["cuando"].timestamp()
    assert claims["exp"] - claims["iat"] == 97


@pytest.mark.parametrize("colision", ["email", "documento", "sin_usuario"])
async def test_conflictos_no_se_apropian_de_fichas_ni_dejan_filas(
    api_auth, aplicacion_auth, datos_registro, colision,
):
    if colision == "sin_usuario":
        ficha = {k: datos_registro[k] for k in ("nombre", "documento", "telefono")}
        assert (await api_auth.post("/clientes", json=ficha)).status_code == 201
    else:
        assert (await api_auth.post("/auth/registro", json=datos_registro)).status_code == 201
    antes = await estado_guardado(aplicacion_auth)
    datos_registro["documento" if colision == "email" else "email"] = "otro@example.com"
    api_auth.cookies.clear()
    respuesta = await api_auth.post("/auth/registro", json=datos_registro)
    assert respuesta.status_code == 409
    mensaje = ("Ya existe un usuario con ese correo." if colision == "email"
               else "Ya existe un cliente con ese documento.")
    assert respuesta.json() == {"detail": mensaje}
    assert "set-cookie" not in respuesta.headers
    assert await estado_guardado(aplicacion_auth) == antes


@pytest.mark.parametrize("caso", ["rol", "extra", "73ascii", "37ñ", "ausente", "tipo", "json"])
async def test_422_sin_bcrypt_cookie_eco_ni_escrituras(
    api_auth, aplicacion_auth, datos_registro, monkeypatch, caso,
):
    async def no_hashear(*args):
        pytest.fail("Una entrada rechazada no debe llegar a bcrypt")

    monkeypatch.setattr(security, "hashear_password", no_hashear)
    mensaje = "Revisá los datos enviados: hay un valor no válido."
    if caso in ("rol", "extra"):
        datos_registro[caso] = datos_registro["password"]
        mensaje = "Enviá sólo los datos permitidos para esta operación."
    elif caso == "73ascii":
        datos_registro["password"] += "x"
    elif caso == "37ñ":
        datos_registro["password"] = "ñ" * 37
    elif caso == "ausente":
        datos_registro.pop("password")
    elif caso == "tipo":
        datos_registro["password"] = {"valor": datos_registro["password"]}
    cuerpo = json.dumps(datos_registro)
    if caso == "json":
        cuerpo = cuerpo[:-1]
        mensaje = "No pudimos leer los datos enviados. Revisá el formato y volvé a intentar."
    respuesta = await api_auth.post(
        "/auth/registro", content=cuerpo, headers={"Content-Type": "application/json"},
    )
    assert respuesta.status_code == 422
    assert respuesta.json() == {"detail": [{"msg": mensaje}]}
    assert "set-cookie" not in respuesta.headers
    assert await estado_guardado(aplicacion_auth) == [[], [], [], [], []]


async def test_openapi_publica_registro_y_login(api_auth):
    documento = (await api_auth.get("/openapi.json")).json()
    assert {ruta for ruta in documento["paths"] if ruta.startswith("/auth")} == {
        "/auth/registro", "/auth/login",
    }
    operacion = documento["paths"]["/auth/registro"]["post"]
    assert set(operacion["responses"]) == {"201", "409", "422"}
    assert "security" not in operacion
    for codigo, esquema in (("201", "SesionLectura"), ("422", "RespuestaValidacion")):
        assert operacion["responses"][codigo]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{esquema}",
        }
