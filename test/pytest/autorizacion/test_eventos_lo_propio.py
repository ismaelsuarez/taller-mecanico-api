"""T-6: eventos de seguridad y rutas de lo propio — DD-26, RN-17, DD-28, SU-11, T-8."""

from sqlalchemy import text

from autorizacion.conftest import PASSWORD_DE_PRUEBA

from conftest import cliente_http


async def _id_de(api_autorizacion, email: str) -> int:
    async with api_autorizacion.motor.begin() as conn:
        resultado = await conn.execute(
            text("SELECT id FROM usuario WHERE email = :email"), {"email": email}
        )
        return int(resultado.one()[0])


# --- GET /eventos ---


async def test_eventos_paginados_para_admin(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        id_cliente = await _id_de(api_autorizacion, "cliente@example.com")
        await admin.post(f"/usuarios/{id_cliente}/roles", json={"rol": "MECANICO"})
        respuesta = await admin.get("/eventos?page=1&size=5")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"items", "total", "page", "size", "pages"}
    assert cuerpo["total"] >= 1
    assert all({"id", "cuando", "actor", "accion"} <= set(f) for f in cuerpo["items"])
    acciones = [f["accion"] for f in cuerpo["items"]]
    assert any("asignado" in a or "Alta" in a or "Carga" in a for a in acciones)


async def test_eventos_sin_rol_admin_da_403(api_autorizacion, abrir_sesion):
    async with abrir_sesion("recepcion@example.com") as recepcion:
        respuesta = await recepcion.get("/eventos")
    assert respuesta.status_code == 403


async def test_eventos_sin_sesion_da_401(api_autorizacion):
    respuesta = await api_autorizacion.cliente.get("/eventos")
    assert respuesta.status_code == 401


