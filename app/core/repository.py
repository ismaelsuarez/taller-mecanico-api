"""BaseRepository[T] y SoftDeleteRepository[T] (EJ-3, T-2; se completa en EJ-6).

RT-TX-01: `add` y `update` hacen `flush()`, nunca `commit()` — todo commit del
sistema pasa por un Unit of Work (B-1, DD-19). La clase del modelo va en el
constructor porque los genéricos se borran en runtime (6.4.3).
"""

from datetime import datetime, timezone
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

T = TypeVar("T", bound=SQLModel)


class BaseRepository(Generic[T]):
    """CRUD básico de una entidad; nada de esto confirma la transacción."""

    def __init__(self, sesion: AsyncSession, modelo: type[T]) -> None:
        self.sesion = sesion
        self.modelo = modelo

    async def get_by_id(self, id: int) -> T | None:
        return await self.sesion.get(self.modelo, id)

    async def get_all(self) -> list[T]:
        resultado = await self.sesion.execute(select(self.modelo))
        return list(resultado.scalars().all())

    async def count(self) -> int:
        resultado = await self.sesion.execute(
            select(func.count()).select_from(self.modelo)
        )
        return resultado.scalar_one()

    async def add(self, entidad: T) -> T:
        self.sesion.add(entidad)
        await self.sesion.flush()
        return entidad

    async def update(self, entidad: T) -> T:
        # La entidad viene de esta misma sesión: flush la persiste sin commit.
        self.sesion.add(entidad)
        await self.sesion.flush()
        return entidad

    async def delete(self, entidad: T) -> None:
        await self.sesion.delete(entidad)
        await self.sesion.flush()


class SoftDeleteRepository(BaseRepository[T]):
    """Entidades con borrado lógico (`borrado_en`, DD-03): lo vigente es lo no borrado."""

    columna_borrado = "borrado_en"

    def _vigente(self):
        return getattr(self.modelo, self.columna_borrado).is_(None)

    async def get_by_id(self, id: int) -> T | None:
        resultado = await self.sesion.execute(
            select(self.modelo).where(self.modelo.id == id, self._vigente())
        )
        return resultado.scalars().first()

    async def get_all(self) -> list[T]:
        resultado = await self.sesion.execute(
            select(self.modelo).where(self._vigente())
        )
        return list(resultado.scalars().all())

    async def count(self) -> int:
        resultado = await self.sesion.execute(
            select(func.count()).select_from(self.modelo).where(self._vigente())
        )
        return resultado.scalar_one()

    async def get_by_id_including_deleted(self, id: int) -> T | None:
        return await self.sesion.get(self.modelo, id)

    async def soft_delete(self, entidad: T) -> T:
        setattr(entidad, self.columna_borrado, datetime.now(timezone.utc))
        await self.sesion.flush()
        return entidad
