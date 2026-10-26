"""Modelos de tabla, restricciones y relaciones del módulo ordenes (EJ-2).

`estado_orden` es un catálogo con PK `codigo` (no `id`) — DD-02; `orden_trabajo.estado`
es FK a ese catálogo, no un CHECK con la lista (RN-19). El catálogo lo carga `seed.py`.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.modules.clientes.models import Vehiculo
    from app.modules.repuestos.models import Repuesto
    from app.modules.usuarios.models import Usuario


class EstadoOrden(SQLModel, table=True):
    """Catálogo de estados de una orden de trabajo. Se consulta desde la API y no se
    edita desde ella (A-5, RN-19). Repositorio de sólo lectura (no hereda de BaseRepository).
    """

    __tablename__ = "estado_orden"

    # PK string: así `orden_trabajo.estado` se lee igual en psql que en la API (DD-02).
    codigo: str = Field(primary_key=True, sa_type=Text, max_length=30)
    descripcion: str = Field(sa_type=Text, max_length=100)
    posicion: int = Field(unique=True)
    # Decide qué es una orden abierta: RN-16 (baja de vehículo) depende de esto.
    es_final: bool = Field(sa_type=Boolean)


class OrdenTrabajo(SQLModel, table=True):
    """Orden de trabajo de un vehículo; nace PENDIENTE con al menos un ítem (RN-10)."""

    __tablename__ = "orden_trabajo"
    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_orden_trabajo_total_no_negativo"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    vehiculo_id: int = Field(foreign_key="vehiculo.id", sa_column_kwargs={"index": True})
    # Se asigna al iniciar (RN-11); nulo mientras está PENDIENTE.
    mecanico_id: Optional[int] = Field(
        default=None, foreign_key="usuario.id", sa_column_kwargs={"index": True}
    )
    # FK al catálogo, no CHECK con la lista (RN-19).
    estado: str = Field(foreign_key="estado_orden.codigo", sa_type=Text, max_length=30, index=True)
    falla: str = Field(sa_type=Text, max_length=500)
    creada_en: datetime = Field(sa_type=DateTime(timezone=True))
    # Lo calcula el servidor (RN-10); nunca viaja en el cuerpo del alta.
    total: Decimal = Field(sa_type=Numeric(12, 2))

    vehiculo: Optional["Vehiculo"] = Relationship(back_populates="ordenes")
    mecanico: Optional["Usuario"] = Relationship()
    items: list["ItemOrden"] = Relationship(
        back_populates="orden", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    historial_estados: list["HistorialEstadoOrden"] = Relationship(
        back_populates="orden", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class ItemOrden(SQLModel, table=True):
    """Ítem de una orden: un repuesto con su cantidad y precio copiado al alta (RN-10)."""

    __tablename__ = "item_orden"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_item_orden_cantidad_positiva"),
        CheckConstraint("precio_unitario > 0", name="ck_item_orden_precio_positivo"),
        # Un repuesto no se repite dentro de la misma orden (RN-10).
        UniqueConstraint("orden_id", "repuesto_id", name="uq_item_orden_repuesto_por_orden"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    orden_id: int = Field(foreign_key="orden_trabajo.id", sa_column_kwargs={"index": True})
    repuesto_id: int = Field(foreign_key="repuesto.id", sa_column_kwargs={"index": True})
    cantidad: int
    precio_unitario: Decimal = Field(sa_type=Numeric(10, 2))

    orden: Optional[OrdenTrabajo] = Relationship(back_populates="items")
    repuesto: Optional["Repuesto"] = Relationship(back_populates="items_orden")


class HistorialEstadoOrden(SQLModel, table=True):
    """Línea de historial de cambio de estado de una orden («append-only») — RN-15.

    `desde_estado` es nulo en la primera línea (alta de la orden).
    """

    __tablename__ = "historial_estado_orden"

    id: Optional[int] = Field(default=None, primary_key=True)
    orden_id: int = Field(foreign_key="orden_trabajo.id", sa_column_kwargs={"index": True})
    desde_estado: Optional[str] = Field(
        default=None, foreign_key="estado_orden.codigo", sa_type=Text, max_length=30, index=True
    )
    hasta_estado: str = Field(foreign_key="estado_orden.codigo", sa_type=Text, max_length=30, index=True)
    usuario_id: int = Field(foreign_key="usuario.id", sa_column_kwargs={"index": True})
    cuando: datetime = Field(sa_type=DateTime(timezone=True))

    orden: Optional[OrdenTrabajo] = Relationship(back_populates="historial_estados")
