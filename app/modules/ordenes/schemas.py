"""Contratos del módulo ordenes: `/mis-ordenes` (EJ-5) y el catálogo de estados (EJ-6)."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.core.paginacion import ParametrosPagina

# Máximo de un INTEGER de PostgreSQL: ids y cantidades se acotan acá para que ningún
# valor desmedido llegue a la base como un error interno (S-5).
ID_MAXIMO = 2_147_483_647


class OrdenResumenLectura(BaseModel):
    """Resumen de una orden propia para el listado `/mis-ordenes` (T-8)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    vehiculo_id: int
    estado: str
    falla: str
    creada_en: datetime
    mecanico_id: Optional[int]
    total: Decimal


class EstadoOrdenCodigo(StrEnum):
    """Códigos de estado que acepta la API (422 si no está acá). Igual al catálogo del seed (RN-19)."""

    PENDIENTE = "PENDIENTE"
    EN_REPARACION = "EN_REPARACION"
    TERMINADA = "TERMINADA"
    CANCELADA = "CANCELADA"


class EstadoOrdenLectura(BaseModel):
    """Una fila del catálogo `estado_orden` para `GET /estados-orden`."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    codigo: str
    descripcion: str
    posicion: int
    es_final: bool


class ParametrosOrdenes(ParametrosPagina):
    """Query params de `GET /ordenes`: paginación + filtro `estado` (DD-40, C-17).

    Con `Annotated[Modelo, Query()]` y `extra="forbid"`, todo query param es campo del modelo.
    """

    estado: EstadoOrdenCodigo | None = None


class ItemOrdenCrear(BaseModel):
    """Un ítem del alta: sólo el repuesto y la cantidad; el precio lo copia el servidor (RN-10)."""

    model_config = ConfigDict(extra="forbid")

    repuesto_id: int = Field(ge=1, le=ID_MAXIMO)
    cantidad: int = Field(ge=1, le=ID_MAXIMO)


class OrdenCrear(BaseModel):
    """Cuerpo de `POST /ordenes`: ni precio, ni total, ni estado, ni fecha (RN-10, SU-07)."""

    model_config = ConfigDict(extra="forbid")

    vehiculo_id: int = Field(ge=1, le=ID_MAXIMO)
    falla: str = Field(min_length=1, max_length=500)
    items: list[ItemOrdenCrear] = Field(min_length=1)

    @model_validator(mode="after")
    def _sin_repuestos_repetidos(self) -> "OrdenCrear":
        ids = [item.repuesto_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise PydanticCustomError("items_repetidos", "Hay repuestos repetidos en la orden.")
        return self


class ItemOrdenLectura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repuesto_id: int
    codigo: str
    descripcion: str
    cantidad: int
    precio_unitario: Decimal
    subtotal: Decimal


class HistorialLectura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desde_estado: Optional[str]
    hasta_estado: str
    usuario_id: int
    cuando: datetime


class OrdenDetalle(BaseModel):
    """Detalle con la forma del ejemplo de la consigna (D1): `cliente` es el nombre."""

    model_config = ConfigDict(extra="forbid")

    id: int
    estado: str
    patente: str
    total: Decimal
    creada_en: datetime
    mecanico_id: Optional[int]
    falla: str
    cliente: str
    items: list[ItemOrdenLectura]
    historial: list[HistorialLectura]
