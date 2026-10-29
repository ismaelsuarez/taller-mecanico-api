"""Verifica los repositorios y el Unit of Work mínimos del EJ-3 (T-2, RT-TX-01..03).

`BaseRepository[T]` y `SoftDeleteRepository[T]` hacen `flush()` y nunca `commit()`;
el `UnitOfWork` confirma al salir del bloque, revierte si sale con excepción y no
cierra la sesión. Contra la PostgreSQL real de test, con el esquema creado por
las migraciones de Alembic (regla A-3).
"""

import inspect

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.clientes.unit_of_work import UnitOfWorkCliente
from app.modules.repuestos.unit_of_work import UnitOfWorkRepuesto
from app.modules.usuarios.unit_of_work import UnitOfWorkIntentoAcceso, UnitOfWorkUsuario


@pytest.fixture
async def fabrica_de_sesiones(base_migrada):
    """Fábrica sobre el esquema real de Alembic, aislado por test."""
    yield async_sessionmaker(base_migrada, expire_on_commit=False)


async def _contar(sesion, modelo) -> int:
    resultado = await sesion.execute(select(func.count()).select_from(modelo))
    return resultado.scalar_one()


def _cliente(nombre: str = "Ana Pérez", documento: str = "DNI-10001") -> Cliente:
    return Cliente(nombre=nombre, documento=documento, telefono="11-5555-0001")


def _vehiculo(cliente_id: int, patente: str = "AA111BB") -> Vehiculo:
    return Vehiculo(cliente_id=cliente_id, patente=patente, marca="Fiat", modelo="Cronos", anio=2020)


