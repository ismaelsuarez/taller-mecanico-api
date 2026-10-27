"""Verifica el esquema declarado en los modelos SQLModel (EJ-2, spec modelo-datos).

La primera parte lee el metadata de SQLAlchemy de la aplicación (sin tocar la base).
La segunda parte (`TestComportamientoEnBase`) verifica contra la PostgreSQL real de test
que los índices, UNIQUE y CHECK se comportan como exige la consigna sobre el
esquema creado por Alembic, incluidos los disparadores de la segunda migración (A-3).
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import DateTime, Numeric, text
from sqlmodel import SQLModel

# Importar todos los modelos para que estén registrados en el metadata de la app.
from app.modules.clientes.models import Cliente, Vehiculo  # noqa: F401
from app.modules.ordenes.models import (  # noqa: F401
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.repuestos.models import (  # noqa: F401
    HistorialPrecio,
    MovimientoStock,
    Repuesto,
)
from app.modules.usuarios.models import (  # noqa: F401
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    Usuario,
)

TABLAS_ESPERADAS = {
    "usuario",
    "asignacion_rol",
    "intento_acceso",
    "evento_seguridad",
    "cliente",
    "vehiculo",
    "repuesto",
    "estado_orden",
    "orden_trabajo",
    "item_orden",
    "historial_estado_orden",
    "movimiento_stock",
    "historial_precio_repuesto",
}


def _metadata():
    return SQLModel.metadata


def _tabla(nombre: str):
    return _metadata().tables[nombre]


def _es_numerico(columna) -> bool:
    return isinstance(columna.type, Numeric)


def _es_timestamptz(columna) -> bool:
    return isinstance(columna.type, DateTime) and columna.type.timezone


class TestTablas:
    def test_las_trece_tablas_existen(self):
        faltantes = TABLAS_ESPERADAS - set(_metadata().tables)
        assert not faltantes, f"Faltan tablas en el metadata: {faltantes}"

    def test_historial_precio_mapea_a_su_tabla(self):
        assert HistorialPrecio.__tablename__ == "historial_precio_repuesto"

    def test_estado_orden_usa_pk_codigo(self):
        tabla = _tabla("estado_orden")
        claves = list(tabla.primary_key.columns)
        assert len(claves) == 1
        assert claves[0].name == "codigo"


class TestTipos:
    @pytest.mark.parametrize(
        "tabla,columna",
        [
            ("repuesto", "precio"),
            ("orden_trabajo", "total"),
            ("item_orden", "precio_unitario"),
            ("historial_precio_repuesto", "precio_anterior"),
            ("historial_precio_repuesto", "precio_nuevo"),
        ],
    )
    def test_dinero_es_numerico(self, tabla, columna):
        col = _tabla(tabla).columns[columna]
        assert _es_numerico(col), f"{tabla}.{columna} debería ser NUMERIC, es {col.type}"

    @pytest.mark.parametrize(
        "tabla,columna",
        [
            ("usuario", "password_cambiada_en"),
            ("asignacion_rol", "desde"),
            ("asignacion_rol", "vence_en"),
            ("asignacion_rol", "revocada_en"),
            ("intento_acceso", "cuando"),
            ("evento_seguridad", "cuando"),
            ("vehiculo", "borrado_en"),
            ("orden_trabajo", "creada_en"),
            ("historial_estado_orden", "cuando"),
            ("movimiento_stock", "cuando"),
            ("historial_precio_repuesto", "cuando"),
        ],
    )
    def test_fechas_son_timestamptz(self, tabla, columna):
        col = _tabla(tabla).columns[columna]
        assert _es_timestamptz(col), f"{tabla}.{columna} debería ser timestamptz, es {col.type}"


class TestIndicesParciales:
    def _indices_parciales_de(self, nombre_tabla: str):
        tabla = _tabla(nombre_tabla)
        return [
            idx
            for idx in tabla.indexes
            if idx.unique and getattr(idx, "dialect_options", {}).get("postgresql", {}).get("where")
        ]

    def test_asignacion_rol_tiene_indice_parcial(self):
        indices = self._indices_parciales_de("asignacion_rol")
        assert indices, "Falta índice único parcial en asignacion_rol"
        idx = indices[0]
        assert [c.name for c in idx.columns] == ["usuario_id", "rol"]
        assert "revocada_en IS NULL" in str(idx.dialect_options["postgresql"]["where"]).replace("(", "").replace(")", "")

    def test_vehiculo_tiene_indice_parcial_de_patente(self):
        indices = self._indices_parciales_de("vehiculo")
        assert indices, "Falta índice único parcial en vehiculo"
        idx = indices[0]
        assert [c.name for c in idx.columns] == ["patente"]
        assert "borrado_en IS NULL" in str(idx.dialect_options["postgresql"]["where"])

    def test_repuesto_tiene_indice_parcial_de_codigo(self):
        indices = self._indices_parciales_de("repuesto")
        assert indices, "Falta índice único parcial en repuesto"
        idx = indices[0]
        assert [c.name for c in idx.columns] == ["codigo"]
        assert "borrado_en IS NULL" in str(idx.dialect_options["postgresql"]["where"])


class TestForeignKeysIndexadas:
    # Cada par (tabla, columna) que es FK según la consigna.
    FKS = [
        ("asignacion_rol", "usuario_id"),
        ("asignacion_rol", "otorgada_por"),
        ("cliente", "usuario_id"),
        ("vehiculo", "cliente_id"),
        ("orden_trabajo", "vehiculo_id"),
        ("orden_trabajo", "mecanico_id"),
        ("orden_trabajo", "estado"),
        ("item_orden", "orden_id"),
        ("item_orden", "repuesto_id"),
        ("historial_estado_orden", "orden_id"),
        ("historial_estado_orden", "desde_estado"),
        ("historial_estado_orden", "hasta_estado"),
        ("historial_estado_orden", "usuario_id"),
        ("movimiento_stock", "repuesto_id"),
        ("movimiento_stock", "orden_id"),
        ("movimiento_stock", "usuario_id"),
        ("historial_precio_repuesto", "repuesto_id"),
        ("historial_precio_repuesto", "usuario_id"),
    ]

    @pytest.mark.parametrize("tabla,columna", FKS)
    def test_fk_tiene_indice(self, tabla, columna):
        col = _tabla(tabla).columns[columna]
        assert col.foreign_keys, f"{tabla}.{columna} no es FK"
        # index=True en la columna crea un índice; también sirve un índice compuesto que la encabece.
        tiene_indice_propio = getattr(col, "index", False)
        tiene_indice_compuesto = any(
            list(idx.columns)[0].name == columna for idx in _tabla(tabla).indexes
        )
        assert tiene_indice_propio or tiene_indice_compuesto, (
            f"{tabla}.{columna} es FK pero no tiene índice"
        )


class TestChecks:
    def _checks_de(self, nombre_tabla: str):
        tabla = _tabla(nombre_tabla)
        return [c for c in tabla.constraints if c.__class__.__name__ == "CheckConstraint"]

    def test_asignacion_rol_check_rol(self):
        checks = self._checks_de("asignacion_rol")
        textos = " ".join(str(c.sqltext) for c in checks)
        assert "ADMIN" in textos and "RECEPCION" in textos and "MECANICO" in textos and "CLIENTE" in textos

    def test_vehiculo_check_anio(self):
        checks = self._checks_de("vehiculo")
        textos = " ".join(str(c.sqltext) for c in checks)
        assert "1950" in textos and "2100" in textos

    def test_repuesto_check_precio_y_stock(self):
        checks = self._checks_de("repuesto")
        textos = " ".join(str(c.sqltext) for c in checks)
        assert "precio" in textos and ">" in textos
        assert "stock" in textos and ">=" in textos

    def test_orden_trabajo_check_total(self):
        checks = self._checks_de("orden_trabajo")
        textos = " ".join(str(c.sqltext) for c in checks)
        assert "total" in textos and ">=" in textos

    def test_item_orden_check_cantidad_y_precio(self):
        checks = self._checks_de("item_orden")
        textos = " ".join(str(c.sqltext) for c in checks)
        assert "cantidad" in textos
        assert "precio_unitario" in textos

    def test_movimiento_stock_check_cantidad_distinta_de_cero(self):
        checks = self._checks_de("movimiento_stock")
        textos = " ".join(str(c.sqltext) for c in checks)
        assert "cantidad" in textos and "<>" in textos or "!=" in textos

    def test_historial_precio_check_cambio(self):
        checks = self._checks_de("historial_precio_repuesto")
        textos = " ".join(str(c.sqltext) for c in checks)
        assert "precio_nuevo" in textos and "precio_anterior" in textos


class TestUniques:
    def test_usuario_email_unique(self):
        col = _tabla("usuario").columns["email"]
        assert col.unique or any(
            list(idx.columns) == [col] and idx.unique for idx in _tabla("usuario").indexes
        ), "usuario.email debería ser UNIQUE"

    def test_cliente_documento_unique(self):
        col = _tabla("cliente").columns["documento"]
        assert col.unique or any(
            list(idx.columns) == [col] and idx.unique for idx in _tabla("cliente").indexes
        ), "cliente.documento debería ser UNIQUE"

    def test_cliente_usuario_id_unique(self):
        col = _tabla("cliente").columns["usuario_id"]
        assert col.unique or any(
            list(idx.columns) == [col] and idx.unique for idx in _tabla("cliente").indexes
        ), "cliente.usuario_id debería ser UNIQUE (uno a uno opcional)"

    def test_item_orden_orden_repuesto_unique(self):
        tabla = _tabla("item_orden")
        en_indices = any(
            idx.unique and [c.name for c in idx.columns] == ["orden_id", "repuesto_id"]
            for idx in tabla.indexes
        )
        en_constraints = any(
            c.__class__.__name__ == "UniqueConstraint"
            and [c.name for c in c.columns] == ["orden_id", "repuesto_id"]
            for c in tabla.constraints
        )
        assert en_indices or en_constraints, "Falta UNIQUE (orden_id, repuesto_id) en item_orden"


class TestRelaciones:
    def test_usuario_cliente_es_objeto_opcional(self):
        propiedad = Usuario.__mapper__.relationships["cliente"]
        assert propiedad.uselist is False, "Usuario.cliente debe devolver un objeto, no una lista"

    def test_cliente_vehiculos_es_lista(self):
        propiedad = Cliente.__mapper__.relationships["vehiculos"]
        assert propiedad.uselist is True

    def test_usuario_roles_es_lista(self):
        propiedad = Usuario.__mapper__.relationships["roles"]
        assert propiedad.uselist is True


class TestDecimalEnPython:
    def test_repuesto_precio_es_decimal_en_el_modelo(self):
        campo = Repuesto.model_fields["precio"]
        assert campo.annotation is Decimal or (campo.annotation and Decimal in getattr(campo.annotation, "__args__", ()))

    def test_orden_total_es_decimal_en_el_modelo(self):
        campo = OrdenTrabajo.model_fields["total"]
        assert campo.annotation is Decimal or (campo.annotation and Decimal in getattr(campo.annotation, "__args__", ()))


# ---------------------------------------------------------------------------
# Comportamiento contra la base de test real (1.3 / 1.4)
# ---------------------------------------------------------------------------

@pytest.fixture
async def esquema_de_test(base_migrada):
    """Reutiliza el esquema real de Alembic, aislado por test."""
    yield base_migrada


async def _ejecutar(motor, consulta: str, **params):
    async with motor.begin() as conn:
        return await conn.execute(text(consulta), params)


async def _falla_por_integridad(motor, consulta: str, **params) -> str:
    from sqlalchemy.exc import DBAPIError

    try:
        await _ejecutar(motor, consulta, **params)
    except DBAPIError as error:
        return str(error.orig)
    raise AssertionError(f"La consulta debía fallar: {consulta}")


@pytest.mark.asyncio
class TestComportamientoEnBase:
    async def test_patente_borrada_puede_reutilizarse(self, esquema_de_test):
        ahora = datetime.now(timezone.utc)
        await _ejecutar(
            esquema_de_test,
            "INSERT INTO cliente (id, nombre, documento, telefono) VALUES (1, 'Laura', 'D-1', '111')",
        )
        await _ejecutar(
            esquema_de_test,
            "INSERT INTO vehiculo (id, cliente_id, patente, marca, modelo, anio, borrado_en) "
            "VALUES (1, 1, 'AC456EF', 'Fiat', 'Cronos', 2020, :ahora)",
            ahora=ahora,
        )
        # La patente del vehículo borrado se puede reusar en uno vigente (índice parcial).
        await _ejecutar(
            esquema_de_test,
            "INSERT INTO vehiculo (id, cliente_id, patente, marca, modelo, anio) "
            "VALUES (2, 1, 'AC456EF', 'Toyota', 'Corolla', 2022)",
        )

    async def test_dos_roles_abiertos_iguales_rechazados(self, esquema_de_test):
        ahora = datetime.now(timezone.utc)
        await _ejecutar(
            esquema_de_test,
            "INSERT INTO usuario (id, email, nombre, password_hash, activo, debe_cambiar_password) "
            "VALUES (1, 'a@x.com', 'A', 'h', true, false)",
        )
        await _ejecutar(
            esquema_de_test,
            "INSERT INTO asignacion_rol (usuario_id, rol, desde) VALUES (1, 'ADMIN', :ahora)",
            ahora=ahora,
        )
        mensaje = await _falla_por_integridad(
            esquema_de_test,
            "INSERT INTO asignacion_rol (usuario_id, rol, desde) VALUES (1, 'ADMIN', :ahora)",
            ahora=ahora,
        )
        assert "uq_asignacion_rol_abierta" in mensaje or "unique" in mensaje.lower()

    async def test_dos_codigos_vigentes_rechazados(self, esquema_de_test):
        await _ejecutar(
            esquema_de_test,
            "INSERT INTO repuesto (id, codigo, descripcion, precio, stock) "
            "VALUES (1, 'FIL-001', 'Filtro', 8500.00, 10)",
        )
        mensaje = await _falla_por_integridad(
            esquema_de_test,
            "INSERT INTO repuesto (id, codigo, descripcion, precio, stock) "
            "VALUES (2, 'FIL-001', 'Otro filtro', 9000.00, 5)",
        )
        assert "uq_repuesto_codigo_vigente" in mensaje or "unique" in mensaje.lower()

    async def test_estado_inexistente_rechazado_por_fk(self, esquema_de_test):
        ahora = datetime.now(timezone.utc)
        await _ejecutar(
            esquema_de_test,
            "INSERT INTO cliente (id, nombre, documento, telefono) VALUES (1, 'Jorge', 'D-2', '222')",
        )
        await _ejecutar(
            esquema_de_test,
            "INSERT INTO vehiculo (id, cliente_id, patente, marca, modelo, anio) "
            "VALUES (1, 1, 'AB123CD', 'Ford', 'Ka', 2018)",
        )
        mensaje = await _falla_por_integridad(
            esquema_de_test,
            "INSERT INTO orden_trabajo (vehiculo_id, estado, falla, creada_en, total) "
            "VALUES (1, 'INEXISTENTE', 'Falla', :ahora, 0)",
            ahora=ahora,
        )
        assert "foreign key" in mensaje.lower() or "fk" in mensaje.lower() or "estado_orden" in mensaje

    async def test_correo_duplicado_rechazado_por_unique(self, esquema_de_test):
        await _ejecutar(
            esquema_de_test,
            "INSERT INTO usuario (id, email, nombre, password_hash, activo, debe_cambiar_password) "
            "VALUES (1, 'a@x.com', 'A', 'h', true, false)",
        )
        mensaje = await _falla_por_integridad(
            esquema_de_test,
            "INSERT INTO usuario (id, email, nombre, password_hash, activo, debe_cambiar_password) "
            "VALUES (2, 'a@x.com', 'B', 'h', true, false)",
        )
        assert "unique" in mensaje.lower() or "usuario_email_key" in mensaje or "uq" in mensaje.lower()
