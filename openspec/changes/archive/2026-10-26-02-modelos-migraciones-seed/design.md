# Design

## Context

EJ-1 dejó la aplicación levantando con `Settings`, lifespan, `/health/*` y el runner de pytest contra PostgreSQL real (ver `proposal.md` → Why). El esquema todavía no existe: `migrations/` sólo tiene un README y `seed.py` está vacío. Restricciones que dan forma al enfoque:

- Nombres de tablas y columnas **obligatorios** (regla A-1); la consigna es la única fuente de verdad.
- Esquema **sólo con Alembic**, plantilla asincrónica, **nunca `create_all`** (regla A-3); la migración del disparador se escribe a mano.
- Reglas duras aplicables: S-1 (`NUMERIC`/`Decimal`, `timestamptz`), S-6 (sin credenciales en `alembic.ini`), A-5 (catálogo `estado_orden` no se edita desde la API), E-1 (identificadores en español), E-2 (pytest contra PostgreSQL real, 0 skipped al cierre).
- Decisiones del equipo: DD-01 (roles en tabla propia), DD-02 (catálogo `estado_orden`), DD-03 (índices únicos parciales), DD-06 (sólo agregado por disparador), DD-14..DD-16 (datos del seed), DD-34 (convenciones de tests de EJ-1).
- T-5: en EJ-2 el seed hashea con bcrypt directamente usando `BCRYPT_ROUNDS` de `Settings`; `core/security.py` ya trae `hashear_password` de EJ-1 y se reutiliza.
- Máquina de desarrollo: Python 3.12 en el venv del proyecto, Docker + Compose, sin `psql` local (se usa `docker compose exec db psql`).

## Goals / Non-Goals

**Goals:**
- Esquema completo con los 13 nombres obligatorios, las tres restricciones de unicidad parcial y el catálogo vacío, listo para que EJ-3..EJ-8 no toquen migraciones de tablas.
- Disparador de sólo agregado instalado por migración escrita a mano y demostrable desde la aplicación y desde psql.
- `seed.py` idempotente que deja el estado inicial conocido y que los siguientes relevos pueden correr sin pensar.
- Suite de pytest que verifica migraciones, seed, índices y disparador contra la PostgreSQL real de test.

**Non-Goals:**
- Endpoints, contratos (`schemas.py`), repositorios o Unit of Work (EJ-3 en adelante).
- Autenticación, cookies o JWT (EJ-4); el seed hashea contraseñas con la función de hash ya existente, sin verificar login.
- Evaluación formal de C-14 con captura de psql (EJ-7 consolida y evidencia); acá sólo se instala y se prueba el comportamiento del disparador.
- Sembrar datos de prueba desde la API (no hay API de escritura todavía).

## Decisions

### D1 — Un modelo SQLModel por módulo, con la clase y la tabla que la consigna fija

Cada `app/modules/<módulo>/models.py` declara sus entidades con `SQLModel(table=True)`:

| Módulo | Clases |
|---|---|
| `usuarios` | `Usuario`, `AsignacionRol`, `IntentoAcceso`, `EventoSeguridad` |
| `clientes` | `Cliente`, `Vehiculo` |
| `repuestos` | `Repuesto`, `MovimientoStock`, `HistorialPrecio` (`__tablename__ = "historial_precio_repuesto"`) |
| `ordenes` | `OrdenTrabajo`, `EstadoOrden`, `ItemOrden`, `HistorialEstadoOrden` |

- Dinero: `Decimal` con `Numeric(10,2)` / `Numeric(12,2)` (S-1). Fechas: `datetime` con `DateTime(timezone=True)`.
- `Usuario.cliente` es `Optional["Cliente"]` con `sa_relationship` que resuelve 1..0..1; `Cliente.usuario` es el lado inverso. `Usuario.roles` es lista de `AsignacionRol`.
- Relaciones de composición (`OrdenTrabajo` → `ItemOrden` / `HistorialEstadoOrden`) con `cascade="all, delete-orphan"` y `passive_deletes=True` para que el borrado en cascada lo resuelva la base.
- FK a `estado_orden.codigo` (PK string) en `orden_trabajo.estado` y en las dos columnas del historial de estados (`desde_estado` nullable).
- El catálogo `EstadoOrden` vive en el módulo `ordenes` aunque lo use la API desde varios lados; su repositorio (EJ-3/6) será de sólo lectura.
- *Alternativa*: un único `models.py` central (rompe la estructura obligatoria por módulo, A-2).

### D2 — Índices y restricciones declarados en el modelo, verificados en los tests

- Los tres índices únicos parciales se declaran con `Index(..., unique=True, postgresql_where=...)` en `__table_args__` de `AsignacionRol`, `Vehiculo` y `Repuesto` (DD-03).
- Cada FK lleva su `index=True` en la columna (o un `Index` dedicado cuando conviene).
- CHECKs con `CheckConstraint` en `__table_args__` (rol, anio, precios, stock, total, cantidad, `precio_nuevo <> precio_anterior`).
- Un test de integridad ejecuta consultas SQL contra la base de test para comprobar que los índices parciales y las FKs existen y se comportan como se espera (patente borrada → se puede reutilizar; rol abierto duplicado → rechazado). Así un refactor accidental de un `__table_args__` falla el suite.

### D3 — Alembic asincrónico con URL desde `Settings`

