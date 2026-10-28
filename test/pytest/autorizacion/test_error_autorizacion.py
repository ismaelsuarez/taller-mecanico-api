"""403 de autorización con mensaje humano y regresión de los traductores compartidos (riesgo item 3)."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errores import EnConflicto, NoAutorizado, NoEncontrado, registrar_traductores


def _aplicacion_de_prueba() -> FastAPI:
    app = FastAPI()
    registrar_traductores(app)

    @app.get("/sin-permiso")
    async def sin_permiso():
        raise NoAutorizado()

    @app.get("/sin-permiso-dedicado")
    async def sin_permiso_dedicado():
        raise NoAutorizado("No podés revocar tu propio rol de administrador.")

    @app.get("/recurso-inexistente")
    async def recurso_inexistente():
        raise NoEncontrado("No existe ese recurso.")

    @app.get("/conflicto")
    async def conflicto():
        raise EnConflicto("Ya existe un usuario con ese correo.")

    return app


async def _consultar(ruta: str) -> tuple[int, dict]:
    app = _aplicacion_de_prueba()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cliente:
        respuesta = await cliente.get(ruta)
    return respuesta.status_code, respuesta.json()


async def test_403_responde_mensaje_humano_por_defecto():
    codigo, cuerpo = await _consultar("/sin-permiso")
    assert codigo == 403
    assert cuerpo == {"detail": "No tenés permiso para realizar esta acción."}


async def test_403_acepta_mensaje_propio_y_no_expone_internos():
    codigo, cuerpo = await _consultar("/sin-permiso-dedicado")
    assert codigo == 403
    assert cuerpo == {"detail": "No podés revocar tu propio rol de administrador."}
    assert "Traceback" not in str(cuerpo)


async def test_regresion_404_y_409_conservan_sus_mensajes():
    codigo, cuerpo = await _consultar("/recurso-inexistente")
    assert (codigo, cuerpo) == (404, {"detail": "No existe ese recurso."})
    codigo, cuerpo = await _consultar("/conflicto")
    assert (codigo, cuerpo) == (409, {"detail": "Ya existe un usuario con ese correo."})
