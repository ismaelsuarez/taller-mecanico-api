# Tasks

> Ciclo TDD (regla E-2, Strict TDD): en cada grupo con comportamiento, primero el test en rojo, después el código mínimo, después refactor con los tests en verde. Comando de tests: `pytest` (desde la raíz, con el venv activo o `docker compose exec api pytest`).
> Convenciones DD-34: sin `__init__.py` en `test/` ni `test/pytest/`; utilidades con `from conftest import ...`; fixture `configurar_entorno` de EJ-1 se reutiliza.

## 1. Modelos SQLModel (spec `modelo-datos`)

- [x] 1.1 RED: crear `test/pytest/test_modelos.py` con tests que fallen todavía: las 13 tablas existen en el metadata de la app; `HistorialPrecio` mapea a `historial_precio_repuesto`; columnas de dinero son NUMERIC y de fecha timestamptz; los tres índices únicos parciales existen con su `postgresql_where`; cada FK tiene índice; CHECKs de rol, anio, precios, stock, total, cantidad y `precio_nuevo <> precio_anterior` están declarados; `estado_orden` usa PK `codigo`; `Usuario.cliente` devuelve objeto opcional. Verificación: `pytest test/pytest/test_modelos.py` falla por falta de implementación.
- [x] 1.2 GREEN: implementar `app/modules/usuarios/models.py` (`Usuario`, `AsignacionRol`, `IntentoAcceso`, `EventoSeguridad`), `app/modules/clientes/models.py` (`Cliente`, `Vehiculo`), `app/modules/repuestos/models.py` (`Repuesto`, `MovimientoStock`, `HistorialPrecio`) y `app/modules/ordenes/models.py` (`OrdenTrabajo`, `EstadoOrden`, `ItemOrden`, `HistorialEstadoOrden`), con tipos, restricciones, índices y relaciones de D1/D2. Verificación: `pytest test/pytest/test_modelos.py` pasa completo.
- [x] 1.3 RED: ampliar `test_modelos.py` con comportamiento contra la base de test real (fixture que migra o que usa el esquema de la sesión): patente borrada lógicamente se puede reutilizar; dos roles abiertos iguales rechazados; dos códigos de repuesto vigentes rechazados; estado inexistente rechazado por FK; correo duplicado rechazado por UNIQUE. Verificación: los tests fallan sin esquema (esperado) o fallan si un índice falta.
- [x] 1.4 GREEN: verificar que los índices/restricciones declarados en 1.2 producen ese comportamiento; corregir `__table_args__` si algo falla. Verificación: `pytest -rs test/pytest/test_modelos.py` con `db` levantada y **0 skipped**.

## 2. Alembic asincrónico y migración 1 (spec `migraciones-esquema`)

- [x] 2.1 Inicializar Alembic con plantilla asincrónica: `alembic.ini` sin `sqlalchemy.url`, `migrations/env.py` que lee `Settings` y usa `target_metadata` de los modelos de la app (importando todos los `models.py`). Verificación: `alembic upgrade head` sobre base vacía falla sólo porque no hay versiones todavía, sin error de conexión ni de plantilla.
- [x] 2.2 RED: test en `test_migraciones.py` que aplica `upgrade head` sobre una base de test vacía y comprueba que las 13 tablas, los tres índices parciales y los CHECKs existen (consultas SQL al catálogo de la base). Verificación: el test falla sin migraciones.
- [x] 2.3 Generar la migración 1 con `alembic revision --autogenerate` (todas las tablas), agregar el comentario que declara que se leyó antes de aplicarla y ajustar lo que autogenerate no vea mal. Verificación: `pytest test/pytest/test_migraciones.py` (parte de tablas) pasa; `alembic upgrade head` en base vacía crea el esquema y `estado_orden` queda vacía.

## 3. Migración 2: disparador de sólo agregado (spec `migraciones-esquema`)