class TestBaseRepository:
    async def test_add_hace_flush_y_no_commit(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            repo = BaseRepository(sesion, Cliente)
            cliente = _cliente()
            await repo.add(cliente)
            # flush: la PK ya está asignada dentro de la transacción…
            assert cliente.id is not None
            assert await _contar(sesion, Cliente) == 1
            # …pero no hubo commit: un rollback la deshace.
            await sesion.rollback()
        async with fabrica_de_sesiones() as sesion:
            assert await _contar(sesion, Cliente) == 0

    async def test_update_hace_flush_sin_commit(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            repo = BaseRepository(sesion, Cliente)
            cliente = _cliente()
            await repo.add(cliente)
            cliente.telefono = "11-9999-9999"
            await repo.update(cliente)
            assert await _contar(sesion, Cliente) == 1
            await sesion.rollback()
        async with fabrica_de_sesiones() as sesion:
            assert await _contar(sesion, Cliente) == 0

    async def test_get_by_id_devuelve_none_si_no_existe(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            repo = BaseRepository(sesion, Cliente)
            assert await repo.get_by_id(999999) is None

    async def test_get_by_id_devuelve_la_entidad(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            repo = BaseRepository(sesion, Cliente)
            cliente = _cliente()
            await repo.add(cliente)
            await sesion.commit()
            encontrado = await repo.get_by_id(cliente.id)
            assert encontrado is not None
            assert encontrado.documento == "DNI-10001"

    async def test_count_cuenta_todo(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            repo = BaseRepository(sesion, Cliente)
            await repo.add(_cliente())
            await repo.add(_cliente(documento="DNI-10002"))
            await sesion.commit()
            assert await repo.count() == 2

    async def test_delete_es_fisico_y_hace_flush(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            repo = BaseRepository(sesion, Cliente)
            cliente = _cliente()
            await repo.add(cliente)
            await sesion.commit()
            await repo.delete(cliente)
            assert await _contar(sesion, Cliente) == 0


class TestSoftDeleteRepository:
    async def _preparar(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            repo = SoftDeleteRepository(sesion, Vehiculo)
            cliente = _cliente()
            await repo.add(cliente)
            vigente = _vehiculo(cliente.id, patente="AA111BB")
            dado_de_baja = _vehiculo(cliente.id, patente="ZZ999YY")
            await repo.add(vigente)
            await repo.add(dado_de_baja)
            await sesion.commit()
            await repo.soft_delete(dado_de_baja)
            await sesion.commit()
            return vigente.id, dado_de_baja.id

    async def test_get_by_id_filtra_los_dados_de_baja(self, fabrica_de_sesiones):
        _, id_baja = await self._preparar(fabrica_de_sesiones)
        async with fabrica_de_sesiones() as sesion:
            repo = SoftDeleteRepository(sesion, Vehiculo)
            assert await repo.get_by_id(id_baja) is None

    async def test_get_by_id_including_deleted_lo_encuentra(self, fabrica_de_sesiones):
        _, id_baja = await self._preparar(fabrica_de_sesiones)
        async with fabrica_de_sesiones() as sesion:
            repo = SoftDeleteRepository(sesion, Vehiculo)
            encontrado = await repo.get_by_id_including_deleted(id_baja)
            assert encontrado is not None
            assert encontrado.borrado_en is not None

    async def test_soft_delete_pone_borrado_en(self, fabrica_de_sesiones):
        id_vigente, id_baja = await self._preparar(fabrica_de_sesiones)
        async with fabrica_de_sesiones() as sesion:
            repo = SoftDeleteRepository(sesion, Vehiculo)
            vigente = await repo.get_by_id(id_vigente)
            assert vigente is not None and vigente.borrado_en is None
            baja = await repo.get_by_id_including_deleted(id_baja)
            assert baja is not None and baja.borrado_en is not None

    async def test_count_y_get_all_sólo_vigentes(self, fabrica_de_sesiones):
        await self._preparar(fabrica_de_sesiones)
        async with fabrica_de_sesiones() as sesion:
            repo = SoftDeleteRepository(sesion, Vehiculo)
            assert await repo.count() == 1
            assert len(await repo.get_all()) == 1


class TestUnitOfWork:
    async def test_confirma_al_salir_del_bloque(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            uow = UnitOfWork(sesion)
            async with uow:
                repo = BaseRepository(sesion, Cliente)
                await repo.add(_cliente())
            # Confirmado: otra conexión lo ve.
        async with fabrica_de_sesiones() as sesion:
            assert await _contar(sesion, Cliente) == 1

    async def test_revuelve_con_excepcion_sin_confirmar(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            uow = UnitOfWork(sesion)
            with pytest.raises(RuntimeError, match="falla"):
                async with uow:
                    repo = BaseRepository(sesion, Cliente)
                    await repo.add(_cliente())
                    raise RuntimeError("falla a propósito")
        async with fabrica_de_sesiones() as sesion:
            assert await _contar(sesion, Cliente) == 0

    async def test_no_cierra_la_sesion(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            uow = UnitOfWork(sesion)
            async with uow:
                pass
            # La sesión sigue usable: el UoW no la cerró (RT-TX-03, B-3).
            resultado = await sesion.execute(text("SELECT 1"))
            assert resultado.scalar_one() == 1

    async def test_uow_de_clientes_compone_sus_repositorios(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            uow = UnitOfWorkCliente(sesion)
            assert uow.clientes.sesion is sesion
            assert uow.vehiculos.sesion is sesion
            async with uow:
                cliente = _cliente()
                await uow.clientes.add(cliente)
                await uow.vehiculos.add(_vehiculo(cliente.id))
        async with fabrica_de_sesiones() as sesion:
            assert await _contar(sesion, Cliente) == 1
            assert await _contar(sesion, Vehiculo) == 1

    async def test_uow_de_repuestos_compone_sus_repositorios(self, fabrica_de_sesiones):
        async with fabrica_de_sesiones() as sesion:
            uow = UnitOfWorkRepuesto(sesion)
            assert uow.repuestos.sesion is sesion
            assert uow.movimientos.sesion is sesion
            assert uow.precios.sesion is sesion


class TestCommitFallido:
    """La confirmación puede fallar: el UoW base revierte, propaga y no cierra (D4, RT-TX-03)."""

    @pytest.mark.parametrize(
        "clase_uow",
        [
            UnitOfWork,
            UnitOfWorkCliente,
            UnitOfWorkRepuesto,
            UnitOfWorkUsuario,
            UnitOfWorkIntentoAcceso,
        ],
    )
    @pytest.mark.parametrize(
        "error",
        [
            RuntimeError("commit roto"),
            OperationalError("COMMIT", {}, Exception("conexión caída")),
        ],
        ids=["error-generico", "error-de-base"],
    )
    async def test_revierte_propaga_y_no_cierra_la_sesion(
        self, fabrica_de_sesiones, monkeypatch, clase_uow, error,
    ):
        async with fabrica_de_sesiones() as sesion:
            cerrada = False
            cerrar_real = sesion.close

            async def cerrar():
                nonlocal cerrada
                cerrada = True
                await cerrar_real()

            async def commit_que_falla():
                raise error

            monkeypatch.setattr(sesion, "commit", commit_que_falla)
            monkeypatch.setattr(sesion, "close", cerrar)
            with pytest.raises(type(error)):
                async with clase_uow(sesion):
                    await BaseRepository(sesion, Cliente).add(_cliente())
                    assert await _contar(sesion, Cliente) == 1  # flush hecho, sin confirmar
            # Revertido: la transacción abierta por el flush ya no existe y la sesión sigue usable.
            assert not sesion.in_transaction()
            assert not cerrada
            assert (await sesion.execute(text("SELECT 1"))).scalar_one() == 1
        async with fabrica_de_sesiones() as sesion:
            assert await _contar(sesion, Cliente) == 0


class TestJerarquiaAuditada:
    """Auditoría contra el Ejercicio 6: dos clases, modelo en el constructor, flush sin commit."""

    SEIS_METODOS = ("get_by_id", "get_all", "count", "add", "update", "delete")
    SOLO_BORRADO_LOGICO = ("get_by_id_including_deleted", "soft_delete")

    @pytest.mark.parametrize("clase", [BaseRepository, SoftDeleteRepository])
    def test_el_constructor_recibe_la_sesion_y_la_clase_del_modelo(self, clase):
        assert list(inspect.signature(clase.__init__).parameters) == ["self", "sesion", "modelo"]

    @pytest.mark.parametrize("clase", [BaseRepository, SoftDeleteRepository])
    def test_ofrece_los_seis_metodos_asincronicos(self, clase):
        for nombre in self.SEIS_METODOS:
            assert inspect.iscoroutinefunction(getattr(clase, nombre)), nombre

    def test_la_base_no_tiene_borrado_logico(self):
        for nombre in self.SOLO_BORRADO_LOGICO:
            assert not hasattr(BaseRepository, nombre), nombre

    def test_el_borrado_logico_vive_solo_en_la_subclase(self):
        assert issubclass(SoftDeleteRepository, BaseRepository)
        for nombre in self.SOLO_BORRADO_LOGICO:
            assert nombre in vars(SoftDeleteRepository), nombre

    @pytest.mark.parametrize("modelo", [Cliente, Vehiculo], ids=["cliente", "vehiculo"])
    async def test_add_asigna_id_con_flush_y_desaparece_al_revertir(
        self, fabrica_de_sesiones, modelo,
    ):
        async with fabrica_de_sesiones() as sesion:
            dueno = _cliente()
            await BaseRepository(sesion, Cliente).add(dueno)
            entidad = dueno
            if modelo is Vehiculo:
                entidad = _vehiculo(dueno.id)
                await BaseRepository(sesion, Vehiculo).add(entidad)
            assert entidad.id is not None
            await sesion.rollback()
        async with fabrica_de_sesiones() as sesion:
            assert await _contar(sesion, modelo) == 0