async def test_eventos_pagina_fuera_de_rango_da_422(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.get("/eventos?page=9999")
    assert respuesta.status_code == 422


async def test_eventos_no_expone_secretos(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.get("/eventos?size=100")
    assert respuesta.status_code == 200
    texto = respuesta.text.lower()
    assert "password" not in texto
    assert "hash" not in texto


# --- Preparación de un cliente propio con vehículos y órdenes ---


async def _crear_cliente_propio(api_autorizacion, crear_usuario_autorizacion):
    """Usuario CLIENTE con ficha, 2 vehículos vigentes, 1 dado de baja y 2 órdenes."""
    usuario, password = await crear_usuario_autorizacion(
        email="propio@example.com", roles=("CLIENTE",),
    )
    async with api_autorizacion.motor.begin() as conn:
        await conn.execute(text(
            "INSERT INTO cliente (usuario_id, nombre, documento, telefono) "
            "VALUES (:u, 'Cliente Propio', 'DNI-PROPIO', '111')"
        ), {"u": usuario.id})
        cliente_id = (await conn.execute(text(
            "SELECT id FROM cliente WHERE usuario_id = :u"
        ), {"u": usuario.id})).scalar_one()
        await conn.execute(text(
            "INSERT INTO vehiculo (cliente_id, patente, marca, modelo, anio, borrado_en) VALUES "
            "(:c, 'PR-OP-01', 'Fiat', 'Cronos', 2020, NULL), "
            "(:c, 'PR-OP-02', 'Toyota', 'Corolla', 2022, NULL), "
            "(:c, 'PR-OP-03', 'VW', 'Gol', 2018, now())"
        ), {"c": cliente_id})
        await conn.execute(text(
            "INSERT INTO orden_trabajo (vehiculo_id, estado, falla, creada_en, total) VALUES "
            "((SELECT id FROM vehiculo WHERE patente = 'PR-OP-01'), 'PENDIENTE', "
            "'Falla propia', now(), 1000.00), "
            "((SELECT id FROM vehiculo WHERE patente = 'PR-OP-03'), 'PENDIENTE', "
            "'De vehículo dado de baja', now(), 2000.00)"
        ))
    return usuario, password


# --- GET /mis-vehiculos ---


async def test_mis_vehiculos_muestra_solo_vigentes(api_autorizacion, crear_usuario_autorizacion):
    usuario, password = await _crear_cliente_propio(api_autorizacion, crear_usuario_autorizacion)
    async with cliente_http(api_autorizacion.app) as cliente:
        login = await cliente.post(
            "/auth/login", json={"email": usuario.email, "password": password},
        )
        assert login.status_code == 200, login.text
        respuesta = await cliente.get("/mis-vehiculos")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 2
    patentes = {v["patente"] for v in cuerpo["items"]}
    assert patentes == {"PR-OP-01", "PR-OP-02"}  # el dado de baja no aparece (DD-28)


async def test_mis_vehiculos_sin_ficha_da_pagina_vacia(api_autorizacion, abrir_sesion):
    async with abrir_sesion("mecanico@example.com") as mecanico:
        respuesta = await mecanico.get("/mis-vehiculos")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"items": [], "total": 0, "page": 1, "size": 20, "pages": 1}


async def test_mis_vehiculos_sin_sesion_da_401(api_autorizacion):
    respuesta = await api_autorizacion.cliente.get("/mis-vehiculos")
    assert respuesta.status_code == 401


async def test_mis_vehiculos_pagina_fuera_de_rango_da_422(api_autorizacion, abrir_sesion):
    async with abrir_sesion("cliente@example.com") as cliente:
        respuesta = await cliente.get("/mis-vehiculos?page=999")
    assert respuesta.status_code == 422


# --- GET /mis-ordenes ---


async def test_mis_ordenes_incluye_las_de_vehiculos_dados_de_baja(
    api_autorizacion, crear_usuario_autorizacion,
):
    usuario, password = await _crear_cliente_propio(api_autorizacion, crear_usuario_autorizacion)
    async with cliente_http(api_autorizacion.app) as cliente:
        login = await cliente.post(
            "/auth/login", json={"email": usuario.email, "password": password},
        )
        assert login.status_code == 200, login.text
        respuesta = await cliente.get("/mis-ordenes")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 2  # la del vehículo dado de baja también (DD-28)
    assert cuerpo["items"][0]["estado"] == "PENDIENTE"


async def test_mis_ordenes_no_muestra_las_ajenas(api_autorizacion, abrir_sesion):
    async with abrir_sesion("cliente@example.com") as cliente:
        respuesta = await cliente.get("/mis-ordenes")
    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 0  # Laura no tiene órdenes propias en este entorno


async def test_mis_ordenes_sin_ficha_da_pagina_vacia(api_autorizacion, abrir_sesion):
    async with abrir_sesion("mecanico@example.com") as mecanico:
        respuesta = await mecanico.get("/mis-ordenes")
    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 0


async def test_mis_ordenes_sin_sesion_da_401(api_autorizacion):
    respuesta = await api_autorizacion.cliente.get("/mis-ordenes")
    assert respuesta.status_code == 401


# --- Helper de dueño (T-8) ---


async def test_helper_es_personal_o_dueno(api_autorizacion, crear_usuario_autorizacion):
    """T-8: el personal pasa siempre; el dueño del vehículo también; un ajeno, no."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from app.modules.ordenes.models import OrdenTrabajo
    from app.modules.ordenes.service import es_personal_o_dueno
    from app.modules.ordenes.unit_of_work import UnitOfWorkOrden
    from app.modules.usuarios.schemas import IdentidadLectura, UsuarioLectura

    usuario, _ = await _crear_cliente_propio(api_autorizacion, crear_usuario_autorizacion)
    ajeno, _ = await crear_usuario_autorizacion(email="ajeno@example.com", roles=("CLIENTE",))

    async with api_autorizacion.motor.begin() as conn:
        vehiculo_id = (await conn.execute(text(
            "SELECT id FROM vehiculo WHERE patente = 'PR-OP-01'"
        ))).scalar_one()

    orden = OrdenTrabajo(
        vehiculo_id=vehiculo_id, estado="PENDIENTE", falla="x",
        creada_en=datetime.now(UTC), total=Decimal("0.00"),
    )

    def identidad_de(uid: int, roles: list[str]) -> IdentidadLectura:
        return IdentidadLectura(
            usuario=UsuarioLectura(id=uid, email="x@x", nombre="x", debe_cambiar_password=False),
            roles_vigentes=roles, roles_token=roles,
        )

    async with api_autorizacion.app.state.fabrica_sesiones() as sesion:
        uow = UnitOfWorkOrden(sesion)
        personal = await es_personal_o_dueno(uow, identidad_de(1, ["MECANICO"]), orden)
        duenio = await es_personal_o_dueno(uow, identidad_de(usuario.id, ["CLIENTE"]), orden)
        nadie = await es_personal_o_dueno(uow, identidad_de(ajeno.id, ["CLIENTE"]), orden)

    assert personal is True
    assert duenio is True
    assert nadie is False
