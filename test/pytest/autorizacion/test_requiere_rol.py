"""T-2.1/T-2.2: 401 de identidad y orden 401→403 de `requiere_rol` sobre rutas de prueba.

Las rutas de prueba viven en una app propia con el mismo estado (settings y fábrica
de sesiones) que la aplicación real: no se toca ninguna ruta existente.
"""

from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.dependencies import get_usuario_actual, requiere_rol
from app.core.errores import registrar_traductores
from app.core.security import emitir_token

MENSAJE_SESION = "La sesión no es válida. Volvé a iniciar sesión."


def _app_de_prueba(api_autorizacion) -> FastAPI:
    app = FastAPI()
    app.state.settings = api_autorizacion.app.state.settings
    app.state.fabrica_sesiones = api_autorizacion.app.state.fabrica_sesiones
    registrar_traductores(app)

    @app.get("/solo-identidad")
    async def solo_identidad(identidad=Depends(get_usuario_actual)):
        return {"id": identidad.usuario.id}

    solo_admin = requiere_rol("ADMIN")
    solo_recepcion = requiere_rol("RECEPCION")
    recepcion_o_admin = requiere_rol("ADMIN", "RECEPCION")

    @app.get("/solo-admin")
    async def ruta_solo_admin(identidad=Depends(solo_admin)):
        return {"id": identidad.usuario.id, "roles": identidad.roles_vigentes}

    @app.get("/solo-recepcion")
    async def ruta_solo_recepcion(identidad=Depends(solo_recepcion)):
        return {"id": identidad.usuario.id}

    @app.get("/recepcion-o-admin")
    async def ruta_recepcion_o_admin(identidad=Depends(recepcion_o_admin)):
        return {"id": identidad.usuario.id}

    return app


def _cliente_de_prueba(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://prueba")


async def _token_de(api_autorizacion, email: str) -> str:
    from autorizacion.conftest import PASSWORD_DE_PRUEBA
    async with AsyncClient(
        transport=ASGITransport(app=api_autorizacion.app), base_url="http://prueba",
    ) as cliente:
        respuesta = await cliente.post(
            "/auth/login", json={"email": email, "password": PASSWORD_DE_PRUEBA},
        )
        assert respuesta.status_code == 200, respuesta.text
        token = respuesta.cookies.get("access_token")
    assert token is not None
    return token


async def _consultar_id(api_autorizacion, email: str) -> int:
    async with api_autorizacion.motor.begin() as conn:
        resultado = await conn.execute(
            text("SELECT id FROM usuario WHERE email = :email"), {"email": email}
        )
        fila = resultado.one()
    return int(fila[0])


# --- T-2.1: los 401 de la identidad, sin tocar rutas existentes ---


async def test_sin_cookie_da_401(api_autorizacion):
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        respuesta = await cliente.get("/solo-identidad")
    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_SESION}


async def test_solo_bearer_sin_cookie_da_401(api_autorizacion):
    token = await _token_de(api_autorizacion, "admin@example.com")
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        respuesta = await cliente.get(
            "/solo-identidad", headers={"Authorization": f"Bearer {token}"},
        )
    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_SESION}


async def test_cookie_alterada_da_401(api_autorizacion):
    token = await _token_de(api_autorizacion, "admin@example.com")
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", token + "x")
        respuesta = await cliente.get("/solo-identidad")
    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_SESION}


async def test_token_vencido_da_401(api_autorizacion):
    settings = api_autorizacion.app.state.settings
    vencido = emitir_token(
        1, ["ADMIN"], settings,
        emitido_en=datetime.now(UTC) - timedelta(seconds=settings.access_token_expire_seconds + 60),
    )
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", vencido)
        respuesta = await cliente.get("/solo-identidad")
    assert respuesta.status_code == 401


async def test_usuario_inexistente_da_401(api_autorizacion):
    settings = api_autorizacion.app.state.settings
    fantasma = emitir_token(999999, ["ADMIN"], settings)
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", fantasma)
        respuesta = await cliente.get("/solo-identidad")
    assert respuesta.status_code == 401


async def test_usuario_inactivo_da_401(api_autorizacion, crear_usuario_autorizacion):
    usuario, _ = await crear_usuario_autorizacion(email="luego-inactivo@example.com", activo=False)
    settings = api_autorizacion.app.state.settings
    token = emitir_token(usuario.id, [], settings)
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", token)
        respuesta = await cliente.get("/solo-identidad")
    assert respuesta.status_code == 401


