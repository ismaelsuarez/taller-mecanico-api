"""T-4: alta de personal (POST /usuarios) — DD-18, Flujo 5."""

import pytest

from autorizacion.conftest import PASSWORD_DE_PRUEBA


async def _id_de(api_autorizacion, email: str) -> int:
    from sqlalchemy import text

    async with api_autorizacion.motor.begin() as conn:
        resultado = await conn.execute(
            text("SELECT id FROM usuario WHERE email = :email"), {"email": email}
        )
        return int(resultado.one()[0])


async def test_alta_valida_crea_usuario_rol_y_evento(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post("/usuarios", json={
            "email": "nuevo-mecanico@example.com",
            "nombre": "Mecánico Nuevo",
            "password_provisoria": "Provisoria123!",
            "rol": "MECANICO",
        })
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["email"] == "nuevo-mecanico@example.com"
    assert cuerpo["debe_cambiar_password"] is True
    assert "password_hash" not in cuerpo
    assert "password_provisoria" not in cuerpo

    id_admin = await _id_de(api_autorizacion, "admin@example.com")
    id_nuevo = await _id_de(api_autorizacion, "nuevo-mecanico@example.com")
    from sqlalchemy import text

    async with api_autorizacion.motor.begin() as conn:
        rol = await conn.execute(
            text("SELECT rol, otorgada_por FROM asignacion_rol WHERE usuario_id = :id"),
            {"id": id_nuevo},
        )
        evento = await conn.execute(
            text("SELECT actor, accion FROM evento_seguridad WHERE accion LIKE 'Alta de personal%' ORDER BY id DESC LIMIT 1")
        )
    fila_rol = rol.one()
    assert fila_rol[0] == "MECANICO"
    assert fila_rol[1] == id_admin
    fila_evento = evento.one()
    assert fila_evento[0] == "admin@example.com"
    assert "MECANICO" in fila_evento[1]


async def test_alta_con_rol_cliente_da_422(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post("/usuarios", json={
            "email": "no-cliente@example.com",
            "nombre": "No Cliente",
            "password_provisoria": "Provisoria123!",
            "rol": "CLIENTE",
        })
    assert respuesta.status_code == 422


async def test_alta_con_campo_extra_da_422(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post("/usuarios", json={
            "email": "extra@example.com",
            "nombre": "Extra",
            "password_provisoria": "Provisoria123!",
            "rol": "RECEPCION",
            "activo": False,
        })
    assert respuesta.status_code == 422


async def test_correo_repetido_da_409_sin_filas_sucesoras(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post("/usuarios", json={
            "email": "admin@example.com",
            "nombre": "Duplicado",
            "password_provisoria": "Provisoria123!",
            "rol": "RECEPCION",
        })
    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "Ya existe un usuario con ese correo."}
    from sqlalchemy import text

    async with api_autorizacion.motor.begin() as conn:
        resultado = await conn.execute(
            text("SELECT COUNT(*) FROM asignacion_rol WHERE rol = 'RECEPCION' AND otorgada_por IS NOT NULL")
        )
        assert resultado.scalar_one() == 0


async def test_sin_sesion_o_sin_rol_da_401_o_403(api_autorizacion, abrir_sesion):
    cuerpo = {
        "email": "bloqueado@example.com", "nombre": "Bloqueado",
        "password_provisoria": "Provisoria123!", "rol": "RECEPCION",
    }
    sin_sesion = await api_autorizacion.cliente.post("/usuarios", json=cuerpo)
    async with abrir_sesion("recepcion@example.com") as recepcion:
        sin_rol = await recepcion.post("/usuarios", json=cuerpo)
    assert sin_sesion.status_code == 401
    assert sin_rol.status_code == 403


async def test_alta_no_emite_cookie_ni_sesion(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post("/usuarios", json={
            "email": "sin-sesion@example.com",
            "nombre": "Sin Sesión",
            "password_provisoria": "Provisoria123!",
            "rol": "MECANICO",
        })
    assert respuesta.status_code == 201
    assert "set-cookie" not in {k.lower() for k in respuesta.headers}


async def test_password_provisoria_larga_da_422(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post("/usuarios", json={
            "email": "larga@example.com",
            "nombre": "Larga",
            "password_provisoria": "x" * 73,
            "rol": "MECANICO",
        })
    assert respuesta.status_code == 422