- [x] 3.1 RED: test que tras `upgrade head` un `UPDATE` y un `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` son rechazados (seis casos) y un `INSERT` es admitido. Verificación: el test falla porque el disparador no existe todavía.
- [x] 3.2 GREEN: escribir a mano `migrations/versions/yyyy_solo_agregado.py` con la función y los tres triggers (`UPDATE OR DELETE`), el comentario de lectura previa y un `downgrade()` que los elimina. Verificación: el test de 3.1 pasa.
- [x] 3.3 RED: test del ciclo `upgrade head` → `downgrade base` → `upgrade head` sobre base vacía y test de que tras el downgrade la función y los triggers ya no existen. Verificación: los tests fallan (ciclo no verificado).
- [x] 3.4 GREEN: ajustar la migración 2 si el downgrade deja restos. Verificación: `pytest -rs test/pytest/test_migraciones.py` con `db` levantada y **0 skipped**; manual: los tres comandos en secuencia sobre una base vacía terminan sin error.

## 4. Seed (spec `datos-iniciales`)

- [x] 4.1 RED: test en `test_seed.py` que corre `seed.py` (subproceso o función importable) sobre la base migrada y comprueba: catálogo con 4 filas en el orden correcto; 7 usuarios con sus roles; `nuevo@example.com` con `debe_cambiar_password`; Laura con usuario y 2 vehículos, Jorge sin usuario con 1; los 4 repuestos con los códigos/precios/stocks de la tabla; un movimiento «Stock inicial» por repuesto cuya suma coincide con `stock`; orden 1 `PENDIENTE` con 2 ítems y total 56500.00; orden 2 `EN_REPARACION` con `mecanico_id` de mecanico@, 4 bujías y total 26000.00; historial de estados coherente; historial de precios del filtro 8000→8500; evento con actor `SISTEMA`. Verificación: el test falla con `seed.py` vacío.
- [x] 4.2 GREEN: implementar `seed.py` según D4 (motor propio, vaciado en orden, catálogo primero, hashes con `hashear_password`, actores por correo — DD-14..DD-16). Verificación: `pytest test/pytest/test_seed.py` pasa.
- [x] 4.3 RED: test de idempotencia (dos corridas dejan el mismo estado lógico) y test de mensaje claro si faltan tablas. Verificación: los tests fallan.
- [x] 4.4 GREEN: ajustar vaciado/mensajes. Verificación: `pytest -rs test/pytest/test_seed.py` con `db` levantada y **0 skipped**; manual: `python seed.py && python seed.py` sin errores y mismo estado.

## 5. Documentación y cierre del relevo

- [x] 5.1 Actualizar `README.md` con los pasos nuevos (`alembic upgrade head`, `python seed.py`, downgrade, cómo recrear la base de test) y dejar claro que el catálogo lo carga el seed. Verificación: seguir el README desde un clon limpio migra, siembra y la app sigue levantando con `/health/ready` en 200.
- [x] 5.2 Correr la suite completa y la revisión de secretos. Verificación: con `db` levantada, `pytest -rs` en verde con **0 skipped**; `git grep -nE 'password *= *["\x27][^"\x27]+|JWT_SECRET *= *["\x27][^"\x27]+'` sin resultados en `seed.py`, migraciones ni `alembic.ini` (las contraseñas de prueba del seed quedan sólo como constantes comentadas en ese archivo).
- [x] 5.3 Marcar `[EJ-2]` como `[x]` en `CHANGES.md` y anotar en `knowledge-base/09_decisiones_y_supuestos.md` cualquier decisión nueva de la implementación (regla D-4). Verificación: el checkbox y las notas están en el diff del commit.

## Workflow follow-up

- `/opsx:archive 02-modelos-migraciones-seed`
- Commit (Conventional Commits) → `bash scripts/sync-memoria.sh` (Windows: `scripts\sync-memoria.bat`) → `git push` (relevo al compañero del EJ-3).
