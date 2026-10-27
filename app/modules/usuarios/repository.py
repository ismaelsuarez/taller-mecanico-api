"""Repositorios de autenticación: heredan flush, nunca confirman transacciones."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import func
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

    async def get_por_email_con_roles(self, email: str) -> Usuario | None:
        resultado = await self.sesion.execute(
            select(Usuario).where(Usuario.email == email).options(
                selectinload(cast(QueryableAttribute[Any], Usuario.roles)),
            )
        )
        return resultado.scalar_one_or_none()


class AsignacionRolRepository(BaseRepository[AsignacionRol]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, AsignacionRol)


class EventoSeguridadRepository(BaseRepository[EventoSeguridad]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, EventoSeguridad)


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
