"""Registro, login auditado, identidad vigente y administración de personal/roles — EJ-4/EJ-5."""

from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy.exc import IntegrityError

from app.core import security
from app.core.errores import DemasiadosIntentos, EnConflicto, NoAutenticado, NoEncontrado
from app.core.paginacion import Pagina, pagina
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    Usuario,
)
from app.modules.usuarios.schemas import (
    AltaPersonalEntrada,
    AsignacionRolEntrada,
    CambioPasswordEntrada,
    EventoLectura,
    IdentidadLectura,
    LoginEntrada,
    MensajeLectura,
    RegistroEntrada,
    RolAsignadoLectura,
    RolesAsignadosLectura,
    UsuarioLectura,
)
from app.modules.usuarios.unit_of_work import UnitOfWorkIntentoAcceso, UnitOfWorkUsuario


async def obtener_identidad(
    uow: UnitOfWorkUsuario, claims: security.ClaimsSesion,
) -> IdentidadLectura:
    """Consultar estado actual sin reemitir el token ni aplicar permisos RBAC."""
    identidad = None
    async with uow:
        usuario = await uow.usuarios.get_por_id_con_roles(int(claims["sub"]))
        if (usuario is None or not usuario.activo or (
            usuario.password_cambiada_en is not None
            and claims["iat"] < usuario.password_cambiada_en.timestamp()
        )):
            raise NoAutenticado("La sesión no es válida. Volvé a iniciar sesión.")
        ahora = datetime.now(UTC)
        identidad = IdentidadLectura(
            usuario=UsuarioLectura.model_validate(usuario),
            roles_vigentes=[rol.rol for rol in usuario.roles
                            if rol.revocada_en is None and (rol.vence_en is None or rol.vence_en > ahora)],
            roles_token=claims["roles"],
        )
    assert identidad is not None
    return identidad


async def roles_vigentes(uow: UnitOfWorkUsuario, usuario_id: int) -> list[str]:
    """D3: la consulta de roles por petición que usa `requiere_rol`, sin caché."""
    async with uow:
        return await uow.usuarios.get_roles_vigentes(usuario_id)


async def cambiar_password(
    uow: UnitOfWorkUsuario, usuario_id: int, datos: CambioPasswordEntrada, rondas: int,
) -> tuple[datetime, list[str]]:
    usuario = None
    password_hash = None
    async with uow:
        usuario = await uow.usuarios.get_by_id(usuario_id)
        if usuario is None or not usuario.activo:
            raise NoAutenticado("La sesión no es válida. Volvé a iniciar sesión.")
        password_hash = usuario.password_hash
    # Conservar sólo el hash primitivo; ninguna entidad/relación ni conexión durante bcrypt.
    del usuario
    assert password_hash is not None
    if not await security.verificar_password(datos.password_actual, password_hash):
        raise NoAutenticado("La contraseña actual no es correcta.")
    nuevo_hash = await security.hashear_password(datos.password_nueva, rondas)
    cambio = None
    roles: list[str] = []
    async with uow:
        usuario = await uow.usuarios.get_por_id_con_roles(usuario_id)
        if usuario is None or not usuario.activo:
            raise NoAutenticado("La sesión no es válida. Volvé a iniciar sesión.")
        cambio = datetime.now(UTC)
        usuario.password_hash = nuevo_hash
        usuario.password_cambiada_en = cambio
        usuario.debe_cambiar_password = False
        await uow.usuarios.update(usuario)
        await uow.eventos.add(EventoSeguridad(
            cuando=cambio, actor=usuario.email, accion="Cambio de contraseña",
        ))
        roles = [rol.rol for rol in usuario.roles
                 if rol.revocada_en is None and (rol.vence_en is None or rol.vence_en > cambio)]
    # La marca persistida conserva microsegundos y sólo se devuelve tras confirmar.
    assert cambio is not None
    return cambio, roles


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


# --- Administración de personal y roles (EJ-5, DD-18 / Flujo 5) ---


