# Implementación EJ-6 — Repositorios, Unit of Work y órdenes de trabajo

Change activo: `openspec/changes/06-repositorios-uow-ordenes/` (proposal + design + 3 specs + tasks); fuente de verdad funcional. Este archivo sólo registra ejecución, evidencias, rutas y commits. Rama de trabajo: `feat/06-repositorios-uow-ordenes` (desde `main`, base `eeeda3e`). Sin push ni merge sin autorización de entrega. Espejo en engram: `odd/06-repositorios-uow-ordenes/tasks` (proyecto `taller`).

## Objetivo y alcance

Completar el Ejercicio 6 (20 pts): jerarquía de repositorios auditada, `UnitOfWork` base con rollback de commit fallido, repositorios y UoW de `ordenes`, catálogo `estado_orden` de sólo lectura, punto único de stock con guarda, y las rutas `POST/GET /ordenes`, `GET /ordenes/{id}`, `iniciar|terminar|cancelar`, `GET /estados-orden`. Sin migraciones, sin cambios de `seed.py`, sin aviso en segundo plano (EJ-8).

Superficie autorizada del primer tramo (grupos 1-3): `app/core/unit_of_work.py`, `app/modules/**/{unit_of_work,repository}.py`, `app/modules/ordenes/**`, `app/modules/vehiculos/**`, `test/pytest/**`, `test/ordenes.http`, KB `09`, skills, este documento y `tasks.md`. Prohibido en este tramo: `.env`, migraciones, `seed.py`, `CHANGES.md`.

## Restricciones

Reglas duras de `CLAUDE.md` (A-*, B-*, S-*, D-*, E-*); Strict TDD (RED → GREEN → TRIANGULAR → REFACTOR) con pytest + httpx contra PostgreSQL real migrada con Alembic; sin atribución de IA en commits; ~400 líneas autorales por grupo es sólo heurística de planificación.

## Tasks (grupos de `tasks.md` ↔ IDs estables)

- T1 [done] — Grupo 1: preparación y red de seguridad (1.1, 1.2). Ruta: inline (comandos de estado/entorno) + suite completa en segundo plano. Commit `532d109`.
  - 1.1: `bash scripts/setup.sh` restauró las skills de dominio (ver L1); leídas `tdd`, `work-unit-commits`, resto aplicadas por rutas de `.agents/skills/`.
  - 1.2: este documento + baseline de la suite completa (L3).
- T2 [done] — Grupo 2: UoW base y auditoría de la jerarquía (2.1-2.4). Ruta: inline (tareas mecánicas pequeñas, un archivo de producción y su test por tarea). Commit `a985925`.
  - 2.1: `TestCommitFallido` (5 UoW × 2 errores): RED 6 fallos (Base/Cliente/Repuesto, `in_transaction` seguía abierta) → GREEN con el rollback del commit fallido en `UnitOfWork.__aexit__`; overrides de `UnitOfWorkUsuario`/`UnitOfWorkIntentoAcceso` eliminados (esos 4 casos ya pasaban antes y siguen en verde); `test/pytest/auth/` íntegro en verde.
  - 2.2: `test/pytest/test_capas.py` (AST): único `commit(` en el UoW base, servicios no construyen UoW, routers sin SQL (pasan); servicios sin SQL falla hoy por `ordenes/service.py::_es_dueno_del_vehiculo` (RED observado) y queda `xfail(strict=True)` hasta 3.2. `app/modules/health/router.py` (`SELECT 1` de readiness) queda fuera: no es módulo con datos.
  - 2.3: `TestJerarquiaAuditada` (firma `(sesion, modelo)`, seis métodos async, base sin borrado lógico, subclase con `get_by_id_including_deleted`/`soft_delete`, `add` con id y deshecho al revertir × 2 entidades). Auditoría de código existente: pasan de inmediato (RED no aplica; sin cambios de producción en `repository.py`).
  - 2.4: `test_atomicidad_bloques.py`: RN-02 (falla en `eventos.add` y en `clientes.add` → 0 filas) y RN-20 (falla en el historial con 2 conjuntos de datos → precio y descripción intactos, 0 líneas) con controles de éxito. Auditoría: ya estaban en un bloque; pasan de inmediato.
