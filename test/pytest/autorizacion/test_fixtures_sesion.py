"""Evidencia T-1.3: sesión real por login, roles vigentes y cambio pendiente."""

import pytest


async def test_login_real_entrega_cookie_y_roles_vigentes(abrir_sesion):
    async with abrir_sesion("admin@example.com") as cliente:
        assert cliente.cookies.get("access_token")
        yo = await cliente.get("/auth/yo")
    assert yo.status_code == 200
    cuerpo = yo.json()
    assert cuerpo["usuario"]["email"] == "admin@example.com"
    assert cuerpo["usuario"]["debe_cambiar_password"] is False
    assert cuerpo["roles_vigentes"] == ["ADMIN"]
    assert cuerpo["roles_token"] == ["ADMIN"]


@pytest.mark.parametrize("email,rol", [
    ("recepcion@example.com", "RECEPCION"),
    ("mecanico@example.com", "MECANICO"),
    ("cliente@example.com", "CLIENTE"),
])
async def test_usuarios_fijos_entran_con_su_rol_vigente(abrir_sesion, email, rol):
    async with abrir_sesion(email) as cliente:
        yo = await cliente.get("/auth/yo")
    assert yo.status_code == 200
    assert yo.json()["roles_vigentes"] == [rol]


async def test_nuevo_entra_con_cambio_pendiente_y_rol_vigente(abrir_sesion):
    async with abrir_sesion("nuevo@example.com") as cliente:
        yo = await cliente.get("/auth/yo")
    assert yo.status_code == 200
    cuerpo = yo.json()
    assert cuerpo["usuario"]["debe_cambiar_password"] is True
    assert cuerpo["roles_vigentes"] == ["MECANICO"]


async def test_login_con_password_equivocada_no_entrega_cookie(api_autorizacion):
    respuesta = await api_autorizacion.cliente.post(
        "/auth/login", json={"email": "admin@example.com", "password": "otra-clave"},
    )
    assert respuesta.status_code == 401
    assert "access_token" not in respuesta.cookies


async def test_fabrica_crea_usuario_ad_hoc_con_su_rol(crear_usuario_autorizacion, abrir_sesion):
    usuario, password = await crear_usuario_autorizacion(
        email="ad-hoc@example.com", roles=("MECANICO",),
    )
    async with abrir_sesion("ad-hoc@example.com", password) as cliente:
        yo = await cliente.get("/auth/yo")
    assert yo.status_code == 200
    assert yo.json()["usuario"]["id"] == usuario.id
    assert yo.json()["roles_vigentes"] == ["MECANICO"]


async def test_fabrica_puede_crear_inactivo(crear_usuario_autorizacion):
    usuario, _ = await crear_usuario_autorizacion(
        email="inactivo@example.com", roles=(), activo=False,
    )
    assert usuario.id is not None
    assert usuario.activo is False
