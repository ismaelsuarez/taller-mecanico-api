# Proposal

## Why

Es el segundo relevo del equipo ([EJ-2] en `CHANGES.md`, Ejercicio 2 de la consigna, 14 pts). EJ-1 dejó la aplicación levantando con configuración y salud, pero sin modelo de datos: no hay tablas, no hay migraciones y `seed.py` está vacío. Los seis ejercicios restantes (CRUD, autenticación, autorización, órdenes, integridad, rendimiento) dependen del esquema completo con los nombres obligatorios de la consigna, los tres índices únicos parciales, el catálogo de estados y el disparador de sólo agregado. Governance CRITICO: un error de esquema se arrastra a todo el resto de la corrección.

## What Changes

- Modelos SQLModel en `app/modules/*/models.py` con las **13 tablas** y nombres de columna obligatorios (`usuario`, `asignacion_rol`, `intento_acceso`, `evento_seguridad`, `cliente`, `vehiculo`, `repuesto`, `estado_orden`, `orden_trabajo`, `item_orden`, `historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto` — clase `HistorialPrecio`, IN-02).
- Restricciones e índices: tres **índices únicos parciales** con `postgresql_where` (`asignacion_rol (usuario_id, rol) WHERE revocada_en IS NULL`, `vehiculo (patente) WHERE borrado_en IS NULL`, `repuesto (codigo) WHERE borrado_en IS NULL`); CHECK de `anio`, `precio`, `stock`, `total`, `cantidad`, `precio_unitario` y `precio_nuevo <> precio_anterior`; índice en cada FK; fechas `timestamptz`; dinero `NUMERIC`/`Decimal` (nunca `float`).
- Catálogo `estado_orden` con PK `codigo` (no `id`), `posicion` UNIQUE y `es_final`; la migración lo crea **vacío** y las filas las carga `seed.py`.
- Relaciones navegables en los dos extremos de cada relación que se lea (`Usuario.cliente` devuelve objeto, no lista).
- Alembic con **plantilla asincrónica**; `alembic.ini` sin credenciales (URL desde `Settings`); **nunca `create_all`** (regla A-3).
- **Migración 1**: `--autogenerate` con todas las tablas. **Migración 2**: escrita a mano, función + disparador de sólo agregado sobre `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto` (rechaza `UPDATE` y `DELETE`, venga de donde venga — RN-15). Cada migración con comentario que declara que se leyó antes de aplicarla.
- `seed.py`: vacía las tablas y carga el estado inicial conocido (catálogo primero, después usuarios, clientes, vehículos, repuestos con movimiento «Stock inicial», órdenes 1 y 2 con historiales coherentes, historial de precios del filtro y evento de seguridad con actor `SISTEMA`); hash bcrypt directo con `BCRYPT_ROUNDS` (T-5); idempotente (correr dos veces deja el mismo estado).
- Tests: ciclo `upgrade head` → `downgrade base` → `upgrade head`; seed dos veces seguidas con el mismo resultado; comprobaciones SQL de los índices parciales, la FK de estado y el disparador.

## Capabilities

### New Capabilities

- `modelo-datos`: esquema relacional completo con nombres obligatorios, tipos (`NUMERIC`, `timestamptz`), restricciones CHECK/UNIQUE, tres índices únicos parciales, catálogo `estado_orden` y relaciones navegables.
- `migraciones-esquema`: creación del esquema **sólo** con Alembic asincrónico (migración 1 autogenerada + migración 2 a mano con el disparador de sólo agregado); ciclo upgrade/downgrade/upgrade; sin credenciales en `alembic.ini`.
- `datos-iniciales`: `seed.py` idempotente que deja el estado inicial conocido del taller (catálogo, 7 usuarios, 2 clientes, 4 repuestos, 2 órdenes con historiales) y es parte de la puesta en marcha.

### Modified Capabilities

<!-- Ninguno: los specs existentes (configuracion-aplicacion, salud-servicio) no cambian de requisito. -->

## Impact

- **Código nuevo**: `app/modules/usuarios/models.py`, `app/modules/clientes/models.py`, `app/modules/repuestos/models.py`, `app/modules/ordenes/models.py`; contenido de `seed.py`.
- **Migraciones**: `alembic.ini`, `migrations/env.py` (plantilla async), `migrations/versions/` con las dos versiones.
- **Dependencias**: ninguna nueva (SQLModel, SQLAlchemy async, asyncpg, Alembic ya están en `requirements.txt` desde EJ-1).
- **Documentación**: `README.md` (pasos de migración y seed), `env.example` sin cambios.
- **Tests**: `test/pytest/` (migraciones, seed, índices, disparador) y los `.http`/SQL de verificación que el DoD exige.
- **Sin endpoints nuevos**: la API sigue exponiendo sólo `/health/*`; los routers de CRUD llegan en EJ-3.
