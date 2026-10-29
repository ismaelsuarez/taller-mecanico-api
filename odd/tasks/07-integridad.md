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
- T2 [partial: 2.1–2.3 done; 2.4 y 2.5 abiertas] — Grupo 2: evidencia C-14, `test/solo_agregado.sql` verificado por la suite. Ruta: **inline** (un SQL, un módulo de prueba y su apoyo, README y KB; el terreno ya estaba mapeado por design D2/D3; disparador de delegación: ninguno). Commit: ver «Commits de la feature».
  - 2.1 RED: `test/pytest/integridad/test_solo_agregado_sql.py` (+ `_apoyo.py`, `conftest.py` que reutiliza `base_sembrada` de `ordenes/conftest.py`, que corre el `seed.py` real en subproceso en lugar de llamar `seed.sembrar` en el proceso: mismo resultado, sin duplicar la fixture). Primer run: 13 failed (`FileNotFoundError: test/solo_agregado.sql`, la razón correcta) + 1 passed (el lector de comentarios/metacomandos, que no lee el archivo).
  - 2.2 GREEN: `test/solo_agregado.sql` según D2 (encabezado con precondición y comandos venv/Docker sin credenciales, `\set ON_ERROR_STOP off`, seis `UPDATE`/`DELETE` sobre `id = 1`, alta con estado `INEXISTENTE` y valores válidos en lo demás, `SELECT` final de conteos, resultado esperado en un comentario por sentencia). Un ajuste del test: el nombre de la restricción no está en el adaptador de SQLAlchemy sino en la excepción de asyncpg que envuelve (`__cause__`); `_atributo` mira ambas. Run: 15 passed.
  - 2.3 TRIANGULAR: sobre la base migrada **sin sembrar** las seis sentencias terminan con `sqlstate=None` y `filas=0` (el detector puede fallar) y `exigir_precondicion` falla con «Precondición incumplida … python seed.py»; con la base sembrada pero sin la fila de `movimiento_stock`, la precondición acusa esa tabla. Run: 16 passed. Siete casos parametrizados (6 × 23001, 1 × 23503 con `orden_trabajo_estado_fkey`) más el archivo completo (independencia, conteos `3 | 4 | 1 | 2`, datos idénticos antes y después).
  - 2.4 **abierta (bloqueada por superficie)**: la salida de `psql -a` está capturada y verificada (siete errores, conteos sin cambios, L5), pero guardarla en `docs/evidencias/C-14-solo-agregado.txt` queda fuera de la superficie autorizada del tramo (`docs/` no figura). Copia lista en el scratchpad de la sesión (`…/scratchpad/C-14-solo-agregado.txt`); sólo falta crear `docs/evidencias/` y copiarla.
  - 2.5 **parcial**: README «Caso C-14 (sólo agregado)» y KB (DD-55, SU-16) escritos y releídos; no se marca porque los comandos del README no se pudieron ejecutar «tal como están escritos» (no hay `psql` en el host ni servicio `db` de `docker compose` en esta máquina; se ejecutó el equivalente exacto con `docker exec` sobre el contenedor de la base de test, L5) y porque remite al archivo de 2.4.
- T3 [pending] — Grupo 3: sólo agregado venga de donde venga (3.1–3.4). Ruta: **inline** (tres archivos de prueba acotados; sin código de producción).
- T4 [pending] — Grupo 4: `intento_acceso` (4.1–4.6) — fuera del tramo actual.
- T5 [pending] — Grupo 5: RN-20 y `evento_seguridad` (5.1–5.3) — fuera del tramo actual.
- T6 [pending] — Grupo 6: verificación integrada y DoD (6.1–6.4) — fuera del tramo actual.

## Evidencia

- Grupo 2 (RED → GREEN → TRIANGULAR): ver T2. Run final de `test/pytest/integridad/`: 16 passed.
- Baseline (rama `feat/07-integridad` sin cambios de código): **1010 passed + 2 failed ambientales conocidos** (`test_salud.py::test_el_503_registra_la_causa_en_el_log_sin_secretos` y `test_fixtures_migradas.py::test_migrar_preserva_el_diagnostico_503_en_la_captura_actual`: `TimeoutError` en lugar de `ConnectionRefusedError`, L2 de EJ-5), 0 skipped, 22:03 min (con otra corrida focalizada en paralelo sobre otra base). Idéntico al cierre de EJ-6. Sin tocar umbrales ni pruebas.