async def alta_personal(
    uow: UnitOfWorkUsuario, datos: AltaPersonalEntrada,
    admin_id: int, admin_email: str, rondas: int,
) -> UsuarioLectura:
    """Alta atómica: usuario + asignación (otorgada_por = admin) + evento en un UoW."""
    password_hash = await security.hashear_password(datos.password_provisoria, rondas)
    usuario = Usuario(
        email=datos.email, nombre=datos.nombre, password_hash=password_hash,
        activo=True, debe_cambiar_password=True,
    )
    ahora = datetime.now(UTC)
    async with uow:
        try:
            await uow.usuarios.add(usuario)
        except IntegrityError:
            raise EnConflicto("Ya existe un usuario con ese correo.") from None
        assert usuario.id is not None
        await uow.roles.add(AsignacionRol(
            usuario_id=usuario.id, rol=datos.rol, desde=ahora, otorgada_por=admin_id,
        ))
        await uow.eventos.add(EventoSeguridad(
            cuando=ahora, actor=admin_email,
            accion=f"Alta de personal con rol {datos.rol}",
        ))
    return UsuarioLectura.model_validate(usuario, from_attributes=True)


async def listar_roles_usuario(
    uow: UnitOfWorkUsuario, usuario_id: int,
) -> RolesAsignadosLectura:
    """Sólo las asignaciones vigentes del usuario, sin revocadas ni vencidas."""
    async with uow:
        if await uow.usuarios.get_by_id(usuario_id) is None:
            raise NoEncontrado("Usuario no encontrado.")
        vigentes = await uow.roles.get_vigentes_de(usuario_id)
    return RolesAsignadosLectura(
        items=[RolAsignadoLectura.model_validate(a, from_attributes=True) for a in vigentes]
    )


async def asignar_rol(
    uow: UnitOfWorkUsuario, usuario_id: int,
    datos: AsignacionRolEntrada, admin_id: int, admin_email: str,
) -> RolAsignadoLectura:
    """Reasigna un rol: cierra la fila vencida y abre una nueva; vigente → 409 (RN-03)."""
    ahora = datetime.now(UTC)
    async with uow:
        if await uow.usuarios.get_by_id(usuario_id) is None:
            raise NoEncontrado("Usuario no encontrado.")
        abierta = await uow.roles.get_abierta(usuario_id, datos.rol)
        if abierta is not None and (abierta.vence_en is None or abierta.vence_en > ahora):
            raise EnConflicto("Ese usuario ya tiene ese rol vigente.")
        if abierta is not None:
            # Fila abierta pero vencida: se cierra y se abre una nueva en la misma transacción.
            abierta.revocada_en = ahora
            await uow.roles.update(abierta)
        asignada = AsignacionRol(
            usuario_id=usuario_id, rol=datos.rol, desde=ahora,
            vence_en=datos.vence_en, otorgada_por=admin_id,
        )
        try:
            await uow.roles.add(asignada)
        except IntegrityError:
            raise EnConflicto("Ese usuario ya tiene ese rol vigente.") from None
        await uow.eventos.add(EventoSeguridad(
            cuando=ahora, actor=admin_email,
            accion=f"Rol {datos.rol} asignado a {usuario_id}",
        ))
    return RolAsignadoLectura.model_validate(asignada, from_attributes=True)


async def revocar_rol(
    uow: UnitOfWorkUsuario, usuario_id: int, rol: str,
    admin_id: int, admin_email: str,
) -> MensajeLectura:
    """Escribe `revocada_en` sin borrar la fila; respeta la autoprotección RN-05."""
    ahora = datetime.now(UTC)
    async with uow:
        usuario = await uow.usuarios.get_by_id(usuario_id)
        if usuario is None:
            raise NoEncontrado("Usuario no encontrado.")
        abierta = await uow.roles.get_abierta(usuario_id, rol)
        if abierta is None:
            raise NoEncontrado("Ese usuario no tiene ese rol vigente.")
        if rol == "ADMIN" and usuario_id == admin_id:
            raise EnConflicto("No podés revocar tu propio rol de administrador.")
        es_vigente = abierta.vence_en is None or abierta.vence_en > ahora
        if rol == "ADMIN" and es_vigente and await uow.roles.count_admins_vigentes() <= 1:
            raise EnConflicto("El sistema no puede quedar sin administradores vigentes.")
        abierta.revocada_en = ahora
        await uow.roles.update(abierta)
        await uow.eventos.add(EventoSeguridad(
            cuando=ahora, actor=admin_email,
            accion=f"Rol {rol} revocado a {usuario_id}",
        ))
    return MensajeLectura(mensaje=f"Rol {rol} revocado")


async def listar_eventos(
    uow: UnitOfWorkUsuario, page: int, size: int,
) -> Pagina[EventoLectura]:
    """Historial paginado de eventos de seguridad, del más reciente al más viejo."""
    async with uow:
        items, total = await uow.eventos.get_pagina(page, size)
    lectura = [EventoLectura.model_validate(e, from_attributes=True) for e in items]
    return pagina(lectura, total, page, size)