async def test_iat_anterior_al_cambio_por_una_fraccion_da_401(
    api_autorizacion, crear_usuario_autorizacion,
):
    usuario, _ = await crear_usuario_autorizacion(email="cambio-fraccion@example.com")
    settings = api_autorizacion.app.state.settings
    emitido_en = datetime.now(UTC) - timedelta(seconds=5)
    token = emitir_token(usuario.id, [], settings, emitido_en=emitido_en)
    cambio = emitido_en + timedelta(seconds=0.5)
    async with api_autorizacion.motor.begin() as conn:
        await conn.execute(
            text("UPDATE usuario SET password_cambiada_en = :c WHERE id = :id"),
            {"c": cambio, "id": usuario.id},
        )
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", token)
        respuesta = await cliente.get("/solo-identidad")
    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_SESION}


async def test_iat_posterior_al_cambio_del_mismo_segundo_sigue_valido(
    api_autorizacion, crear_usuario_autorizacion,
):
    usuario, _ = await crear_usuario_autorizacion(email="cambio-mismo-segundo@example.com")
    settings = api_autorizacion.app.state.settings
    emitido_en = datetime.now(UTC) - timedelta(seconds=5)
    token = emitir_token(usuario.id, [], settings, emitido_en=emitido_en)
    cambio = emitido_en - timedelta(seconds=0.5)
    async with api_autorizacion.motor.begin() as conn:
        await conn.execute(
            text("UPDATE usuario SET password_cambiada_en = :c WHERE id = :id"),
            {"c": cambio, "id": usuario.id},
        )
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", token)
        respuesta = await cliente.get("/solo-identidad")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"id": usuario.id}


# --- T-2.2: `requiere_rol` consulta la base y el 401 precede al 403 ---


async def test_ruta_con_rol_da_200_y_devuelve_la_identidad(api_autorizacion):
    token = await _token_de(api_autorizacion, "admin@example.com")
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", token)
        respuesta = await cliente.get("/solo-admin")
    assert respuesta.status_code == 200
    assert respuesta.json()["roles"] == ["ADMIN"]


async def test_sin_sesion_en_ruta_con_rol_da_401_y_no_403(api_autorizacion):
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        respuesta = await cliente.get("/solo-admin")
    assert respuesta.status_code == 401
    assert respuesta.json() == {"detail": MENSAJE_SESION}


async def test_sesion_sin_el_rol_da_403_con_mensaje_humano(api_autorizacion):
    token = await _token_de(api_autorizacion, "cliente@example.com")
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", token)
        respuesta = await cliente.get("/solo-admin")
    assert respuesta.status_code == 403
    assert respuesta.json() == {"detail": "No tenés permiso para realizar esta acción."}


async def test_revocacion_surte_efecto_en_la_siguiente_peticion(api_autorizacion):
    token = await _token_de(api_autorizacion, "recepcion@example.com")
    async with api_autorizacion.motor.begin() as conn:
        await conn.execute(
            text(
                "UPDATE asignacion_rol SET revocada_en = now() "
                "WHERE rol = 'RECEPCION' AND revocada_en IS NULL"
            )
        )
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", token)
        respuesta = await cliente.get("/solo-recepcion")
    assert respuesta.status_code == 403


async def test_rol_vencido_da_403_con_token_aun_valido(api_autorizacion):
    token = await _token_de(api_autorizacion, "recepcion@example.com")
    async with api_autorizacion.motor.begin() as conn:
        await conn.execute(
            text(
                "UPDATE asignacion_rol SET vence_en = now() - interval '1 hour' "
                "WHERE rol = 'RECEPCION' AND revocada_en IS NULL"
            )
        )
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", token)
        respuesta = await cliente.get("/solo-recepcion")
    assert respuesta.status_code == 403


async def test_roles_del_token_no_deciden(api_autorizacion, crear_usuario_autorizacion):
    settings = api_autorizacion.app.state.settings
    usuario, _ = await crear_usuario_autorizacion(
        email="token-miente@example.com", roles=("CLIENTE",),
    )
    mintiendo = emitir_token(usuario.id, ["ADMIN"], settings)
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", mintiendo)
        denegado = await cliente.get("/solo-admin")
    assert denegado.status_code == 403

    id_admin = await _consultar_id(api_autorizacion, "admin@example.com")
    sin_roles = emitir_token(id_admin, [], settings)
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", sin_roles)
        permitido = await cliente.get("/solo-admin")
    assert permitido.status_code == 200


async def test_requiere_rol_acepta_varios_roles(api_autorizacion):
    token = await _token_de(api_autorizacion, "recepcion@example.com")
    async with _cliente_de_prueba(_app_de_prueba(api_autorizacion)) as cliente:
        cliente.cookies.set("access_token", token)
        respuesta = await cliente.get("/recepcion-o-admin")
    assert respuesta.status_code == 200
