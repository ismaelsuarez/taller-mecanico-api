"""Deja la base en el estado inicial conocido del taller (EJ-2).

Uso: `python seed.py` después de `alembic upgrade head`.
Vacía las tablas en orden seguro y recarga: catálogo, usuarios con roles, clientes y
vehículos, repuestos con su movimiento «Stock inicial», dos órdenes con historiales,
historial de precios del filtro y un evento de seguridad con actor `SISTEMA`.
Es idempotente: dos corridas dejan el mismo estado lógico.

Las contraseñas de abajo son DE MENTIRA y viven sólo en este archivo (S-6):
son datos de prueba para poder loguearse en desarrollo; no son credenciales reales.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

# Importar todos los modelos para registrarlos en el metadata (por si se usa create_all en tests).
from app.modules.clientes import models as _models_clientes  # noqa: F401
from app.modules.ordenes import models as _models_ordenes  # noqa: F401
from app.modules.repuestos import models as _models_repuestos  # noqa: F401
from app.modules.usuarios import models as _models_usuarios  # noqa: F401

# ---------------------------------------------------------------------------
# Contraseñas de prueba — SOLO ACÁ, nunca en configuración ni en el repo (S-6).
# ---------------------------------------------------------------------------
PASSWORD_ADMIN = "Admin1234!"
PASSWORD_RECEPCION = "Recep1234!"
PASSWORD_MECANICO = "Mecan1234!"
PASSWORD_CLIENTE = "Client1234!"
PASSWORD_NUEVO = "Nuev1234!"
# ---------------------------------------------------------------------------

AHORA = datetime.now(timezone.utc)


def _url() -> str:
    from app.core.config import cargar_settings

    return cargar_settings().url_base_datos


def _settings():
    from app.core.config import cargar_settings

    return cargar_settings()


async def _hashear(password: str, rondas: int) -> str:
    """Hash bcrypt con la utilidad del proyecto (T-5: reutiliza security.py)."""
    from app.core.security import configurar_semaforo_bcrypt, hashear_password

    configurar_semaforo_bcrypt(1)
    return await hashear_password(password, rondas)


async def _vaciar(sesion) -> None:
    """Vacía las tablas en orden inverso a las dependencias.

    Usa TRUNCATE ... CASCADE: los disparadores de sólo agregado son FOR EACH ROW y no se
    disparan con TRUNCATE (que es a nivel de sentencia), así que el seed puede recargar
    las tablas de auditoría sin violar RN-15.
    """
    tablas = [
        "historial_estado_orden",
        "movimiento_stock",
        "historial_precio_repuesto",
        "item_orden",
        "orden_trabajo",
        "vehiculo",
        "cliente",
        "asignacion_rol",
        "intento_acceso",
        "evento_seguridad",
        "usuario",
        "repuesto",
        "estado_orden",
    ]
    for tabla in tablas:
        await sesion.execute(text(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE"))


async def _cargar(sesion, hashes: dict[str, str]) -> None:
    # 1. Catálogo de estados (primero: las órdenes dependen de él).
    estados = [
        ("PENDIENTE", "Esperando ser tomada por un mecánico", 1, False),
        ("EN_REPARACION", "En curso de reparación", 2, False),
        ("TERMINADA", "Reparación terminada", 3, True),
        ("CANCELADA", "Orden cancelada", 4, True),
    ]
    for codigo, descripcion, posicion, es_final in estados:
        await sesion.execute(
            text(
                "INSERT INTO estado_orden (codigo, descripcion, posicion, es_final) "
                "VALUES (:codigo, :descripcion, :posicion, :es_final)"
            ),
            {"codigo": codigo, "descripcion": descripcion, "posicion": posicion, "es_final": es_final},
        )

    # 2. Usuarios.
    usuarios = [
        (1, "admin@example.com", "Administrador Uno", PASSWORD_ADMIN, True, False),
        (2, "admin2@example.com", "Administrador Dos", PASSWORD_ADMIN, True, False),
        (3, "recepcion@example.com", "Recepción", PASSWORD_RECEPCION, True, False),
        (4, "mecanico@example.com", "Mecánico Uno", PASSWORD_MECANICO, True, False),
        (5, "mecanico2@example.com", "Mecánico Dos", PASSWORD_MECANICO, True, False),
        (6, "cliente@example.com", "Laura Cliente", PASSWORD_CLIENTE, True, False),
        (7, "nuevo@example.com", "Nuevo Mecánico", PASSWORD_NUEVO, True, True),
    ]
    for uid, email, nombre, password, activo, debe_cambiar in usuarios:
        await sesion.execute(
            text(
                "INSERT INTO usuario (id, email, nombre, password_hash, activo, debe_cambiar_password) "
                "VALUES (:id, :email, :nombre, :hash, :activo, :debe)"
            ),
            {
                "id": uid,
                "email": email,
                "nombre": nombre,
                "hash": hashes[email],
                "activo": activo,
                "debe": debe_cambiar,
            },
        )

    # 3. Roles vigentes.
    roles = [
        (1, "ADMIN"), (2, "ADMIN"), (3, "RECEPCION"),
        (4, "MECANICO"), (5, "MECANICO"), (6, "CLIENTE"), (7, "MECANICO"),
    ]
    for uid, rol in roles:
        await sesion.execute(
            text(
                "INSERT INTO asignacion_rol (usuario_id, rol, desde) "
                "VALUES (:uid, :rol, :desde)"
            ),
            {"uid": uid, "rol": rol, "desde": AHORA},
        )

    # 4. Clientes.
    # Laura (id=1) con usuario (id=6); Jorge (id=2) sin usuario.
    await sesion.execute(
        text(
            "INSERT INTO cliente (id, usuario_id, nombre, documento, telefono) "
            "VALUES (1, 6, 'Laura Cliente', 'DNI-30111222', '11-5555-0001')"
        )
    )
    await sesion.execute(
        text(
            "INSERT INTO cliente (id, usuario_id, nombre, documento, telefono) "
            "VALUES (2, NULL, 'Jorge Sin Cuenta', 'DNI-28999888', '11-5555-0002')"
        )
    )

    # 5. Vehículos: Laura tiene 2 (id 1 y 2 — AC456EF), Jorge 1 (id 3).
    await sesion.execute(
        text(
            "INSERT INTO vehiculo (id, cliente_id, patente, marca, modelo, anio) VALUES "
            "(1, 1, 'AA111BB', 'Fiat', 'Cronos', 2020), "
            "(2, 1, 'AC456EF', 'Toyota', 'Corolla', 2022), "
            "(3, 2, 'ZZ999YY', 'Ford', 'Ka', 2018)"
        )
    )

    # 6. Repuestos (ids y códigos de la consigna).
    repuestos = [
        (1, "FIL-001", "Filtro de aceite", Decimal("8500.00"), 10),
        (2, "FRE-010", "Pastillas de freno delanteras", Decimal("32000.00"), 4),
        (3, "BUJ-014", "Bujía de encendido", Decimal("6500.00"), 2),
        (4, "ACE-530", "Aceite 5W30 por litro", Decimal("12000.00"), 20),
    ]
    for rid, codigo, descripcion, precio, stock in repuestos:
        await sesion.execute(
            text(
                "INSERT INTO repuesto (id, codigo, descripcion, precio, stock) "
                "VALUES (:id, :codigo, :descripcion, :precio, :stock)"
            ),
            {"id": rid, "codigo": codigo, "descripcion": descripcion, "precio": precio, "stock": stock},
        )
        # Movimiento «Stock inicial» (DD-14: actor admin@example.com).
        await sesion.execute(
            text(
                "INSERT INTO movimiento_stock (repuesto_id, orden_id, usuario_id, cantidad, motivo, cuando) "
                "VALUES (:rid, NULL, 1, :stock, 'Stock inicial', :cuando)"
            ),
            {"rid": rid, "stock": stock, "cuando": AHORA},
        )

    # 7. Órdenes.
    # Orden 1: PENDIENTE, primer vehículo de Laura, «Cambio de aceite y filtro» (DD-15).
    await sesion.execute(
        text(
            "INSERT INTO orden_trabajo (id, vehiculo_id, mecanico_id, estado, falla, creada_en, total) VALUES "
            "(1, 1, NULL, 'PENDIENTE', 'Cambio de aceite y filtro', :cuando, 56500.00)"
        ),
        {"cuando": AHORA},
    )
    await sesion.execute(
        text(
            "INSERT INTO item_orden (orden_id, repuesto_id, cantidad, precio_unitario) VALUES "
            "(1, 1, 1, 8500.00), (1, 4, 4, 12000.00)"
        )
    )
    # Orden 2: EN_REPARACION, vehículo de Jorge, «Falla de encendido», 4 bujías con stock 2 (DD-16).
    await sesion.execute(
        text(
            "INSERT INTO orden_trabajo (id, vehiculo_id, mecanico_id, estado, falla, creada_en, total) VALUES "
            "(2, 3, 4, 'EN_REPARACION', 'Falla de encendido', :cuando, 26000.00)"
        ),
        {"cuando": AHORA},
    )
    await sesion.execute(
        text(
            "INSERT INTO item_orden (orden_id, repuesto_id, cantidad, precio_unitario) VALUES "
            "(2, 3, 4, 6500.00)"
        )
    )

    # 8. Historial de estados (DD-14).
    await sesion.execute(
        text(
            "INSERT INTO historial_estado_orden (orden_id, desde_estado, hasta_estado, usuario_id, cuando) VALUES "
            "(1, NULL, 'PENDIENTE', 3, :cuando), "
            "(2, NULL, 'PENDIENTE', 3, :cuando), "
            "(2, 'PENDIENTE', 'EN_REPARACION', 4, :cuando)"
        ),
        {"cuando": AHORA},
    )

    # 9. Historial de precios del filtro (8000 → 8500, actor admin).
    await sesion.execute(
        text(
            "INSERT INTO historial_precio_repuesto (repuesto_id, usuario_id, precio_anterior, precio_nuevo, cuando) "
            "VALUES (1, 1, 8000.00, 8500.00, :cuando)"
        ),
        {"cuando": AHORA},
    )

    # 10. Evento de seguridad del sistema.
    await sesion.execute(
        text(
            "INSERT INTO evento_seguridad (cuando, actor, accion) VALUES "
            "(:cuando, 'SISTEMA', 'Carga de los datos iniciales')"
        ),
        {"cuando": AHORA},
    )

    # 11. Secuencias: `TRUNCATE ... RESTART IDENTITY` dejó cada secuencia en 1 y
    # los ids del seed son explícitos, así que no la avanzan. Sin este paso el
    # primer alta de la API insertaría id=1 y chocaría con un id ya sembrado
    # (DD-38). Sólo estas tablas reciben ids explícitos acá; el resto se llenó
    # con ids implícitos, que ya dejaron la secuencia en su lugar.
    for tabla in ("usuario", "cliente", "vehiculo", "repuesto", "orden_trabajo"):
        # `tabla` sale de esta lista fija del código, nunca de datos externos.
        await sesion.execute(
            text(
                "SELECT setval(pg_get_serial_sequence(:tabla, 'id'), "
                "COALESCE((SELECT max(id) FROM " + tabla + "), 1), "
                "EXISTS (SELECT 1 FROM " + tabla + "))"
            ),
            {"tabla": tabla},
        )


async def sembrar() -> None:
    settings = _settings()
    motor = create_async_engine(settings.url_base_datos)
    try:
        # Verificar que las tablas existen (si no, falta migrar).
        async with motor.connect() as conn:
            existe = await conn.execute(
                text("SELECT to_regclass('estado_orden') IS NOT NULL")
            )
            if not existe.scalar():
                raise SystemExit(
                    "Falta migrar la base: corré `alembic upgrade head` antes de `python seed.py`."
                )

        # Hashear contraseñas antes de abrir la transacción (costo de bcrypt).
        emails_con_password = {
            "admin@example.com": PASSWORD_ADMIN,
            "admin2@example.com": PASSWORD_ADMIN,
            "recepcion@example.com": PASSWORD_RECEPCION,
            "mecanico@example.com": PASSWORD_MECANICO,
            "mecanico2@example.com": PASSWORD_MECANICO,
            "cliente@example.com": PASSWORD_CLIENTE,
            "nuevo@example.com": PASSWORD_NUEVO,
        }
        hashes = {}
        for email, password in emails_con_password.items():
            hashes[email] = await _hashear(password, settings.bcrypt_rounds)

        # Vaciar y recargar en una sola transacción.
        from sqlalchemy.ext.asyncio import AsyncSession

        async with motor.connect() as conexion:
            async with conexion.begin():
                sesion = AsyncSession(bind=conexion)
                await _vaciar(sesion)
                await _cargar(sesion, hashes)
                await sesion.flush()

        print("Seed aplicado: la base quedó en el estado inicial conocido.")
    finally:
        await motor.dispose()


def main() -> None:
    asyncio.run(sembrar())


if __name__ == "__main__":
    main()
