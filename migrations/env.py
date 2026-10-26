"""Entorno de Alembic con plantilla asincrónica (EJ-2).

La URL nunca vive en `alembic.ini` (S-6): se arma desde `Settings` (variables de entorno /
`.env`), igual que la aplicación. Los modelos se importan todos para que `--autogenerate`
vea las 13 tablas.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Importar todos los modelos para registrarlos en el metadata (autogenerate).
from app.modules.clientes import models as models_clientes  # noqa: F401
from app.modules.ordenes import models as models_ordenes  # noqa: F401
from app.modules.repuestos import models as models_repuestos  # noqa: F401
from app.modules.usuarios import models as models_usuarios  # noqa: F401
from sqlmodel import SQLModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _url_desde_settings() -> str:
    """URL asincrónica desde la configuración del entorno; nunca desde el .ini."""
    from app.core.config import cargar_settings

    return cargar_settings().url_base_datos


def run_migrations_offline() -> None:
    """Corre migraciones en modo offline (sólo genera SQL, no necesita DBAPI)."""
    url = _url_desde_settings()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Corre migraciones en modo online con un motor asincrónico."""
    # La URL no viene del .ini: la arma Settings desde el entorno.
    seccion = dict(config.get_section(config.config_ini_section, {}) or {})
    seccion["sqlalchemy.url"] = _url_desde_settings()

    connectable = async_engine_from_config(
        seccion,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
