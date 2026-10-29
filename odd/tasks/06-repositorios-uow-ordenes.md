# Implementación EJ-6 — Repositorios, Unit of Work y órdenes de trabajo

Change activo: `openspec/changes/06-repositorios-uow-ordenes/` (proposal + design + 3 specs + tasks); fuente de verdad funcional. Este archivo sólo registra ejecución, evidencias, rutas y commits. Rama de trabajo: `feat/06-repositorios-uow-ordenes` (desde `main`, base `eeeda3e`). Sin push ni merge sin autorización de entrega. Espejo en engram: `odd/06-repositorios-uow-ordenes/tasks` (proyecto `taller`).

## Objetivo y alcance

Completar el Ejercicio 6 (20 pts): jerarquía de repositorios auditada, `UnitOfWork` base con rollback de commit fallido, repositorios y UoW de `ordenes`, catálogo `estado_orden` de sólo lectura, punto único de stock con guarda, y las rutas `POST/GET /ordenes`, `GET /ordenes/{id}`, `iniciar|terminar|cancelar`, `GET /estados-orden`. Sin migraciones, sin cambios de `seed.py`, sin aviso en segundo plano (EJ-8).

Superficie autorizada del primer tramo (grupos 1-3): `app/core/unit_of_work.py`, `app/modules/**/{unit_of_work,repository}.py`, `app/modules/ordenes/**`, `app/modules/vehiculos/**`, `test/pytest/**`, `test/ordenes.http`, KB `09`, skills, este documento y `tasks.md`. Prohibido en este tramo: `.env`, migraciones, `seed.py`, `CHANGES.md`.

## Restricciones

Reglas duras de `CLAUDE.md` (A-*, B-*, S-*, D-*, E-*); Strict TDD (RED → GREEN → TRIANGULAR → REFACTOR) con pytest + httpx contra PostgreSQL real migrada con Alembic; sin atribución de IA en commits; ~400 líneas autorales por grupo es sólo heurística de planificación.

## Tasks (grupos de `tasks.md` ↔ IDs estables)

- T1 [done] — Grupo 1: preparación y red de seguridad (1.1, 1.2). Ruta: inline (comandos de estado/entorno) + suite completa en segundo plano. Commit: ver Log L4.
  - 1.1: `bash scripts/setup.sh` restauró las skills de dominio (ver L1); leídas `tdd`, `work-unit-commits`, resto aplicadas por rutas de `.agents/skills/`.
  - 1.2: este documento + baseline de la suite completa (L3).
- T2 [ ] — Grupo 2: UoW base y auditoría de la jerarquía (2.1-2.4). Ruta: inline (tareas mecánicas pequeñas, un archivo de producción y su test por tarea).
- T3 [ ] — Grupo 3: repositorios de `ordenes` y reubicación de consultas (3.1-3.4). Ruta: inline (archivos de producción: `ordenes/repository.py`, `ordenes/unit_of_work.py`, `clientes/{repository,unit_of_work,service}`, `ordenes/service.py`).
- T4 [ ] — Grupo 4: catálogo de estados y `GET /estados-orden` (pendiente de otro tramo).
- T5 [ ] — Grupo 5: punto único de stock con guarda (pendiente).
- T6 [ ] — Grupo 6: contratos, alta, listado y detalle (pendiente).
- T7 [ ] — Grupo 7: iniciar y cancelar (pendiente).
- T8 [ ] — Grupo 8: terminar orden RN-13 (pendiente).
- T9 [ ] — Grupo 9: verificación integrada y DoD (pendiente).

Pronóstico de líneas autorales (adiciones + eliminaciones, sin generados): G1 ~60 · G2 ~260 · G3 ~380 · G4 ~220 · G5 ~120 · G6 ~520 · G7 ~300 · G8 ~380 · G9 ~120 → ~2 360 en total. Supera ~400, por lo que la entrega se parte en slices por grupo (estrategia `ask-on-risk`, a decidir con el usuario al preparar el PR; no se pushea en este tramo).

## Criterios de aceptación

C-06 completo, C-10, C-11, C-12 (sin aviso), C-13, C-17 en `test/ordenes.http`; ningún `commit()` fuera del UoW base; ningún `service.py` construye su UoW ni ejecuta SQL; catálogo de sólo lectura sin herencia; suite completa sin regresiones frente al baseline (697 passed + 2 fallos ambientales conocidos).

## Checks aplicables

`pytest` focalizado por tarea; suite completa en cierre de grupo si la tarea lo pide; `openspec validate 06-repositorios-uow-ordenes --strict` al final; `alembic up/down/up` vía `test_migraciones.py`.

## Progreso

Tramo actual: grupos 1-3. Ver Log.

## Evidencia de verificación

- Baseline (antes de la primera escritura de código): **697 passed + 2 failed ambientales conocidos** (`test_salud.py::test_el_503_registra_la_causa_en_el_log_sin_secretos` y `test_fixtures_migradas.py::test_migrar_preserva_el_diagnostico_503_en_la_captura_actual`: reciben `TimeoutError` en lugar de `ConnectionRefusedError`, L2 de EJ-5), 0 skipped, 280 s. Idéntico al baseline conocido de EJ-5.

## Siguiente paso

Cerrar grupos 1-3 y continuar con el grupo 4 en otro tramo.

## Log

- L1: Apertura del tramo. `bash scripts/setup.sh` restauró las 18 skills de dominio en `.agents/skills/` (enlazadas en `.claude/skills/`, 23 en total) y configuró `core.hooksPath=.githooks`; `skills-lock.json` quedó con hashes recalculados distintos (ruido de fin de línea en Windows) y se revirtió con `git checkout` para no ensuciar el commit. El registro `.atl/skill-registry.md` no indexa las skills de dominio: resolución por rutas de `.agents/skills/` (`skill_resolution: fallback-path`, degradada pero auditable).
- L2: Entorno de pruebas ausente en esta máquina al iniciar (clon fresco: sin `.env`, sin paquetes de Python en el intérprete 3.13 global, sin contenedor PostgreSQL del proyecto). Para no tocar `.env` (prohibido en este tramo) se montó un entorno efímero fuera del repo: venv en el scratchpad de la sesión con `requirements.txt` y un contenedor `postgres:16` (`taller-pg-test`, 127.0.0.1:55432, credenciales descartables, bases `taller` y `taller_test`), con las variables pasadas por entorno de proceso (`POSTGRES_*`, `JWT_SECRET`, `BCRYPT_ROUNDS=4`). El puerto 5432 está bloqueado por permisos de Windows (socket no permitido), de ahí el 55432. Nada de esto entra al repo.
- L3: Baseline de la suite completa (sobre PostgreSQL 16 aislada, esquema Alembic): 697 passed + 2 failed ambientales conocidos (mismos nombres que EJ-5 L2), 0 skipped, 4:40 min. Sin tocar umbrales ni pruebas.
