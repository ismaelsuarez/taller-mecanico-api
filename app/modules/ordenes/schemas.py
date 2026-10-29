"""Contratos del módulo ordenes: `/mis-ordenes` (EJ-5) y el catálogo de estados (EJ-6)."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
