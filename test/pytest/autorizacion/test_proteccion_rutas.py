"""T-3.1–T-3.3: matriz RBAC sobre las rutas existentes, auditoría con la sesión y los dos grupos."""

import pytest

from autorizacion.conftest import PASSWORD_DE_PRUEBA

from conftest import cliente_http


async def _token_de(api_autorizacion, email: str) -> str:
    async with cliente_http(api_autorizacion.app) as cliente:
        respuesta = await cliente.post(
            "/auth/login", json={"email": email, "password": PASSWORD_DE_PRUEBA},
        )
        assert respuesta.status_code == 200, respuesta.text
        token = respuesta.cookies.get("access_token")
    assert token is not None
    return token


async def _consultar_id(api_autorizacion, email: str) -> int:
    from sqlalchemy import text

    async with api_autorizacion.motor.begin() as conn:
        resultado = await conn.execute(
            text("SELECT id FROM usuario WHERE email = :email"), {"email": email}
        )
        fila = resultado.one()
    return int(fila[0])


async def _crear_repuesto(abrir_sesion) -> dict:
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post("/repuestos", json={
            "codigo": "FIL-001", "descripcion": "Filtro de aceite",
            "precio": "1500.00", "stock_inicial": 3,
        })
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


# --- T-3.1: la matriz de permisos ---


async def test_c18_recepcion_no_cambia_precio_ni_descripcion(api_autorizacion, abrir_sesion):
    creado = await _crear_repuesto(abrir_sesion)
    async with abrir_sesion("recepcion@example.com") as recepcion:
        precio = await recepcion.patch(
            f"/repuestos/{creado['id']}", json={"precio": "9999.00"},
        )
        descripcion = await recepcion.patch(
            f"/repuestos/{creado['id']}", json={"descripcion": "Otra descripción"},
        )
    assert precio.status_code == 403
    assert descripcion.status_code == 403

    async with abrir_sesion("admin@example.com") as admin:
        detalle = await admin.get(f"/repuestos/{creado['id']}")
        historial = await admin.get(f"/repuestos/{creado['id']}/precios")
    assert detalle.json()["precio"] == "1500.00"
    assert detalle.json()["descripcion"] == "Filtro de aceite"
    assert historial.json() == []


async def test_mecanico_consulta_repuestos_y_clientes_requiere_recepcion(
    api_autorizacion, abrir_sesion,
):
    await _crear_repuesto(abrir_sesion)
    async with abrir_sesion("mecanico@example.com") as mecanico:
        listado = await mecanico.get("/repuestos")
        clientes = await mecanico.post("/clientes", json={
            "nombre": "Sin Permiso", "documento": "DNI-999", "telefono": "11-999",
        })
    assert listado.status_code == 200
    assert clientes.status_code == 403


async def test_cliente_sin_rol_de_personal_recibe_403(api_autorizacion, abrir_sesion):
    await _crear_repuesto(abrir_sesion)
    async with abrir_sesion("cliente@example.com") as cliente_sesion:
        repuestos = await cliente_sesion.get("/repuestos")
        ficha = await cliente_sesion.get("/clientes/1")
    assert repuestos.status_code == 403
    assert ficha.status_code == 403


@pytest.mark.parametrize("ruta,metodo", [
    ("/clientes", "post"),
    ("/clientes/1", "get"),
    ("/repuestos", "get"),
    ("/repuestos", "post"),
])
async def test_sin_sesion_da_401_y_no_403(api_autorizacion, ruta, metodo):
    peticion = getattr(api_autorizacion.cliente, metodo)
    respuesta = await peticion(ruta, json={}) if metodo == "post" else await peticion(ruta)
    assert respuesta.status_code == 401


# --- T-3.2: la auditoría firma con el usuario de la sesión ---


