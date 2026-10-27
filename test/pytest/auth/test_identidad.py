"""Identidad HTTP por cookie; estado real PostgreSQL/Alembic, sin permisos EJ-5."""

import secrets
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlmodel import select

from app.core import security
from app.core.unit_of_work import UnitOfWork
from app.modules.usuarios.models import AsignacionRol, Usuario

from .test_registro import api_auth as api_auth
from .test_registro import estado_guardado


async def test_yo_proyecta_identidad_sin_secretos(
    api_auth, aplicacion_auth, crear_usuario_auth,
):
    usuario, password = await crear_usuario_auth(
        email="identidad@example.com", debe_cambiar_password=True,
    )
    login = await api_auth.post("/auth/login", json={"email": usuario.email, "password": password})
    assert login.status_code == 200
    antes = await estado_guardado(aplicacion_auth)
    respuesta = await api_auth.get("/auth/yo")
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "usuario": {"id": usuario.id, "email": usuario.email,
                    "nombre": "Usuario de prueba", "debe_cambiar_password": True},
        "roles_vigentes": ["CLIENTE"], "roles_token": ["CLIENTE"],
    }
    assert respuesta.headers["content-type"] == "application/json"
    assert "set-cookie" not in respuesta.headers and "retry-after" not in respuesta.headers
    assert await estado_guardado(aplicacion_auth) == antes


@pytest.mark.parametrize("caso", [
    "ausente", "bearer", "malformado", "firma", "expirado", "inexistente", "inactivo",
    "sin_sub", "sin_iat", "sin_exp", "sin_roles", "sub_numero", "sub_texto",
    "iat_texto", "iat_booleano", "iat_futuro", "exp_texto", "exp_booleano",
    "roles_texto", "roles_numero", "id_fuera_rango",
])
async def test_yo_rechaza_sesion_invalida_sin_eco_ni_escrituras(
    api_auth, aplicacion_auth, crear_usuario_auth, caso,
):
    usuario, _ = await crear_usuario_auth(email="rechazo@example.com", activo=caso != "inactivo")
    settings = aplicacion_auth.state.settings
    ahora = datetime.now(UTC).timestamp()
    claims = {"sub": str(usuario.id), "iat": ahora - 1, "exp": ahora + 60, "roles": ["CLIENTE"]}
    cambios = {
        "expirado": ("exp", ahora - 1), "inexistente": ("sub", "2147483647"),
        "sub_numero": ("sub", usuario.id), "sub_texto": ("sub", "no-es-id"),
        "iat_texto": ("iat", str(ahora)), "iat_booleano": ("iat", True),
        "iat_futuro": ("iat", ahora + 60), "exp_texto": ("exp", str(ahora + 60)),
        "exp_booleano": ("exp", True), "roles_texto": ("roles", "ADMIN"),
        "roles_numero": ("roles", [1]), "id_fuera_rango": ("sub", str(2**63)),
    }
    if caso.startswith("sin_"):
        claims.pop(caso.removeprefix("sin_"))
    elif caso in cambios:
        campo, valor = cambios[caso]
        claims[campo] = valor
    clave = secrets.token_hex(32) if caso == "firma" else settings.jwt_secret.get_secret_value()
    token = jwt.encode(claims, clave, algorithm=settings.jwt_algorithm)
    if caso == "malformado":
        token = secrets.token_hex(16)
    encabezados = {"Cookie": f"access_token={token}"}
    if caso == "ausente":
        encabezados = {}
    elif caso == "bearer":
        encabezados = {"Authorization": f"Bearer {token}"}
    antes = await estado_guardado(aplicacion_auth)
    respuesta = await api_auth.get("/auth/yo", headers=encabezados)
    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "La sesión no es válida. Volvé a iniciar sesión."}
    assert respuesta.headers["content-type"] == "application/json"
    assert "set-cookie" not in respuesta.headers and "retry-after" not in respuesta.headers
    assert await estado_guardado(aplicacion_auth) == antes