- `migrations/env.py` con la plantilla asincrónica de Alembic 1.13: obtiene `Settings`, usa `settings.url_base_datos` (el `@computed_field` de EJ-1) y el motor de `app.core.database`; `target_metadata = Base.metadata` de SQLModel (importando todos los `models.py` para que autogenerate vea las 13 tablas).
- `alembic.ini` sin `sqlalchemy.url`; la plantilla la arma en runtime (S-6).
- Migración 1 (`xxxx_tablas.py`): `--autogenerate` con el metadata completo. En el comentario superior se declara que se leyó antes de aplicarla (A-3).
- Migración 2 (`yyyy_solo_agregado.py`): **escrita a mano**, `upgrade()` crea la función `solo_agregado()` y los tres triggers `trg_<tabla>_solo_agregado` (evento `UPDATE OR DELETE`); `downgrade()` los dropea en orden inverso. También lleva el comentario de lectura previa.
- El disparador lanza excepción con mensaje claro en español (p. ej. «La tabla historial_estado_orden es de sólo agregado: no se puede modificar ni borrar.»); el mensaje no expone nombres internos sensibles beyond la propia tabla (que el usuario de psql ya ve).
- *Alternativa*: permisos REVOKE de UPDATE/DELETE (DD-06 la descarta como equivalente; el TP usa un solo rol de base y el disparador es más explícito en la corrección).

### D4 — `seed.py` como script async con su propio motor

- `seed.py` es un script independiente (`python seed.py`) que:
  1. arma `Settings` y un motor asincrónico propio (no reutiliza el de la app porque la app no está corriendo);
  2. verifica que las tablas existan (si no, sale con mensaje «Falta migrar: corré `alembic upgrade head`.»);
  3. vacía las tablas en orden inverso a las dependencias (historiales/movimientos/items/órdenes/vehículos/clientes/asignaciones/intentos/eventos/usuarios/repuestos/estados);
  4. carga el catálogo primero, después el resto en orden de FK;
  5. hashea contraseñas con `hashear_password` de `app.core.security` (reutiliza el semáforo de EJ-1; T-5);
  6. cierra el motor.
- Idempotencia por vaciado completo + recarga (no hay UPSERT): dos corridas dejan el mismo estado lógico.
- Contraseñas de mentira definidas como constantes al inicio del archivo, junto con un comentario que dice que son de prueba y no salen de ahí (S-6, DD-14..DD-16).
- Los `usuario_id` de movimientos, historiales y precios salen de una consulta por correo tras crear los usuarios (DD-14), no están hardcodeados como números.
- *Alternativa*: seed con SQLAlchemy Core puro (pierde la reutilización de `hashear_password` y la coherencia con los modelos).

### D5 — Arquitectura de verificación (pytest + SQL)

Siguiendo DD-34 (sin `__init__.py` en `test/` ni `test/pytest/`; `from conftest import ...`):

- `test/pytest/conftest.py` (ampliación del de EJ-1): fixture `base_migrada` que aplica `upgrade head` sobre la base de test al inicio de la sesión y deja el esquema listo; fixture `seed_limpio` que corre `seed.py` y limpie después si hace falta.
- `test/pytest/test_modelos.py`: existencia de las 13 tablas, tipos NUMERIC/timestamptz, los tres índices parciales y su comportamiento, CHECKs, FK de estado, navegación `Usuario.cliente`.
- `test/pytest/test_migraciones.py`: ciclo upgrade→downgrade→upgrade; el disparador rechaza UPDATE/DELETE y admite INSERT; el downgrade limpia el disparador.
- `test/pytest/test_seed.py`: seed dos veces con el mismo resultado; catálogo con 4 filas; coherencia stock↔movimientos; totales de las órdenes; evento `SISTEMA`.
- Alcance del runner: los tests que necesitan base se saltan con motivo claro si la base no responde (comodidad heredada de EJ-1); el DoD exige correrlos con `db` levantada y **0 skipped**.

### D6 — Orden de implementación (TDD)

1. Modelos (RED con tests de existencia/tipos → GREEN con `models.py`).
2. Alembic env + migración 1 (RED: upgrade falla sin tablas → GREEN).
3. Migración 2 del disparador (RED: UPDATE pasa → GREEN: rechaza).
4. Seed (RED: sin seed los datos no existen → GREEN).
5. Cierre: README, `pytest -rs` 0 skipped, checkbox en `CHANGES.md`.

## Risks / Trade-offs

- [Autogenerate puede omitir un índice o CHECK si el metadata no está completo] → los tests de `test_modelos.py` verifican por SQL directo, no confían en el autogenerate.
- [El disparador rompe el `downgrade base` si no se dropea antes que las tablas] → el `downgrade()` de la migración 2 dropea triggers y función; la migración 1 no toca esas tablas. Verificado en el ciclo upgrade/downgrade/upgrade.
- [Seed idempotente por TRUNCATE/DELETE puede fallar si aparece una FK nueva sin cascade] → el vaciado usa `DELETE` en orden inverso explícito (sin depender de CASCADE) y un test de dos corridas lo cubre.
- [bcrypt en el seed suma tiempo] → setenta hashes a costo 12 son segundos aceptables; en tests el costo baja a 4 (DD-34).
- [Dos fuentes de verdad de `Base.metadata` (app y migrations)] → `env.py` importa los mismos `models.py` que la app; un modelo olvidado rompe el autogenerate y se ve al primer upgrade.

## Migration Plan

Despliegue: `alembic upgrade head` + `python seed.py` (ya documentados en el README de EJ-1 como próximos pasos). Rollback: `alembic downgrade base` elimina tablas, índices, función y triggers. No hay datos productivos que migrar: el proyecto está en desarrollo y el seed es el estado inicial.

## Open Questions

Ninguna: las preguntas del seed están resueltas en DD-14, DD-15 y DD-16; la de `otorgada_por` (SU-02) queda como FK nullable y no bloquea este change.
