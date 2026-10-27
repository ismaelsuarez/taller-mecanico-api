"""La fábrica auth entrega credenciales reales sobre el esquema migrado."""

import asyncio
from typing import cast

import bcrypt
from sqlalchemy import column, select, table
from sqlalchemy.orm import QueryableAttribute, selectinload
from sqlmodel import col

from app.modules.usuarios.models import Usuario


async def test_usuarios_consecutivos_autenticables_con_roles_y_secuencias(
    aplicacion_auth, crear_usuario_auth, api_auth,
):
    primero, clave_primera = await crear_usuario_auth(
        email="primero@example.com", roles=("ADMIN", "RECEPCION"),
    )
    segundo, clave_segunda = await crear_usuario_auth(
        email="segundo@example.com", debe_cambiar_password=True,
    )
    assert primero.id > 0
    assert segundo.id == primero.id + 1
    async with aplicacion_auth.state.fabrica_sesiones() as sesion:
        usuarios = (await sesion.execute(
            select(Usuario)
            .options(selectinload(cast(QueryableAttribute, Usuario.roles)))
            .order_by(col(Usuario.id))
        )).scalars().all()
        assert [u.email for u in usuarios] == ["primero@example.com", "segundo@example.com"]
        assert [{r.rol for r in u.roles} for u in usuarios] == [
            {"ADMIN", "RECEPCION"}, {"CLIENTE"},
        ]
        assert [u.debe_cambiar_password for u in usuarios] == [False, True]
        asignaciones = [r for u in usuarios for r in u.roles]
        assert len({r.id for r in asignaciones}) == 3
        assert all(r.vence_en is None and r.revocada_en is None for r in asignaciones)
        assert all(r.desde.tzinfo is not None for r in asignaciones)
    # La verificación independiente observa hashes persistidos, no mocks ni placeholders.
    async with asyncio.Semaphore(1):
        for usuario, clave in zip(usuarios, (clave_primera, clave_segunda), strict=True):
            assert usuario.activo
            assert await asyncio.to_thread(
                bcrypt.checkpw, clave.encode(), usuario.password_hash.encode(),
            )
            assert not await asyncio.to_thread(
                bcrypt.checkpw, b"incorrecta", usuario.password_hash.encode(),
            )
    assert (await api_auth.get("/health/ready")).status_code == 200


async def test_auth_reutiliza_alembic_con_sus_disparadores(aplicacion_auth):
    version = table("alembic_version", column("version_num"))
    catalogo = table("pg_trigger", column("tgname"), column("tgisinternal"))
    async with aplicacion_auth.state.motor.connect() as conexion:
        assert (await conexion.execute(
            select(version.c.version_num)
        )).scalars().all() == ["a1b2c3d4e5f6"]
        disparadores = await conexion.execute(
            select(catalogo.c.tgname).where(catalogo.c.tgisinternal.is_(False))
        )
        assert set(disparadores.scalars()) == {
            "trg_historial_estado_orden_solo_agregado",
            "trg_movimiento_stock_solo_agregado",
            "trg_historial_precio_repuesto_solo_agregado",
        }
