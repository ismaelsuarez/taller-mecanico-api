"""Modelos de tabla, restricciones y relaciones del módulo repuestos (EJ-2).

El stock sólo cambia a través de `movimiento_stock` (RN-14). Código único entre
vigentes (índice parcial, DD-03). Dinero siempre NUMERIC/Decimal, nunca float (S-1).
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Numeric, Text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.ordenes.models import ItemOrden


class Repuesto(SQLModel, table=True):
    """Repuesto del catálogo del taller; borrado lógico."""

    __tablename__ = "repuesto"
    __table_args__ = (
        CheckConstraint("precio > 0", name="ck_repuesto_precio_positivo"),
        CheckConstraint("stock >= 0", name="ck_repuesto_stock_no_negativo"),
        Index(
            "uq_repuesto_codigo_vigente",
            "codigo",
            unique=True,
            postgresql_where="borrado_en IS NULL",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(sa_type=Text, max_length=50)
    descripcion: str = Field(sa_type=Text, max_length=255)
    precio: Decimal = Field(sa_type=Numeric(10, 2))
    stock: int = Field(default=0)
    borrado_en: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))

    movimientos: list["MovimientoStock"] = Relationship(back_populates="repuesto")
    historial_precios: list["HistorialPrecio"] = Relationship(back_populates="repuesto")
    items_orden: list["ItemOrden"] = Relationship(back_populates="repuesto")


class MovimientoStock(SQLModel, table=True):
    """Movimiento de stock («append-only»): alta, reposición o salida por orden — RN-14.

    `cantidad > 0` suman, `cantidad < 0` restan (salidas por orden, SU-08); CHECK `<> 0`.
    """

    __tablename__ = "movimiento_stock"
    __table_args__ = (
        CheckConstraint("cantidad <> 0", name="ck_movimiento_stock_cantidad_no_cero"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    repuesto_id: int = Field(foreign_key="repuesto.id", sa_column_kwargs={"index": True})
    # Nulo fuera del contexto de una orden (p. ej. stock inicial, reposición).
    orden_id: Optional[int] = Field(
        default=None, foreign_key="orden_trabajo.id", sa_column_kwargs={"index": True}
    )
    usuario_id: int = Field(foreign_key="usuario.id", sa_column_kwargs={"index": True})
    cantidad: int
    motivo: str = Field(sa_type=Text, max_length=120)
    cuando: datetime = Field(sa_type=DateTime(timezone=True))

    repuesto: Optional[Repuesto] = Relationship(back_populates="movimientos")


class HistorialPrecio(SQLModel, table=True):
    """Línea de historial de precio de un repuesto («append-only») — RN-20.

    La tabla se llama `historial_precio_repuesto` (IN-02); la clase, `HistorialPrecio`.
    """

    __tablename__ = "historial_precio_repuesto"
    __table_args__ = (
        CheckConstraint("precio_nuevo > 0", name="ck_historial_precio_nuevo_positivo"),
        CheckConstraint(
            "precio_nuevo <> precio_anterior",
            name="ck_historial_precio_cambio_real",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    repuesto_id: int = Field(foreign_key="repuesto.id", sa_column_kwargs={"index": True})
    usuario_id: int = Field(foreign_key="usuario.id", sa_column_kwargs={"index": True})
    precio_anterior: Decimal = Field(sa_type=Numeric(10, 2))
    precio_nuevo: Decimal = Field(sa_type=Numeric(10, 2))
    cuando: datetime = Field(sa_type=DateTime(timezone=True))

    repuesto: Optional[Repuesto] = Relationship(back_populates="historial_precios")
