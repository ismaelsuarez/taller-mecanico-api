"""Repositorios de autenticación: heredan flush, nunca confirman transacciones."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import QueryableAttribute, selectinload
from sqlmodel import col, select

from app.core.repository import BaseRepository
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    Usuario,
)


class UsuarioRepository(BaseRepository[Usuario]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, Usuario)

    async def get_por_id_con_roles(self, usuario_id: int) -> Usuario | None:
        # La PK es INTEGER: fuera de su rango no existe usuario, sin desbordar asyncpg.
        if not -(2**31) <= usuario_id < 2**31:
            return None
        resultado = await self.sesion.execute(
            select(Usuario).where(Usuario.id == usuario_id).options(
                selectinload(cast(QueryableAttribute[Any], Usuario.roles)),
            )
        )
        return resultado.scalar_one_or_none()

    async def get_por_email_con_roles(self, email: str) -> Usuario | None:
        resultado = await self.sesion.execute(
            select(Usuario).where(Usuario.email == email).options(
                selectinload(cast(QueryableAttribute[Any], Usuario.roles)),
            )
        )
        return resultado.scalar_one_or_none()

    async def get_roles_vigentes(self, usuario_id: int) -> list[str]:
        """D3: roles no revocados y sin vencer, consultados en cada petición (sin caché)."""
        if not -(2**31) <= usuario_id < 2**31:
            return []
        ahora = datetime.now(UTC)
        resultado = await self.sesion.execute(
            select(col(AsignacionRol.rol))
            .where(
                AsignacionRol.usuario_id == usuario_id,
                col(AsignacionRol.revocada_en).is_(None),
                or_(
                    col(AsignacionRol.vence_en).is_(None),
                    AsignacionRol.vence_en > ahora,
                ),
            )
            .order_by(col(AsignacionRol.rol))
        )
        return list(resultado.scalars().all())


class AsignacionRolRepository(BaseRepository[AsignacionRol]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, AsignacionRol)

    async def get_abierta(self, usuario_id: int, rol: str) -> AsignacionRol | None:
        """Asignación abierta (revocada_en IS NULL), aunque su vencimiento ya haya pasado."""
        if not -(2**31) <= usuario_id < 2**31:
            return None
        resultado = await self.sesion.execute(
            select(AsignacionRol).where(
                AsignacionRol.usuario_id == usuario_id,
                AsignacionRol.rol == rol,
                col(AsignacionRol.revocada_en).is_(None),
            )
        )
        return resultado.scalars().first()

    async def get_vigentes_de(self, usuario_id: int) -> list[AsignacionRol]:
        """Sólo las vigentes: no revocadas y sin vencer (RN-03, RN-04)."""
        if not -(2**31) <= usuario_id < 2**31:
            return []
        ahora = datetime.now(UTC)
        resultado = await self.sesion.execute(
            select(AsignacionRol).where(
                AsignacionRol.usuario_id == usuario_id,
                col(AsignacionRol.revocada_en).is_(None),
                or_(
                    col(AsignacionRol.vence_en).is_(None),
                    AsignacionRol.vence_en > ahora,
                ),
            ).order_by(col(AsignacionRol.rol))
        )
        return list(resultado.scalars().all())

    async def count_admins_vigentes(self) -> int:
        """Administradores vigentes; RN-05 exige que nunca bajen de uno."""
        ahora = datetime.now(UTC)
        resultado = await self.sesion.execute(
            select(func.count()).select_from(AsignacionRol).where(
                AsignacionRol.rol == "ADMIN",
                col(AsignacionRol.revocada_en).is_(None),
                or_(
                    col(AsignacionRol.vence_en).is_(None),
                    AsignacionRol.vence_en > ahora,
                ),
            )
        )
        return resultado.scalar_one()


class EventoSeguridadRepository(BaseRepository[EventoSeguridad]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, EventoSeguridad)

    async def get_pagina(self, page: int, size: int) -> tuple[list[EventoSeguridad], int]:
        """Listado paginado del historial de eventos, del más reciente al más viejo."""
        total = await self.count()
        resultado = await self.sesion.execute(
            select(EventoSeguridad)
            .order_by(col(EventoSeguridad.cuando).desc(), col(EventoSeguridad.id).desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(resultado.scalars().all()), total


@dataclass(frozen=True)
class VentanaIntentos:
    fallos: int
    fallo_mas_antiguo: datetime | None


class IntentoAccesoRepository(BaseRepository[IntentoAcceso]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, IntentoAcceso)

    async def consultar_ventana(
        self, email: str, ip: str, ahora: datetime,
    ) -> VentanaIntentos:
        """D3: fallos en (ahora - 60 s, ahora], posteriores al último éxito.

        Incluye los bloqueados guardados como exito=False; no borra historia.
        Devuelve datos primitivos para decidir >= 5 y calcular Retry-After.
        La lectura provoca autobegin: salir del UoW antes de esperar bcrypt.
        """
        inicio = ahora - timedelta(seconds=60)
        ultimo_exito = (
            select(func.max(IntentoAcceso.cuando))
            .where(
                IntentoAcceso.email == email,
                IntentoAcceso.ip == ip,
                col(IntentoAcceso.exito).is_(True),
                IntentoAcceso.cuando <= ahora,
            )
            .correlate(None)
            .scalar_subquery()
        )
        resultado = await self.sesion.execute(
            select(func.count(), func.min(IntentoAcceso.cuando)).where(
                IntentoAcceso.email == email,
                IntentoAcceso.ip == ip,
                col(IntentoAcceso.exito).is_(False),
                IntentoAcceso.cuando > inicio,
                IntentoAcceso.cuando <= ahora,
                IntentoAcceso.cuando > func.coalesce(ultimo_exito, inicio),
            )
        )
        fallos, mas_antiguo = resultado.one()
        return VentanaIntentos(fallos, mas_antiguo)
