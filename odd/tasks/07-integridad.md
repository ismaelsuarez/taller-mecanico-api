# Implementación EJ-7 — Integridad: sólo agregado, atomicidad del historial e `intento_acceso` auditados

Change activo: `openspec/changes/07-integridad/` (proposal + design D1–D9 + 3 specs + tasks, 23 tareas); fuente de verdad funcional. Este archivo sólo registra ejecución, evidencias, rutas y commits. Rama de trabajo: `feat/07-integridad` (desde `main`, base `532bb6c`). Sin push ni merge sin autorización de entrega. Espejo en engram: `odd/07-integridad/tasks` (proyecto `taller`). Governance **CRITICO** (audit trail).

## Objetivo y alcance

Completar el Ejercicio 7 (10 pts): demostrar y consolidar que el disparador de sólo agregado (migración 2, T-6) rechaza `UPDATE`/`DELETE` en `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` venga de donde venga, con la evidencia C-14 (`test/solo_agregado.sql`, ejecutada por la suite y por `psql`); fijar por prueba que los repositorios de esas tablas sólo agregan; auditar RN-20 (precio e historial en el mismo bloque) y la escritura de `intento_acceso` en su propia sesión como única excepción declarada (C-05); auditar `evento_seguridad` contra DD-26. **Sin migraciones nuevas, sin endpoints, tablas ni columnas** (D1); se corrige sólo lo que la auditoría encuentre.

Superficie autorizada del primer tramo (grupos 1–3): `openspec/changes/07-integridad/tasks.md`, este documento, `test/solo_agregado.sql`, `test/pytest/integridad/**`, `test/pytest/test_migraciones.py`, `test/pytest/test_capas.py`, `test/pytest/conftest.py`, `README.md`, `knowledge-base/09_decisiones_y_supuestos.md`. Prohibido en este tramo: `migrations/**`, `app/**`, `main.py`, `seed.py`, `.env`, `CHANGES.md`, `skills-lock.json`, `.engram/`.

## Restricciones

Reglas duras de `CLAUDE.md` (A-*, B-*, S-*, D-*, E-*); Strict TDD (RED → GREEN → TRIANGULAR → REFACTOR) con pytest + httpx contra PostgreSQL real migrada con Alembic; pruebas de caracterización de comportamiento ya existente se registran como tales con su prueba de sensibilidad (D9), sin inventar un RED; mensajes al usuario en español claro (S-9) y sin secretos (S-6); sin atribución de IA en commits; ~400 líneas autorales por grupo es sólo heurística de planificación.

## Aprobación del plan (tarea 1.1)

El usuario aprobó explícitamente el plan el 2026-10-29 (governance CRITICO), aceptando los valores por defecto de las decisiones abiertas: **D6** (sin traductor global de `IntegrityError`/`CHECK` → 409 en EJ-7 ni EJ-8) y **D7** (los eventos de rol mantienen el **id numérico** como «Y»; se registra como SU nuevo en el grupo 5), y las costuras de prueba de **D9** (RED para `solo_agregado.sql` y el comentario de la excepción; caracterización en verde, cada una con su comprobación de que puede fallar). Registrado en engram (observación 4683, topic `opsx/07-integridad/approval`). No se vuelve a preguntar.

## Pronóstico y entrega

Pronóstico de líneas autorales (adiciones + eliminaciones, sin generados): G1 ~170 (documento ODD; los artefactos del change ya escritos suman ~450 de markdown), G2 ~330, G3 ~320, G4 ~330, G5 ~170, G6 ~120 → **~1 400 en total**, por encima de ~400. Estrategia de entrega: `ask-on-risk` (por defecto); la estrategia de cadena (`stacked-to-main` o `feature-branch-chain`) **no está elegida**: se pregunta al usuario antes de cualquier push/PR. Cada grupo es un commit (work unit) con sus pruebas y docs; límites de slices a decidir con el usuario.

## Tasks (grupos de `tasks.md` ↔ IDs estables)