async def test_reposicion_firmada_por_el_admin_de_la_sesion(api_autorizacion, abrir_sesion):
    creado = await _crear_repuesto(abrir_sesion)
    id_admin = await _consultar_id(api_autorizacion, "admin@example.com")
    id_admin2 = await _consultar_id(api_autorizacion, "admin2@example.com")
    async with abrir_sesion("admin2@example.com") as admin2:
        respuesta = await admin2.post(
            f"/repuestos/{creado['id']}/reponer", json={"cantidad": 5, "motivo": "Reposición"},
        )
    assert respuesta.status_code == 200
    async with abrir_sesion("admin@example.com") as admin:
        movimientos = (await admin.get(
            f"/repuestos/{creado['id']}/movimientos",
        )).json()
    # Stock inicial (admin que dio el alta) + reposición firmada por admin2.
    assert [fila["usuario_id"] for fila in movimientos] == [id_admin, id_admin2]


async def test_precio_cambiado_por_el_admin_de_la_sesion(api_autorizacion, abrir_sesion):
    creado = await _crear_repuesto(abrir_sesion)
    id_admin2 = await _consultar_id(api_autorizacion, "admin2@example.com")
    async with abrir_sesion("admin2@example.com") as admin2:
        respuesta = await admin2.patch(
            f"/repuestos/{creado['id']}", json={"precio": "2500.00"},
        )
    assert respuesta.status_code == 200
    async with abrir_sesion("admin@example.com") as admin:
        historial = (await admin.get(
            f"/repuestos/{creado['id']}/precios",
        )).json()
    assert [fila["usuario_id"] for fila in historial] == [id_admin2]


async def test_sin_sesion_no_se_escribe_auditoria(api_autorizacion, abrir_sesion):
    creado = await _crear_repuesto(abrir_sesion)
    reponer = await api_autorizacion.cliente.post(
        f"/repuestos/{creado['id']}/reponer", json={"cantidad": 2, "motivo": "No debe quedar"},
    )
    patch = await api_autorizacion.cliente.patch(
        f"/repuestos/{creado['id']}", json={"precio": "3000.00"},
    )
    assert reponer.status_code == 401
    assert patch.status_code == 401
    async with abrir_sesion("admin@example.com") as admin:
        movimientos = (await admin.get(
            f"/repuestos/{creado['id']}/movimientos",
        )).json()
        historial = (await admin.get(
            f"/repuestos/{creado['id']}/precios",
        )).json()
        detalle = (await admin.get(f"/repuestos/{creado['id']}")).json()
    assert len(movimientos) == 1  # sólo el «Stock inicial»
    assert historial == []
    assert detalle["stock"] == 3


# --- T-3.3: los dos grupos y el cambio obligatorio (C-09) ---


async def test_c09_cambio_pendiente_bloquea_lo_protegido_y_no_lo_propio(
    api_autorizacion, abrir_sesion,
):
    nuevo_token = await _token_de(api_autorizacion, "nuevo@example.com")
    async with abrir_sesion("nuevo@example.com") as nuevo:
        protegido = await nuevo.get("/repuestos")
        identidad = await nuevo.get("/auth/yo")
    assert protegido.status_code == 403
    assert protegido.json() == {"detail": "Tenés que cambiar tu contraseña antes de continuar."}
    assert identidad.status_code == 200
    assert identidad.json()["usuario"]["debe_cambiar_password"] is True

    cambio = await api_autorizacion.cliente.post(
        "/auth/cambiar-password",
        json={"password_actual": PASSWORD_DE_PRUEBA, "password_nueva": "clave-nueva-123"},
        cookies={"access_token": nuevo_token},
    )
    assert cambio.status_code == 200
    cookie_nueva = cambio.cookies.get("access_token")
    assert cookie_nueva and cookie_nueva != nuevo_token

    async with cliente_http(api_autorizacion.app) as despues:
        despues.cookies.set("access_token", cookie_nueva)
        desbloqueado = await despues.get("/repuestos")
        vieja = await despues.get("/repuestos", cookies={"access_token": nuevo_token})
    assert desbloqueado.status_code == 200
    assert vieja.status_code == 401


async def test_las_rutas_abiertas_siguen_sin_sesion(api_autorizacion):
    vivo = await api_autorizacion.cliente.get("/health/live")
    assert vivo.status_code == 200
    login = await api_autorizacion.cliente.post(
        "/auth/login", json={"email": "admin@example.com", "password": PASSWORD_DE_PRUEBA},
    )
    assert login.status_code == 200