## Commits de la feature

Rama `feat/07-integridad` desde `main` (`532bb6c`), de más viejo a más nuevo: (se completa grupo a grupo).

## Siguiente paso

Grupo 3 (sólo agregado venga de donde venga).

## Log

- L1: Apertura del tramo. Rama `feat/07-integridad` creada por el orquestador desde `main` limpia. Skills de dominio presentes en `.agents/skills/` (enlazadas en `.claude/skills/`, 23 en total). Leídas realmente (`SKILL.md`): `tdd`, `work-unit-commits`, `supabase-postgres-best-practices`, `python-testing-patterns` (primeras 150 líneas), `alembic` (workflow, reglas y gotchas, líneas 120–265) y `postgresql-table-design` (reglas, restricciones, índices). No cargadas en este tramo (sin código de producción ni de modelos): `sqlalchemy`, `sqlmodel`, `python-error-handling`. El registro `.atl/skill-registry.md` no indexa las skills de dominio: resolución por rutas de `.agents/skills/` (`skill_resolution: fallback-path`, degradada pero auditable).
- L2: Entorno de pruebas fuera del repo (no se toca `.env`): venv en el scratchpad de la sesión y contenedor `postgres:16` `taller-pg-test` (127.0.0.1:55432; el 5432 está bloqueado por permisos de Windows). Para correr pruebas focalizadas **en paralelo** con la suite completa sin que `DROP SCHEMA` de una pise a la otra, se creó una segunda base de test efímera `taller_test2` en el mismo contenedor y se exportó `POSTGRES_TEST_DB=taller_test2` sólo para esas corridas; la suite completa usa la `taller_test` del entorno. Nada de esto entra al repo.
- L3: Baseline de la suite completa (PostgreSQL 16 aislada, esquema Alembic, `pytest -q -rfs`): 1010 passed + 2 failed ambientales conocidos (mismos nombres que EJ-5/EJ-6), 0 skipped, 22:03 min. Reportados como conocidos; no se arreglan ni se tocan sus umbrales.
- L4: `psql 16` no está instalado en el host; la salida de `test/solo_agregado.sql` se tomó con el `psql` del contenedor de la base de test (`docker exec -i … sh -c 'stdbuf -o0 psql -U … -d … -a 2>&1' < test/solo_agregado.sql`) tras `alembic upgrade head` + `python seed.py` sobre `taller_test2`. Hallazgo: al redirigir a un archivo, `psql` entrega stdout (buffer) y stderr (sin buffer) desordenados; con `stdbuf -o0` y `2>&1` dentro del `sh -c` cada error queda junto a su sentencia (documentado en el README). En una terminal no hace falta.
- L5: Salida condensada de la corrida (siete errores, en orden): `ERROR: La tabla historial_estado_orden es de sólo agregado: no se puede modificar ni borrar.` (UPDATE y DELETE), lo mismo para `movimiento_stock` y para `historial_precio_repuesto` (seis en total, `CONTEXT: PL/pgSQL function solo_agregado() line 3 at RAISE`), y `ERROR: insert or update on table "orden_trabajo" violates foreign key constraint "orden_trabajo_estado_fkey"` / `DETAIL: Key (estado)=(INEXISTENTE) is not present in table "estado_orden".`; cierre `3 | 4 | 1 | 2`. La corrida se repitió con la forma del README para Docker (`docker exec -e POSTGRES_TEST_DB=… -i … sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_TEST_DB" -a'`): 7 `ERROR`.
- L6: Decisiones D-4 registradas en la KB `09`: DD-55 (consolidación de integridad, D1–D4) y SU-16 (`TRUNCATE` y `session_replication_role` fuera del disparador). Los SU de los grupos 4 y 5 (`intento_acceso`, «Y» = id) se escriben en sus grupos.