async def test_yo_compara_fracciones_originales_y_usuario_actual(
    api_auth, aplicacion_auth, crear_usuario_auth,
):
    usuario, _ = await crear_usuario_auth(email="fracciones@example.com")
    cambio = (datetime.now(UTC) - timedelta(seconds=10)).replace(microsecond=500000)
    async with aplicacion_auth.state.fabrica_sesiones() as sesion, UnitOfWork(sesion):
        actual = await sesion.get(Usuario, usuario.id)
        actual.password_cambiada_en = cambio
    antes = await estado_guardado(aplicacion_auth)
    for diferencia, codigo in ((-1, 401), (0, 200), (1, 200)):
        token = security.emitir_token(usuario.id, [], aplicacion_auth.state.settings,
                                     emitido_en=cambio + timedelta(microseconds=diferencia))
        respuesta = await api_auth.get("/auth/yo", headers={"Cookie": f"access_token={token}"})
        assert respuesta.status_code == codigo
        esperado = {"detail": "La sesión no es válida. Volvé a iniciar sesión."} if codigo == 401 else {
            "usuario": {"id": usuario.id, "email": usuario.email,
                        "nombre": "Usuario de prueba", "debe_cambiar_password": False},
            "roles_vigentes": ["CLIENTE"], "roles_token": [],
        }
        assert respuesta.json() == esperado and "set-cookie" not in respuesta.headers
        assert await estado_guardado(aplicacion_auth) == antes
    # La misma cookie válida deja de valer al desactivar al usuario, sin reemitirla.
    async with aplicacion_auth.state.fabrica_sesiones() as sesion, UnitOfWork(sesion):
        actual = await sesion.get(Usuario, usuario.id)
        actual.activo = False
    antes = await estado_guardado(aplicacion_auth)
    respuesta = await api_auth.get("/auth/yo", headers={"Cookie": f"access_token={token}"})
    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": "La sesión no es válida. Volvé a iniciar sesión."}
    assert "set-cookie" not in respuesta.headers
    assert await estado_guardado(aplicacion_auth) == antes


async def test_yo_refleja_roles_revocados_vencidos_y_sin_roles(
    api_auth, aplicacion_auth, crear_usuario_auth,
):
    usuario, password = await crear_usuario_auth(
        email="roles@example.com", roles=("CLIENTE", "ADMIN", "MECANICO"),
    )
    login = await api_auth.post("/auth/login", json={"email": usuario.email, "password": password})
    assert login.status_code == 200
    for quitar_todos in (False, True):
        async with aplicacion_auth.state.fabrica_sesiones() as sesion, UnitOfWork(sesion):
            for rol in (await sesion.scalars(select(AsignacionRol))).all():
                if rol.rol == "ADMIN" or quitar_todos:
                    rol.revocada_en = datetime.now(UTC)
                elif rol.rol == "MECANICO":
                    rol.vence_en = datetime.now(UTC) - timedelta(seconds=1)
                else:
                    rol.vence_en = datetime.now(UTC) + timedelta(hours=1)
        antes = await estado_guardado(aplicacion_auth)
        respuesta = await api_auth.get("/auth/yo", headers={"Authorization": "Bearer ignorado"})
        assert respuesta.status_code == 200
        datos = respuesta.json()
        assert datos["usuario"] == {"id": usuario.id, "email": usuario.email,
                                    "nombre": "Usuario de prueba", "debe_cambiar_password": False}
        assert datos["roles_vigentes"] == ([] if quitar_todos else ["CLIENTE"])
        assert set(datos["roles_token"]) == {"CLIENTE", "ADMIN", "MECANICO"}
        assert set(datos) == {"usuario", "roles_vigentes", "roles_token"}
        assert "set-cookie" not in respuesta.headers
        assert await estado_guardado(aplicacion_auth) == antes


async def test_cookie_registro_habilita_yo_y_c01_conserva_422(api_auth, aplicacion_auth):
    registro = await api_auth.post("/auth/registro", json={
        "email": "registro-yo@example.com", "password": secrets.token_hex(16),
        "nombre": "Cliente HTTP", "documento": "IDENTIDAD-1", "telefono": "12345",
    })
    assert registro.status_code == 201
    antes = await estado_guardado(aplicacion_auth)
    respuesta = await api_auth.get("/auth/yo")
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "usuario": {"id": antes[0][0]["id"], "email": "registro-yo@example.com",
                    "nombre": "Cliente HTTP", "debe_cambiar_password": False},
        "roles_vigentes": ["CLIENTE"], "roles_token": ["CLIENTE"],
    }
    invalida = await api_auth.get("/clientes/no-entero")
    assert invalida.status_code == 422
    assert invalida.json() == {"detail": [{"msg": "Ingresá un número entero para el cliente seleccionado."}]}
    assert "set-cookie" not in respuesta.headers and "set-cookie" not in invalida.headers
    assert await estado_guardado(aplicacion_auth) == antes


async def test_openapi_yo_y_logout(api_auth):
    documento = (await api_auth.get("/openapi.json")).json()
    for ruta, metodo, esquema, codigos in (
        ("/auth/yo", "get", "IdentidadLectura", {"200", "401", "422"}),
        ("/auth/logout", "post", "MensajeLectura", {"200", "422"}),
    ):
        operacion = documento["paths"][ruta][metodo]
        assert set(operacion["responses"]) == codigos
        assert "requestBody" not in operacion
        assert operacion["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{esquema}",
        }
    assert documento["paths"]["/auth/yo"]["get"]["responses"]["401"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RespuestaAutenticacion",
    }
