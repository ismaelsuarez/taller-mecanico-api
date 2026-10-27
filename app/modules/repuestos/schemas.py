"""Contratos de entrada y salida del módulo repuestos (EJ-3).

Entrada separada de los modelos de tabla con `extra="forbid"` (RT-PG-01, S-4):
el stock no se edita por PATCH — el alta recibe `stock_inicial` y la reposición
`cantidad`, ambas pasan por el punto único de escritura (RN-14). Dinero siempre
`Decimal`, nunca `float` (S-1): positivo, finito y representable en NUMERIC(10,2)
sin redondeo; los ceros decimales finales no alteran su valor. Las cantidades
respetan el máximo INTEGER. Salidas sin `password_hash` (RT-PG-02).
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# INTEGER de PostgreSQL: existencias y movimientos positivos representables.
MAXIMO_STOCK = 2_147_483_647


class RepuestoCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(min_length=1, max_length=50)
    descripcion: str = Field(min_length=1, max_length=255)
    precio: Decimal = Field(
        gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False
    )
    stock_inicial: int = Field(default=0, ge=0, le=MAXIMO_STOCK)


class RepuestoActualizar(BaseModel):
    """PATCH: sólo descripción y/o precio; se aplican sólo los campos enviados (RT-PG-03)."""

    model_config = ConfigDict(extra="forbid")

    descripcion: str | None = Field(default=None, min_length=1, max_length=255)
    precio: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def _rechaza_nulos_explícitos(self) -> "RepuestoActualizar":
        """`{"precio": null}` no es un valor: se envía el campo con dato o no se envía (RN-18)."""
        for campo in ("descripcion", "precio"):
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(f"El campo {campo} no admite null.")
        return self


class RepuestoReponer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cantidad: int = Field(gt=0, le=MAXIMO_STOCK)
    motivo: str = Field(default="Reposición", min_length=1, max_length=120)


class RepuestoLectura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    codigo: str
    descripcion: str
    precio: Decimal
    stock: int


class MovimientoLectura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    repuesto_id: int
    orden_id: int | None
    usuario_id: int
    cantidad: int
    motivo: str
    cuando: datetime


class PrecioLectura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    repuesto_id: int
    usuario_id: int
    precio_anterior: Decimal
    precio_nuevo: Decimal
    cuando: datetime