- T3 [done] — Grupo 3: repositorios de `ordenes` y reubicación de consultas (3.1-3.4). Ruta: inline (cada tarea toca un archivo de producción central más pequeños cableados; sin exploración extra). Commit: ver Log L6.
  - 3.1: `test_repositorio_ordenes.py` (11 casos): RED `AttributeError` ×11 → GREEN con `es_dueno_del_vehiculo` y `tiene_abiertas_del_vehiculo`; triangulado dueño/ajeno/sin ficha/inexistente/vehículo de baja y 7 combinaciones de estados finales/no finales + vehículo ajeno.
  - 3.2: `test_reubicacion_consultas.py` (8) + quitado el `xfail` de `test_capas.py` (RED observado: `ordenes/service.py:58 .execute()`/`select()`): `es_personal_o_dueno` usa el repositorio, `UnitOfWorkCliente.ordenes`, `borrar_vehiculo` usa `tiene_abiertas_del_vehiculo`, `VehiculoRepository.tiene_ordenes_abiertas` eliminado. Capas en verde; `test_clientes_vehiculos.py` (RN-16, C-19) y `autorizacion/` sin cambios de contrato.
  - 3.3: `test_repositorios_detalle.py` (6): `ItemOrdenRepository`, `HistorialEstadoOrdenRepository` (sólo `add`) y `get_detalle_con_items_e_historial`; precarga comprobada con `expunge_all()` (sin carga perezosa; repuesto dado de baja incluido); mutación sin `populate_existing` hace fallar la prueba del mismo bloque (evidencia de sensibilidad).
  - 3.4: `test_unit_of_work_orden.py` (8): `UnitOfWorkOrden` compone `ordenes`, `items`, `historial`, `estados`, `vehiculos`, `repuestos` con la misma sesión. **Observación de orden de tareas**: 3.4 exige `estados`, pero `EstadoOrdenRepository` es la tarea 4.1; se creó sólo el esqueleto (constructor, sin lecturas ni herencia de `BaseRepository`) y las lecturas/pruebas de sólo lectura quedan para 4.1.
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

Tramo actual: grupos 1-3, cerrados (ver Log L4-L6). Progreso OpenSpec: 10/31 tareas.

## Evidencia de verificación

- Cierre del grupo 3: suite completa **762 passed + 2 failed ambientales conocidos**, 0 skipped (L6). Focalizadas del grupo: `test/pytest/ordenes` 33 passed; `test_repositorios_uow.py` + `test_atomicidad_bloques.py` + `test_capas.py` + `auth/` 291 passed.
- Baseline (antes de la primera escritura de código): **697 passed + 2 failed ambientales conocidos** (`test_salud.py::test_el_503_registra_la_causa_en_el_log_sin_secretos` y `test_fixtures_migradas.py::test_migrar_preserva_el_diagnostico_503_en_la_captura_actual`: reciben `TimeoutError` en lugar de `ConnectionRefusedError`, L2 de EJ-5), 0 skipped, 280 s. Idéntico al baseline conocido de EJ-5.

## Siguiente paso

Grupo 4 (T4): `EstadoOrdenRepository` con lecturas, `EstadoOrdenCodigo`/`EstadoOrdenLectura` y `GET /estados-orden` + bloque C-17 de `test/ordenes.http`.

## Log

- L1: Apertura del tramo. `bash scripts/setup.sh` restauró las 18 skills de dominio en `.agents/skills/` (enlazadas en `.claude/skills/`, 23 en total) y configuró `core.hooksPath=.githooks`; `skills-lock.json` quedó con hashes recalculados distintos (ruido de fin de línea en Windows) y se revirtió con `git checkout` para no ensuciar el commit. El registro `.atl/skill-registry.md` no indexa las skills de dominio: resolución por rutas de `.agents/skills/` (`skill_resolution: fallback-path`, degradada pero auditable).
- L2: Entorno de pruebas ausente en esta máquina al iniciar (clon fresco: sin `.env`, sin paquetes de Python en el intérprete 3.13 global, sin contenedor PostgreSQL del proyecto). Para no tocar `.env` (prohibido en este tramo) se montó un entorno efímero fuera del repo: venv en el scratchpad de la sesión con `requirements.txt` y un contenedor `postgres:16` (`taller-pg-test`, 127.0.0.1:55432, credenciales descartables, bases `taller` y `taller_test`), con las variables pasadas por entorno de proceso (`POSTGRES_*`, `JWT_SECRET`, `BCRYPT_ROUNDS=4`). El puerto 5432 está bloqueado por permisos de Windows (socket no permitido), de ahí el 55432. Nada de esto entra al repo.
- L3: Baseline de la suite completa (sobre PostgreSQL 16 aislada, esquema Alembic): 697 passed + 2 failed ambientales conocidos (mismos nombres que EJ-5 L2), 0 skipped, 4:40 min. Sin tocar umbrales ni pruebas.
- L4: Grupo 1 commiteado como `532d109` (artefactos del change, documento ODD, baseline).
- L5: Grupo 2 commiteado como `a985925`. Hallazgo: `app/modules/health/router.py` ejecuta `SELECT 1` sobre la sesión (sonda de readiness); no es un módulo con datos y queda fuera de la inspección de capas (DD-51 punto 5).
- L6: Grupo 3 cerrado. Suite completa tras el grupo: **762 passed + los 2 failed ambientales conocidos** (mismos nombres que el baseline), 0 skipped, 4:16 min; +65 pruebas nuevas respecto de 697, cero regresiones. Registrada DD-51 en `knowledge-base/09_decisiones_y_supuestos.md` (D-4). Observación de orden de tareas: 3.4 compone `estados` antes de que 4.1 cree el repositorio; se dejó sólo el esqueleto y 4.1 agrega lecturas y pruebas de sólo lectura.
