"""Fixtures de EJ-6 para el módulo órdenes: PostgreSQL real migrada con Alembic.

`fabrica` entrega una fábrica de sesiones sobre el esquema de Alembic con el
catálogo `estado_orden` ya cargado (lo hace `seed.py` en producción, A-5), y
`Datos` arma filas reales dentro de una sesión (sin mocks de la base).
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import ItemOrden, OrdenTrabajo
from app.modules.repuestos.models import Repuesto
from app.modules.usuarios.models import Usuario
from autorizacion.conftest import (  # noqa: F401  (se reutilizan las sesiones reales de EJ-5, sin duplicarlas)
    abrir_sesion,
    api_autorizacion,
    crear_usuario_autorizacion,
)
from conftest import (  # el conftest raíz lo importa pytest como módulo suelto
    CATALOGO_ESTADOS,
    aplicacion_iniciada,
    cliente_http,
)


@pytest.fixture
async def fabrica(base_migrada):
    """Fábrica de sesiones sobre el esquema migrado, con el catálogo de estados cargado."""
    async with base_migrada.begin() as conn:
        for codigo, descripcion, posicion, es_final in CATALOGO_ESTADOS:
            await conn.execute(
                text(
                    "INSERT INTO estado_orden (codigo, descripcion, posicion, es_final) "
                    "VALUES (:c, :d, :p, :f)"
                ),
                {"c": codigo, "d": descripcion, "p": posicion, "f": es_final},
            )
    yield async_sessionmaker(base_migrada, expire_on_commit=False)


class Datos:
    """Constructores de filas reales; hacen `flush` y dejan el `commit` al test."""

    def __init__(self, sesion: AsyncSession) -> None:
        self.sesion = sesion

    async def usuario(self, email: str) -> Usuario:
        usuario = Usuario(
            email=email, nombre="Usuario de prueba", password_hash="x" * 60,
            activo=True, debe_cambiar_password=False,
        )
        self.sesion.add(usuario)
        await self.sesion.flush()
        return usuario

    async def cliente(self, documento: str, usuario: Usuario | None = None) -> Cliente:
        cliente = Cliente(
            nombre="Cliente de prueba", documento=documento, telefono="11-5555-0000",
            usuario_id=usuario.id if usuario else None,
        )
        self.sesion.add(cliente)
        await self.sesion.flush()
        return cliente

    async def vehiculo(self, cliente: Cliente, patente: str, *, de_baja: bool = False) -> Vehiculo:
        vehiculo = Vehiculo(
            cliente_id=cliente.id, patente=patente, marca="Fiat", modelo="Cronos", anio=2020,
            borrado_en=datetime.now(UTC) if de_baja else None,
        )
        self.sesion.add(vehiculo)
        await self.sesion.flush()
        return vehiculo

    async def repuesto(
        self, codigo: str, *, precio: str = "100.00", stock: int = 10, de_baja: bool = False,
    ) -> Repuesto:
        repuesto = Repuesto(
            codigo=codigo, descripcion=f"Repuesto {codigo}", precio=Decimal(precio), stock=stock,
            borrado_en=datetime.now(UTC) if de_baja else None,
        )
        self.sesion.add(repuesto)
        await self.sesion.flush()
        return repuesto

    async def orden(
        self,
        vehiculo: Vehiculo,
        estado: str = "PENDIENTE",
        items: tuple[tuple[Repuesto, int], ...] = (),
        mecanico: Usuario | None = None,
    ) -> OrdenTrabajo:
        total = sum((repuesto.precio * cantidad for repuesto, cantidad in items), Decimal("0.00"))
        orden = OrdenTrabajo(
            vehiculo_id=vehiculo.id, estado=estado, falla="Falla de prueba",
            creada_en=datetime.now(UTC), total=total,
            mecanico_id=mecanico.id if mecanico else None,
        )
        self.sesion.add(orden)
        await self.sesion.flush()
        for repuesto, cantidad in items:
            self.sesion.add(ItemOrden(
                orden_id=orden.id, repuesto_id=repuesto.id, cantidad=cantidad,
                precio_unitario=repuesto.precio,
            ))
        await self.sesion.flush()
        return orden


@pytest.fixture
async def base_sembrada(base_migrada):
    """Esquema de Alembic con los datos iniciales reales de `seed.py` (subproceso, como en producción)."""
    from test_seed import _ejecutar_seed  # reutiliza el runner del test del seed (sin duplicarlo)

    await _ejecutar_seed()
    return base_migrada


# Contraseñas de mentira del seed (viven sólo en seed.py, S-6): se importan, no se copian.
def _passwords_del_seed() -> dict[str, str]:
    import seed

    return {
        "admin@example.com": seed.PASSWORD_ADMIN,
        "admin2@example.com": seed.PASSWORD_ADMIN,
        "recepcion@example.com": seed.PASSWORD_RECEPCION,
        "mecanico@example.com": seed.PASSWORD_MECANICO,
        "mecanico2@example.com": seed.PASSWORD_MECANICO,
        "cliente@example.com": seed.PASSWORD_CLIENTE,
        "nuevo@example.com": seed.PASSWORD_NUEVO,
    }


@dataclass(frozen=True)
class EntornoSembrado:
    """API levantada sobre los datos reales del seed; `entrar` abre una sesión por login real."""

    app: FastAPI
    motor: AsyncEngine
    entrar: Callable[[str], AbstractAsyncContextManager[AsyncClient]]
    anonimo: Callable[[], AbstractAsyncContextManager[AsyncClient]]

    async def contar(self, *tablas: str) -> list[int]:
        """Cantidad de filas de cada tabla (nombres fijos del código de test, nunca del usuario)."""
        cuentas = []
        async with self.motor.connect() as conn:
            for tabla in tablas:
                cuentas.append((await conn.execute(text(f"SELECT count(*) FROM {tabla}"))).scalar_one())
        return cuentas

    async def consulta(self, sql: str, **parametros):
        async with self.motor.connect() as conn:
            return (await conn.execute(text(sql), parametros)).all()

    async def ejecutar(self, sql: str, **parametros) -> None:
        async with self.motor.begin() as conn:
            await conn.execute(text(sql), parametros)


@pytest.fixture
async def api_sembrada(base_sembrada) -> AsyncIterator[EntornoSembrado]:
    """La aplicación real con lifespan, sobre Alembic + `seed.py` (C-06, C-10..C-13, C-17)."""
    passwords = _passwords_del_seed()
    async with aplicacion_iniciada() as app:

        @asynccontextmanager
        async def entrar(email: str) -> AsyncIterator[AsyncClient]:
            async with cliente_http(app) as cliente:
                login = await cliente.post(
                    "/auth/login", json={"email": email, "password": passwords[email]},
                )
                assert login.status_code == 200, login.text
                yield cliente

        yield EntornoSembrado(
            app=app, motor=base_sembrada, entrar=entrar, anonimo=lambda: cliente_http(app),
        )
