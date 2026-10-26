"""Modelos de tabla, restricciones y relaciones del módulo clientes (EJ-2).

Vehiculo usa borrado lógico (`borrado_en`) con índice único parcial de patente (DD-03):
un auto vendido no impide registrar otro con la misma patente.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, DateTime, Index, Text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.ordenes.models import OrdenTrabajo
    from app.modules.usuarios.models import Usuario


class Cliente(SQLModel, table=True):
    """Ficha de cliente del taller; opcionalmente vinculada a un usuario (uno a uno)."""

    __tablename__ = "cliente"

    id: Optional[int] = Field(default=None, primary_key=True)
    # UNIQUE: uno a uno opcional con usuario; nulo si el cliente no tiene cuenta.
    usuario_id: Optional[int] = Field(
        default=None, foreign_key="usuario.id", unique=True, index=True
    )
    nombre: str = Field(sa_type=Text, max_length=255)
    documento: str = Field(sa_type=Text, unique=True, max_length=50)
    telefono: str = Field(sa_type=Text, max_length=50)

    usuario: Optional["Usuario"] = Relationship(
        back_populates="cliente",
        sa_relationship_kwargs={"foreign_keys": "[Cliente.usuario_id]"},
    )
    vehiculos: list["Vehiculo"] = Relationship(back_populates="cliente")


class Vehiculo(SQLModel, table=True):
    """Auto de un cliente. Patente única entre los vigentes (índice parcial, DD-03)."""

    __tablename__ = "vehiculo"
    __table_args__ = (
        CheckConstraint("anio BETWEEN 1950 AND 2100", name="ck_vehiculo_anio"),
        Index(
            "uq_vehiculo_patente_vigente",
            "patente",
            unique=True,
            postgresql_where="borrado_en IS NULL",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    cliente_id: int = Field(foreign_key="cliente.id", sa_column_kwargs={"index": True})
    patente: str = Field(sa_type=Text, max_length=20)
    marca: str = Field(sa_type=Text, max_length=100)
    modelo: str = Field(sa_type=Text, max_length=100)
    anio: int
    borrado_en: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))

    cliente: Optional[Cliente] = Relationship(back_populates="vehiculos")
    ordenes: list["OrdenTrabajo"] = Relationship(back_populates="vehiculo")
