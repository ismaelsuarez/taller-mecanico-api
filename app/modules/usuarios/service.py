"""Registro atómico y login auditado; bcrypt sin transacción ni conexión retenida."""

from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy.exc import IntegrityError

from app.core import security
from app.core.errores import DemasiadosIntentos, EnConflicto, NoAutenticado
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    Usuario,
)
from app.modules.usuarios.schemas import LoginEntrada, RegistroEntrada
from app.modules.usuarios.unit_of_work import UnitOfWorkIntentoAcceso, UnitOfWorkUsuario


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


async def iniciar_sesion(
    uow: UnitOfWorkUsuario, intentos: UnitOfWorkIntentoAcceso,
    datos: LoginEntrada, ip: str, hash_ficticio: str,
) -> tuple[int, bool, list[str]]:
    ahora = datetime.now(UTC)
    ventana = None
    async with intentos:
        ventana = await intentos.intentos.consultar_ventana(datos.email, ip, ahora)
    assert ventana is not None
    if ventana.fallos >= 5:
        assert ventana.fallo_mas_antiguo is not None
        espera = max(1, ceil((ventana.fallo_mas_antiguo + timedelta(seconds=60) - ahora).total_seconds()))
        # El intento sobrevive incluso si falla la confirmación del evento normal.
        async with intentos:
            await intentos.intentos.add(IntentoAcceso(
                email=datos.email, ip=ip, cuando=ahora, exito=False,
            ))
        async with uow:
            await uow.eventos.add(EventoSeguridad(
                cuando=ahora, actor=datos.email, accion="Login bloqueado por demasiados intentos",
            ))
        raise DemasiadosIntentos(espera)

    usuario_id, password_hash, pendiente, activo = None, hash_ficticio, False, False
    asignaciones: list[tuple[str, datetime | None, datetime | None]] = []
    async with uow:
        usuario = await uow.usuarios.get_por_email_con_roles(datos.email)
        if usuario is not None:
            usuario_id, password_hash = usuario.id, usuario.password_hash
            pendiente, activo = usuario.debe_cambiar_password, usuario.activo
            asignaciones = [(rol.rol, rol.revocada_en, rol.vence_en) for rol in usuario.roles]
    # Sólo primitivas fuera de la lectura; el UoW devuelve la conexión antes de bcrypt.
    correcta = await security.verificar_password(datos.password, password_hash)
    exito = usuario_id is not None and correcta and activo
    # DD-19: confirma en otra transacción/conexión incluso ante rechazo o rollback normal.
    async with intentos:
        await intentos.intentos.add(IntentoAcceso(
            email=datos.email, ip=ip, cuando=datetime.now(UTC), exito=exito,
        ))
    if usuario_id is None or not correcta:
        raise NoAutenticado("El correo o la contraseña no son correctos.")
    if not activo:
        raise NoAutenticado("Tu cuenta está desactivada. Comunicate con el taller para reactivarla.")
    assert usuario_id is not None
    ahora = datetime.now(UTC)
    roles = [rol for rol, revocada, vence in asignaciones
             if revocada is None and (vence is None or vence > ahora)]
    return usuario_id, pendiente, roles
