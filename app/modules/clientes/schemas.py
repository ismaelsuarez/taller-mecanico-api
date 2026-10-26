"""Contratos de entrada y salida del módulo clientes (Cliente, Vehiculo) — EJ-3.

Entrada separada de los modelos de tabla con `extra="forbid"` (RT-PG-01, S-4):
nadie puede mandar `id`, `usuario_id` ni `borrado_en` en el cuerpo. Salidas sin
`password_hash` (RT-PG-02). El `id` del cliente de un vehículo viene de la ruta,
no del cuerpo.
"""

from pydantic import BaseModel, ConfigDict, Field


class ClienteCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=255)
    documento: str = Field(min_length=1, max_length=50)
    telefono: str = Field(min_length=1, max_length=50)


class VehiculoCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patente: str = Field(min_length=1, max_length=20)
    marca: str = Field(min_length=1, max_length=100)
    modelo: str = Field(min_length=1, max_length=100)
    anio: int = Field(ge=1950, le=2100)


class VehiculoLectura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    cliente_id: int
    patente: str
    marca: str
    modelo: str
    anio: int


class ClienteLectura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    nombre: str
    documento: str
    telefono: str


class ClienteDetalle(ClienteLectura):
    """Cliente con sus vehículos vigentes (precargados — T-10)."""

    vehiculos: list[VehiculoLectura] = Field(default_factory=list)
