"""Fallo inyectado en el límite de confirmación; la base y sus flush son reales."""

from sqlalchemy import func
from sqlmodel import select

from app.core.errores import EnConflicto
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, Usuario
from app.modules.usuarios.router import construir_uow
from app.modules.usuarios.unit_of_work import UnitOfWorkUsuario

from .test_registro import api_auth as api_auth
from .test_registro import datos_registro as datos_registro
from .test_registro import estado_guardado


async def test_commit_fallido_revierte_sin_cerrar_sesion_ni_emitir_cookie(
    api_auth, aplicacion_auth, datos_registro, monkeypatch,
):
    app = aplicacion_auth
    antes = await estado_guardado(app)
    async with app.state.fabrica_sesiones() as sesion:
        uow = UnitOfWorkUsuario(sesion)
        for repo in (uow.usuarios, uow.roles, uow.clientes, uow.eventos):
            assert repo.sesion is sesion
        llego_al_commit = False
        cerrada = False
        cerrar_real = sesion.close

        async def cerrar():
            nonlocal cerrada
            cerrada = True
            await cerrar_real()

        async def fallar_commit():
            nonlocal llego_al_commit
            llego_al_commit = True
            for modelo in (Usuario, AsignacionRol, Cliente, EventoSeguridad):
                assert await sesion.scalar(select(func.count()).select_from(modelo)) == 1
            assert await estado_guardado(app) == antes  # Los repositorios sólo hicieron flush.
            raise EnConflicto("No pudimos completar el registro. Volvé a intentar.")

        monkeypatch.setattr(sesion, "commit", fallar_commit)
        monkeypatch.setattr(sesion, "close", cerrar)
        app.dependency_overrides[construir_uow] = lambda: uow
        try:
            respuesta = await api_auth.post("/auth/registro", json=datos_registro)
            assert respuesta.status_code == 409
            assert respuesta.json() == {
                "detail": "No pudimos completar el registro. Volvé a intentar.",
            }
            assert "set-cookie" not in respuesta.headers and llego_al_commit
            assert not sesion.in_transaction() and not cerrada
            assert await estado_guardado(app) == antes
        finally:
            app.dependency_overrides.pop(construir_uow)
