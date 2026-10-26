"""Excepciones de dominio y sus traductores a HTTP (EJ-3, D8).

El servicio las lanza sin conocer FastAPI; la aplicación las registra como
exception handlers y devuelve 404/409 con el mensaje propio en español
(RN-18, S-9). Nunca se filtra texto interno de la base.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ErrorDeDominio(Exception):
    """Base de las excepciones de negocio que la aplicación traduce a HTTP."""


class NoEncontrado(ErrorDeDominio):
    """Recurso inexistente o ya dado de baja → 404."""


class EnConflicto(ErrorDeDominio):
    """La operación choca con una regla de unicidad o de negocio → 409."""


def _respuesta_de_dominio(error: ErrorDeDominio) -> JSONResponse:
    codigo = 404 if isinstance(error, NoEncontrado) else 409
    return JSONResponse(status_code=codigo, content={"detail": str(error)})


def registrar_traductores(app: FastAPI) -> None:
    """Registra los handlers que convierten excepciones de dominio en respuestas HTTP."""

    async def _traducir_no_encontrado(request: Request, error: NoEncontrado) -> JSONResponse:
        return _respuesta_de_dominio(error)

    async def _traducir_en_conflicto(request: Request, error: EnConflicto) -> JSONResponse:
        return _respuesta_de_dominio(error)

    app.add_exception_handler(NoEncontrado, _traducir_no_encontrado)
    app.add_exception_handler(EnConflicto, _traducir_en_conflicto)