- T1 [done] — Grupo 1: aprobación, preparación y red de seguridad (1.1, 1.2, 1.3). Ruta: **inline** (estado/entorno, un documento y su espejo) con la suite completa en segundo plano; disparador de delegación: ninguno (no se escribió código de producción; las lecturas de preparación fueron del change y del documento de EJ-6). Commit: ver «Commits de la feature».
  - 1.1: aprobación registrada arriba (engram 4683).
  - 1.2: skills leídas (L1).
  - 1.3: este documento + espejo en engram + baseline de la suite completa (L3).
- T2 [pending] — Grupo 2: evidencia C-14, `test/solo_agregado.sql` verificado por la suite (2.1–2.5). Ruta: **inline** (un SQL, un módulo de prueba y su apoyo, README y KB; el terreno ya estaba mapeado por design D2/D3).
- T3 [pending] — Grupo 3: sólo agregado venga de donde venga (3.1–3.4). Ruta: **inline** (tres archivos de prueba acotados; sin código de producción).
- T4 [pending] — Grupo 4: `intento_acceso` (4.1–4.6) — fuera del tramo actual.
- T5 [pending] — Grupo 5: RN-20 y `evento_seguridad` (5.1–5.3) — fuera del tramo actual.
- T6 [pending] — Grupo 6: verificación integrada y DoD (6.1–6.4) — fuera del tramo actual.

## Evidencia

- Baseline (rama `feat/07-integridad` sin cambios de código): **1010 passed + 2 failed ambientales conocidos** (`test_salud.py::test_el_503_registra_la_causa_en_el_log_sin_secretos` y `test_fixtures_migradas.py::test_migrar_preserva_el_diagnostico_503_en_la_captura_actual`: `TimeoutError` en lugar de `ConnectionRefusedError`, L2 de EJ-5), 0 skipped, 22:03 min (con otra corrida focalizada en paralelo sobre otra base). Idéntico al cierre de EJ-6. Sin tocar umbrales ni pruebas.

## Commits de la feature

Rama `feat/07-integridad` desde `main` (`532bb6c`), de más viejo a más nuevo: (se completa grupo a grupo).

## Siguiente paso

Grupo 2 (evidencia C-14, `test/solo_agregado.sql`).

## Log

- L1: Apertura del tramo. Rama `feat/07-integridad` creada por el orquestador desde `main` limpia. Skills de dominio presentes en `.agents/skills/` (enlazadas en `.claude/skills/`, 23 en total). Leídas realmente (`SKILL.md`): `tdd`, `work-unit-commits`, `supabase-postgres-best-practices`, `python-testing-patterns` (primeras 150 líneas), `alembic` (workflow, reglas y gotchas, líneas 120–265) y `postgresql-table-design` (reglas, restricciones, índices). No cargadas en este tramo (sin código de producción ni de modelos): `sqlalchemy`, `sqlmodel`, `python-error-handling`. El registro `.atl/skill-registry.md` no indexa las skills de dominio: resolución por rutas de `.agents/skills/` (`skill_resolution: fallback-path`, degradada pero auditable).
- L2: Entorno de pruebas fuera del repo (no se toca `.env`): venv en el scratchpad de la sesión y contenedor `postgres:16` `taller-pg-test` (127.0.0.1:55432; el 5432 está bloqueado por permisos de Windows). Para correr pruebas focalizadas **en paralelo** con la suite completa sin que `DROP SCHEMA` de una pise a la otra, se creó una segunda base de test efímera `taller_test2` en el mismo contenedor y se exportó `POSTGRES_TEST_DB=taller_test2` sólo para esas corridas; la suite completa usa la `taller_test` del entorno. Nada de esto entra al repo.
- L3: Baseline de la suite completa (PostgreSQL 16 aislada, esquema Alembic, `pytest -q -rfs`): 1010 passed + 2 failed ambientales conocidos (mismos nombres que EJ-5/EJ-6), 0 skipped, 22:03 min. Reportados como conocidos; no se arreglan ni se tocan sus umbrales.
