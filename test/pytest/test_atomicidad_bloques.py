"""RN-02 y RN-20 escriben en un solo bloque de Unit of Work (spec persistencia, RT-TX-04).

Falla inyectada en una escritura intermedia o final, contra la PostgreSQL real
migrada con Alembic: si cualquiera falla, no queda ninguna fila del bloque. Cada
caso lleva su control de éxito para que la falla no sea una prueba vacía.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core import security
from app.modules.clientes.models import Cliente
from app.modules.repuestos.models import HistorialPrecio, Repuesto
from app.modules.repuestos.schemas import RepuestoActualizar
from app.modules.repuestos.service import actualizar_repuesto
from app.modules.repuestos.unit_of_work import UnitOfWorkRepuesto
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, Usuario
from app.modules.usuarios.schemas import RegistroEntrada
from app.modules.usuarios.service import registrar_usuario
from app.modules.usuarios.unit_of_work import UnitOfWorkUsuario

RONDAS_DE_TEST = 4


@pytest.fixture(autouse=True)
def semaforo_bcrypt(monkeypatch):
    """Semáforo propio de cada test (el lifespan no corre acá): se descarta al terminar."""
    monkeypatch.setattr(security, "_semaforo", None)
    security.configurar_semaforo_bcrypt(1)


@pytest.fixture
async def fabrica_de_sesiones(base_migrada):
    yield async_sessionmaker(base_migrada, expire_on_commit=False)


async def _contar(fabrica, modelo) -> int:
    async with fabrica() as sesion:
        return (await sesion.execute(select(func.count()).select_from(modelo))).scalar_one()


def _registro(email: str = "nuevo@example.com", documento: str = "DNI-30001") -> RegistroEntrada:
    return RegistroEntrada(
        nombre="Ana Pérez", documento=documento, telefono="11-5555-0001",
        email=email, password="clave-de-registro-1",
    )


async def _filas_de_registro(fabrica) -> tuple[int, ...]:
    return tuple([
        await _contar(fabrica, modelo)
        for modelo in (Usuario, AsignacionRol, Cliente, EventoSeguridad)
    ])


class TestRegistroEnUnSoloBloque:
    """RN-02: usuario + rol CLIENTE + ficha (+ evento) o nada."""

    async def test_el_registro_exitoso_deja_las_cuatro_filas(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            await registrar_usuario(UnitOfWorkUsuario(sesion), _registro(), RONDAS_DE_TEST)
        assert await _filas_de_registro(fabrica_de_sesiones) == (1, 1, 1, 1)

    @pytest.mark.parametrize(
        ("repositorio", "etiqueta"),
        [("eventos", "ultima-escritura"), ("clientes", "escritura-intermedia")],
    )
    async def test_una_falla_en_el_bloque_no_deja_ninguna_fila(
        self, fabrica_de_sesiones, monkeypatch, repositorio, etiqueta,
    ):
        async with fabrica_de_sesiones() as sesion:
            uow = UnitOfWorkUsuario(sesion)

            async def falla(*_args, **_kwargs):
                raise RuntimeError(f"falla inyectada: {etiqueta}")

            monkeypatch.setattr(getattr(uow, repositorio), "add", falla)
            with pytest.raises(RuntimeError, match="falla inyectada"):
                await registrar_usuario(
                    uow, _registro(email="otro@example.com", documento="DNI-30002"),
                    RONDAS_DE_TEST,
                )
        assert await _filas_de_registro(fabrica_de_sesiones) == (0, 0, 0, 0)


async def _sembrar_repuesto(fabrica, precio: str) -> tuple[int, int]:
    async with fabrica() as sesion:
        usuario = Usuario(
            email="admin@example.com", nombre="Administrador", password_hash="x" * 60,
            activo=True, debe_cambiar_password=False,
        )
        repuesto = Repuesto(codigo="BUJ-014", descripcion="Bujía", precio=Decimal(precio), stock=2)
        sesion.add_all([usuario, repuesto])
        await sesion.flush()
        sesion.add(AsignacionRol(usuario_id=usuario.id, rol="ADMIN", desde=datetime.now(UTC)))
        await sesion.commit()
        return usuario.id, repuesto.id


async def _leer_repuesto(fabrica, repuesto_id: int) -> Repuesto:
    async with fabrica() as sesion:
        repuesto = await sesion.get(Repuesto, repuesto_id)
        assert repuesto is not None
        return repuesto


class TestCambioDePrecioEnUnSoloBloque:
    """RN-20: precio nuevo + línea de historial, o ninguno."""

    async def test_el_cambio_exitoso_deja_precio_y_linea(self, fabrica_de_sesiones):
        usuario_id, repuesto_id = await _sembrar_repuesto(fabrica_de_sesiones, "100.00")
        async with fabrica_de_sesiones() as sesion:
            await actualizar_repuesto(
                UnitOfWorkRepuesto(sesion), repuesto_id,
                RepuestoActualizar(precio=Decimal("150.00")), usuario_id,
            )
        assert (await _leer_repuesto(fabrica_de_sesiones, repuesto_id)).precio == Decimal("150.00")
        assert await _contar(fabrica_de_sesiones, HistorialPrecio) == 1

    @pytest.mark.parametrize(
        ("precio_inicial", "cambio"),
        [
            ("100.00", {"precio": Decimal("150.00")}),
            ("80.50", {"precio": Decimal("99.99"), "descripcion": "Bujía iridio"}),
        ],
        ids=["solo-precio", "precio-y-descripcion"],
    )
    async def test_falla_al_escribir_el_historial_no_deja_el_precio_nuevo(
        self, fabrica_de_sesiones, monkeypatch, precio_inicial, cambio,
    ):
        usuario_id, repuesto_id = await _sembrar_repuesto(fabrica_de_sesiones, precio_inicial)
        async with fabrica_de_sesiones() as sesion:
            uow = UnitOfWorkRepuesto(sesion)

            async def falla(*_args, **_kwargs):
                raise RuntimeError("falla inyectada: historial")

            monkeypatch.setattr(uow.precios, "add_si_hubo_cambio", falla)
            with pytest.raises(RuntimeError, match="falla inyectada"):
                await actualizar_repuesto(
                    uow, repuesto_id, RepuestoActualizar(**cambio), usuario_id,
                )
        repuesto = await _leer_repuesto(fabrica_de_sesiones, repuesto_id)
        assert repuesto.precio == Decimal(precio_inicial)
        assert repuesto.descripcion == "Bujía"
        assert await _contar(fabrica_de_sesiones, HistorialPrecio) == 0
