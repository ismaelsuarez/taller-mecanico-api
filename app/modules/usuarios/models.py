"""Modelos de tabla, restricciones y relaciones del módulo usuarios (EJ-2).

Usuario no tiene columna `rol` (DD-01): los roles son filas vigentes de `asignacion_rol`.
Revocar un rol escribe `revocada_en`; la fila nunca se borra.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.clientes.models import Cliente


class Usuario(SQLModel, table=True):
    """Persona del sistema (personal o cliente con cuenta)."""

    __tablename__ = "usuario"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(sa_type=Text, unique=True, index=True, max_length=255)
    nombre: str = Field(sa_type=Text, max_length=255)
    password_hash: str = Field(sa_type=Text, max_length=255)
    activo: bool = Field(default=True, sa_type=Boolean)
    debe_cambiar_password: bool = Field(default=False, sa_type=Boolean)
    password_cambiada_en: Optional[datetime] = Field(
        default=None, sa_type=DateTime(timezone=True)
    )

    roles: list["AsignacionRol"] = Relationship(
        back_populates="usuario",
        sa_relationship_kwargs={"foreign_keys": "[AsignacionRol.usuario_id]"},
    )
    # Uno a uno opcional: un usuario puede no tener ficha de cliente.
    cliente: Optional["Cliente"] = Relationship(
        back_populates="usuario",
        sa_relationship_kwargs={"foreign_keys": "[Cliente.usuario_id]"},
    )


class AsignacionRol(SQLModel, table=True):
    """Historial de roles de un usuario. Una asignación abierta por (usuario, rol) — RN-03."""

    __tablename__ = "asignacion_rol"
    __table_args__ = (
        CheckConstraint(
            "rol IN ('ADMIN', 'RECEPCION', 'MECANICO', 'CLIENTE')",
            name="ck_asignacion_rol_rol_valido",
        ),
        Index(
            "uq_asignacion_rol_abierta",
            "usuario_id",
            "rol",
            unique=True,
            postgresql_where="revocada_en IS NULL",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", sa_column_kwargs={"index": True})
    rol: str = Field(sa_type=Text, max_length=20)
    desde: datetime = Field(sa_type=DateTime(timezone=True))
    vence_en: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    revocada_en: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    # Suposición SU-02: FK a usuario; nulo para asignaciones del seed/registro.
    otorgada_por: Optional[int] = Field(
        default=None, foreign_key="usuario.id", sa_column_kwargs={"index": True}
    )

    usuario: Optional[Usuario] = Relationship(
        back_populates="roles",
        sa_relationship_kwargs={"foreign_keys": "[AsignacionRol.usuario_id]"},
    )


class IntentoAcceso(SQLModel, table=True):
    """Registro de cada intento de login (correcto o fallido) — RN-08.

    Se escribe desde una sesión y transacción propias (T-7, DD-19); ese detalle vive en el
    servicio (EJ-4), no en el modelo.
    """

    __tablename__ = "intento_acceso"
    __table_args__ = (
        Index("ix_intento_acceso_correo_ip_cuando", "email", "ip", "cuando"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    cuando: datetime = Field(sa_type=DateTime(timezone=True))
    email: str = Field(sa_type=Text, max_length=255)
    ip: str = Field(sa_type=Text, max_length=64)
    exito: bool = Field(sa_type=Boolean)


class EventoSeguridad(SQLModel, table=True):
    """Evento de seguridad: altas, roles, cambios de contraseña, datos iniciales — DD-26.

    `actor` es texto (correo del usuario o `SISTEMA`), no una FK.
    """

    __tablename__ = "evento_seguridad"

    id: Optional[int] = Field(default=None, primary_key=True)
    cuando: datetime = Field(sa_type=DateTime(timezone=True))
    actor: str = Field(sa_type=Text, max_length=255)
    accion: str = Field(sa_type=Text, max_length=255)
