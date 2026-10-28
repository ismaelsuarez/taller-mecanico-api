"""T-5: asignación y revocación de roles — RN-03, RN-05, RT-SE-11, C-07, C-08."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from autorizacion.conftest import PASSWORD_DE_PRUEBA


async def _id_de(api_autorizacion, email: str) -> int:
    async with api_autorizacion.motor.begin() as conn:
        resultado = await conn.execute(
            text("SELECT id FROM usuario WHERE email = :email"), {"email": email}
        )
        return int(resultado.one()[0])


async def _asignacion_abierta(api_autorizacion, usuario_id: int, rol: str):
    async with api_autorizacion.motor.begin() as conn:
        resultado = await conn.execute(
            text(
                "SELECT id, revocada_en, vence_en FROM asignacion_rol "
                "WHERE usuario_id = :u AND rol = :r AND revocada_en IS NULL"
            ),
            {"u": usuario_id, "r": rol},
        )
        return resultado.one_or_none()


# --- Consulta de roles ---


async def test_listar_roles_muestra_solo_vigentes(api_autorizacion, abrir_sesion):
    id_cliente = await _id_de(api_autorizacion, "cliente@example.com")
    async with abrir_sesion("admin@example.com") as admin:
        asignado = await admin.post(
            f"/usuarios/{id_cliente}/roles", json={"rol": "RECEPCION"},
        )
        assert asignado.status_code == 201, asignado.text
        revocado = await admin.delete(f"/usuarios/{id_cliente}/roles/RECEPCION")
        assert revocado.status_code == 200
        listado = await admin.get(f"/usuarios/{id_cliente}/roles")
    assert listado.status_code == 200
    roles = [fila["rol"] for fila in listado.json()["items"]]
    assert roles == ["CLIENTE"]  # la revocada no aparece


async def test_listar_roles_de_usuario_inexistente_da_404(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.get("/usuarios/999999/roles")
    assert respuesta.status_code == 404


async def test_listar_roles_sin_rol_admin_da_403(api_autorizacion, abrir_sesion):
    id_cliente = await _id_de(api_autorizacion, "cliente@example.com")
    async with abrir_sesion("recepcion@example.com") as recepcion:
        respuesta = await recepcion.get(f"/usuarios/{id_cliente}/roles")
    assert respuesta.status_code == 403


# --- Asignación ---


async def test_asignar_rol_con_vencimiento_futuro(api_autorizacion, abrir_sesion):
    id_cliente = await _id_de(api_autorizacion, "cliente@example.com")
    futuro = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post(
            f"/usuarios/{id_cliente}/roles",
            json={"rol": "RECEPCION", "vence_en": futuro},
        )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["rol"] == "RECEPCION"
    assert cuerpo["vence_en"] is not None
    assert cuerpo["otorgada_por"] is not None


async def test_vencimiento_sin_zona_horaria_da_422(api_autorizacion, abrir_sesion):
    id_cliente = await _id_de(api_autorizacion, "cliente@example.com")
    futuro = (datetime.now(UTC) + timedelta(days=1)).replace(tzinfo=None).isoformat()
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post(
            f"/usuarios/{id_cliente}/roles", json={"rol": "MECANICO", "vence_en": futuro},
        )
    assert respuesta.status_code == 422


async def test_vencimiento_en_el_pasado_da_422(api_autorizacion, abrir_sesion):
    id_cliente = await _id_de(api_autorizacion, "cliente@example.com")
    pasado = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post(
            f"/usuarios/{id_cliente}/roles", json={"rol": "MECANICO", "vence_en": pasado},
        )
    assert respuesta.status_code == 422


async def test_rol_abierto_vigente_duplicado_da_409(api_autorizacion, abrir_sesion):
    id_cliente = await _id_de(api_autorizacion, "cliente@example.com")
    async with abrir_sesion("admin@example.com") as admin:
        primero = await admin.post(
            f"/usuarios/{id_cliente}/roles", json={"rol": "RECEPCION"},
        )
        duplicado = await admin.post(
            f"/usuarios/{id_cliente}/roles", json={"rol": "RECEPCION"},
        )
    assert primero.status_code == 201
    assert duplicado.status_code == 409


async def test_reasignar_rol_vencido_cierra_y_abre(api_autorizacion, abrir_sesion):
    id_mecanico = await _id_de(api_autorizacion, "mecanico@example.com")
    async with api_autorizacion.motor.begin() as conn:
        await conn.execute(
            text(
                "UPDATE asignacion_rol SET vence_en = now() - interval '1 hour' "
                "WHERE usuario_id = :u AND rol = 'MECANICO' AND revocada_en IS NULL"
            ),
            {"u": id_mecanico},
        )
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post(
            f"/usuarios/{id_mecanico}/roles", json={"rol": "MECANICO"},
        )
    assert respuesta.status_code == 201, respuesta.text
    async with api_autorizacion.motor.begin() as conn:
        cerradas = await conn.execute(
            text(
                "SELECT COUNT(*) FROM asignacion_rol "
                "WHERE usuario_id = :u AND rol = 'MECANICO' AND revocada_en IS NOT NULL"
            ),
            {"u": id_mecanico},
        )
        abiertas = await conn.execute(
            text(
                "SELECT COUNT(*) FROM asignacion_rol "
                "WHERE usuario_id = :u AND rol = 'MECANICO' AND revocada_en IS NULL"
            ),
            {"u": id_mecanico},
        )
    assert cerradas.scalar_one() >= 1
    assert abiertas.scalar_one() == 1


async def test_asignar_rol_a_usuario_inexistente_da_404(api_autorizacion, abrir_sesion):
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.post(
            "/usuarios/999999/roles", json={"rol": "RECEPCION"},
        )
    assert respuesta.status_code == 404


async def test_asignacion_registra_evento(api_autorizacion, abrir_sesion):
    id_cliente = await _id_de(api_autorizacion, "cliente@example.com")
    async with abrir_sesion("admin2@example.com") as admin2:
        await admin2.post(f"/usuarios/{id_cliente}/roles", json={"rol": "MECANICO"})
    async with api_autorizacion.motor.begin() as conn:
        evento = await conn.execute(
            text(
                "SELECT actor, accion FROM evento_seguridad "
                "WHERE accion LIKE 'Rol MECANICO asignado%' ORDER BY id DESC LIMIT 1"
            )
        )
    fila = evento.one()
    assert fila[0] == "admin2@example.com"
    assert str(id_cliente) in fila[1]


# --- Revocación y autoprotección (C-07, C-08) ---


async def test_revocacion_surte_efecto_en_sesion_abierta(api_autorizacion, abrir_sesion):
    """C-07: la cookie sigue siendo válida, pero la siguiente petición al rol revocado da 403."""
    id_recepcion = await _id_de(api_autorizacion, "recepcion@example.com")
    async with abrir_sesion("recepcion@example.com") as sesion_recepcion:
        antes = await sesion_recepcion.get("/repuestos")
        assert antes.status_code == 200
        async with abrir_sesion("admin@example.com") as admin:
            revocado = await admin.delete(f"/usuarios/{id_recepcion}/roles/RECEPCION")
            assert revocado.status_code == 200
        despues = await sesion_recepcion.get("/repuestos")
    assert despues.status_code == 403
    async with api_autorizacion.motor.begin() as conn:
        fila = await conn.execute(
            text(
                "SELECT revocada_en FROM asignacion_rol "
                "WHERE usuario_id = :u AND rol = 'RECEPCION'"
            ),
            {"u": id_recepcion},
        )
    assert fila.one()[0] is not None  # la fila sigue, no se borra


async def test_admin_no_se_revoca_su_propio_admin(api_autorizacion, abrir_sesion):
    """C-08: el admin no se revoca su ADMIN → 409 y su asignación sigue vigente."""
    id_admin = await _id_de(api_autorizacion, "admin@example.com")
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.delete(f"/usuarios/{id_admin}/roles/ADMIN")
    assert respuesta.status_code == 409
    assert "revocar tu propio rol" in respuesta.json()["detail"]
    async with api_autorizacion.motor.begin() as conn:
        vigente = await conn.execute(
            text(
                "SELECT COUNT(*) FROM asignacion_rol "
                "WHERE usuario_id = :u AND rol = 'ADMIN' AND revocada_en IS NULL"
            ),
            {"u": id_admin},
        )
    assert vigente.scalar_one() == 1


async def test_revocar_otro_admin_cuando_quedan_dos_da_200(
    api_autorizacion, abrir_sesion,
):
    """RN-05: revocar a otro ADMIN está permitido mientras quede al menos uno vigente."""
    id_admin2 = await _id_de(api_autorizacion, "admin2@example.com")
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.delete(f"/usuarios/{id_admin2}/roles/ADMIN")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"mensaje": "Rol ADMIN revocado"}
    async with api_autorizacion.motor.begin() as conn:
        vigente = await conn.execute(
            text(
                "SELECT COUNT(*) FROM asignacion_rol "
                "WHERE rol = 'ADMIN' AND revocada_en IS NULL"
            )
        )
    assert vigente.scalar_one() == 1  # sólo queda admin@example.com


async def test_count_admins_vigentes_ignora_revocados_y_vencidos(api_autorizacion):
    """El conteo de RN-05 cuenta sólo ADMIN no revocados y sin vencer."""
    from app.modules.usuarios.repository import AsignacionRolRepository

    async with api_autorizacion.app.state.fabrica_sesiones() as sesion:
        repo = AsignacionRolRepository(sesion)
        base = await repo.count_admins_vigentes()
    assert base == 2  # admin@example.com y admin2@example.com del entorno

    async with api_autorizacion.motor.begin() as conn:
        await conn.execute(
            text(
                "UPDATE asignacion_rol SET revocada_en = now() "
                "WHERE rol = 'ADMIN' AND revocada_en IS NULL "
                "AND usuario_id = (SELECT id FROM usuario WHERE email = 'admin2@example.com')"
            )
        )
    async with api_autorizacion.app.state.fabrica_sesiones() as sesion:
        repo = AsignacionRolRepository(sesion)
        tras_revocar = await repo.count_admins_vigentes()
    assert tras_revocar == 1


async def test_revocar_rol_inexistente_da_404(api_autorizacion, abrir_sesion):
    id_cliente = await _id_de(api_autorizacion, "cliente@example.com")
    async with abrir_sesion("admin@example.com") as admin:
        respuesta = await admin.delete(f"/usuarios/{id_cliente}/roles/ADMIN")
    assert respuesta.status_code == 404


async def test_revocacion_registra_evento(api_autorizacion, abrir_sesion):
    id_mecanico = await _id_de(api_autorizacion, "mecanico@example.com")
    async with abrir_sesion("admin@example.com") as admin:
        await admin.post(f"/usuarios/{id_mecanico}/roles", json={"rol": "RECEPCION"})
        await admin.delete(f"/usuarios/{id_mecanico}/roles/RECEPCION")
    async with api_autorizacion.motor.begin() as conn:
        evento = await conn.execute(
            text(
                "SELECT actor FROM evento_seguridad "
                "WHERE accion LIKE 'Rol RECEPCION revocado%' ORDER BY id DESC LIMIT 1"
            )
        )
    assert evento.one()[0] == "admin@example.com"
