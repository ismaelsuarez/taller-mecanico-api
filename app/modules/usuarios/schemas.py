"""Contratos de autenticación (EJ-4) y administración de roles (EJ-5); separados de los modelos de tabla."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.modules.clientes.schemas import ClienteCrear


def validar_longitud_password(valor: str) -> str:
    """bcrypt limita bytes, no caracteres; el mensaje nunca copia la contraseña."""
    if len(valor.encode("utf-8")) > 72:
        raise ValueError("La contraseña es demasiado larga.")
    return valor


ClaveBcrypt = Annotated[
    str,
    AfterValidator(validar_longitud_password),
    Field(description="Como máximo 72 bytes UTF-8, no 72 caracteres."),
]


class RegistroEntrada(ClienteCrear):
    """Registro plano: la ficha conserva los límites del contrato de clientes."""

    email: str = Field(min_length=1, max_length=255)
    password: ClaveBcrypt


class LoginEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=255)
    password: ClaveBcrypt


class CambioPasswordEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password_actual: ClaveBcrypt
    password_nueva: ClaveBcrypt


class MensajeLectura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mensaje: str


class SesionLectura(MensajeLectura):
    """Registro, login y cambio: el token sólo viajará en la cookie."""

    debe_cambiar_password: bool
    expira_en_segundos: int


class UsuarioLectura(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    email: str
    nombre: str
    debe_cambiar_password: bool


class IdentidadLectura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario: UsuarioLectura
    roles_vigentes: list[str]
    roles_token: list[str]


RolPersonal = Literal["ADMIN", "RECEPCION", "MECANICO"]
RolAsignable = Literal["ADMIN", "RECEPCION", "MECANICO", "CLIENTE"]


class AltaPersonalEntrada(BaseModel):
    """Alta de personal (POST /usuarios): CLIENTE queda fuera — DD-18."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=255)
    nombre: str = Field(min_length=1, max_length=255)
    password_provisoria: ClaveBcrypt
    rol: RolPersonal


class AsignacionRolEntrada(BaseModel):
    """Asignación de rol (POST /usuarios/{id}/roles): CLIENTE incluido (D1)."""

    model_config = ConfigDict(extra="forbid")

    rol: RolAsignable
    vence_en: datetime | None = None

    @field_validator("vence_en")
    @classmethod
    def vencimiento_con_zona_y_futuro(cls, valor: datetime | None) -> datetime | None:
        if valor is None:
            return None
        if valor.tzinfo is None:
            raise ValueError("La fecha de vencimiento debe incluir la zona horaria.")
        if valor <= datetime.now(UTC):
            raise ValueError("La fecha de vencimiento debe ser posterior al instante actual.")
        return valor


class RolAsignadoLectura(BaseModel):
    """Asignación vigente: sin revocadas ni vencidas, sin datos de contraseña."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    rol: str
    desde: datetime
    vence_en: datetime | None
    otorgada_por: int | None


class RolesAsignadosLectura(BaseModel):
    """Listado de roles vigentes de un usuario, sin paginación (D1)."""

    model_config = ConfigDict(extra="forbid")

    items: list[RolAsignadoLectura]


class EventoLectura(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    cuando: datetime
    actor: str
    accion: str
