"""Contratos de autenticación (EJ-4); separados de los modelos de tabla."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

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
