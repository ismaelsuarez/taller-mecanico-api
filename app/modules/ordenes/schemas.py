"""Contratos de salida mínimos para `/mis-ordenes` (EJ-5); EJ-6 completa el módulo."""

from datetime import datetime
from decimal import Decimal
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
