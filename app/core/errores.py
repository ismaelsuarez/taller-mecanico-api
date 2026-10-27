"""Errores de dominio (404/409) y validación de peticiones (422).

El dominio conserva sus mensajes propios. La validación se traduce sin devolver
entrada, ubicaciones técnicas ni texto interno del validador (RN-18, S-9).
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class MensajeValidacion(BaseModel):
    """Mensaje público, sin ubicación técnica ni entrada original."""

    model_config = ConfigDict(extra="forbid")

    msg: str


class RespuestaValidacion(BaseModel):
    """Contrato 422: mensajes de validación o detalle textual de paginación."""

    model_config = ConfigDict(extra="forbid")

    detail: list[MensajeValidacion] | str


class ErrorDeDominio(Exception):
    """Base de las excepciones de negocio que la aplicación traduce a HTTP."""


class NoEncontrado(ErrorDeDominio):
    """Recurso inexistente o ya dado de baja → 404."""


class EnConflicto(ErrorDeDominio):
    """La operación choca con una regla de unicidad o de negocio → 409."""


def _respuesta_de_dominio(error: ErrorDeDominio) -> JSONResponse:
    codigo = 404 if isinstance(error, NoEncontrado) else 409
    return JSONResponse(status_code=codigo, content={"detail": str(error)})


_CAMPOS_VISIBLES = {
    "nombre": "el nombre",
    "documento": "el documento",
    "telefono": "el teléfono",
    "patente": "la patente",
    "marca": "la marca",
    "modelo": "el modelo",
    "anio": "el año",
    "codigo": "el código del repuesto",
    "descripcion": "la descripción",
    "precio": "el precio",
    "stock_inicial": "la cantidad inicial",
    "cantidad": "la cantidad",
    "motivo": "el motivo",
    "page": "la página",
    "size": "la cantidad por página",
    "cliente_id": "el cliente seleccionado",
    "vehiculo_id": "el vehículo seleccionado",
    "repuesto_id": "el repuesto seleccionado",
}
_MENSAJE_GENERICO = "Revisá los datos enviados: hay un valor no válido."


def _mensaje_validacion(error: dict) -> str:
    """Sólo usa categorías y etiquetas conocidas; ignora input, msg y ctx."""
    tipo = error.get("type")
    ubicacion = error.get("loc", ())
    if tipo == "json_invalid":
        return "No pudimos leer los datos enviados. Revisá el formato y volvé a intentar."
    if tipo == "extra_forbidden":
        return "Enviá sólo los datos permitidos para esta operación."
    if tipo == "missing" and ubicacion == ("body",):
        return "Completá los datos de la solicitud."

    campo = _CAMPOS_VISIBLES.get(ubicacion[-1]) if len(ubicacion) == 2 else None
    if campo is None:
        return _MENSAJE_GENERICO
    if tipo == "missing":
        return f"Completá {campo}."
    if tipo == "string_type":
        return f"Ingresá texto para {campo}."
    if tipo in ("int_type", "int_parsing", "int_from_float"):
        return f"Ingresá un número entero para {campo}."
    if tipo == "string_too_short":
        return f"Completá {campo} con un texto más largo."
    if tipo == "string_too_long":
        return f"Usá un texto más corto para {campo}."
    if tipo in ("greater_than", "greater_than_equal", "less_than", "less_than_equal"):
        return f"Revisá {campo}: está fuera del rango permitido."
    if tipo in ("decimal_type", "decimal_parsing", "finite_number"):
        return f"Ingresá un importe válido para {campo}."
    if tipo in ("decimal_max_digits", "decimal_max_places", "decimal_whole_digits"):
        return f"Revisá {campo}: el importe tiene demasiados dígitos o decimales."
    return _MENSAJE_GENERICO


def registrar_traductores(app: FastAPI) -> None:
    """Registra los traductores de dominio y de validación de las peticiones."""

    @app.exception_handler(RequestValidationError)
    async def _traducir_validacion(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": [{"msg": _mensaje_validacion(fallo)} for fallo in error.errors()]
            },
        )

    @app.exception_handler(NoEncontrado)
    async def _traducir_no_encontrado(request: Request, error: NoEncontrado) -> JSONResponse:
        return _respuesta_de_dominio(error)

    @app.exception_handler(EnConflicto)
    async def _traducir_en_conflicto(request: Request, error: EnConflicto) -> JSONResponse:
        return _respuesta_de_dominio(error)
