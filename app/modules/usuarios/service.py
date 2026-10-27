"""Registro: hash sin transacción y cuatro escrituras en un único UoW inyectado."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.core import security
from app.core.errores import EnConflicto
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, Usuario
from app.modules.usuarios.schemas import RegistroEntrada
from app.modules.usuarios.unit_of_work import UnitOfWorkUsuario


async def registrar_usuario(
    uow: UnitOfWorkUsuario, datos: RegistroEntrada, rondas: int,
) -> int:
    password_hash = await security.hashear_password(datos.password, rondas)
    usuario = Usuario(email=datos.email, nombre=datos.nombre, password_hash=password_hash)
    async with uow:
        try:
            await uow.usuarios.add(usuario)
        except IntegrityError:
            raise EnConflicto("Ya existe un usuario con ese correo.") from None
        assert usuario.id is not None
        ahora = datetime.now(UTC)
        await uow.roles.add(AsignacionRol(
            usuario_id=usuario.id, rol="CLIENTE", desde=ahora,
        ))
        try:
            await uow.clientes.add(Cliente(
                usuario_id=usuario.id, nombre=datos.nombre,
                documento=datos.documento, telefono=datos.telefono,
            ))
        except IntegrityError:
            raise EnConflicto("Ya existe un cliente con ese documento.") from None
        await uow.eventos.add(EventoSeguridad(
            cuando=ahora, actor=datos.email, accion="Alta de usuario cliente (registro)",
        ))
    assert usuario.id is not None
    return usuario.id
