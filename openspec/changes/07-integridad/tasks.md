# Tasks

Plan de ejecución de `/opsx:apply 07-integridad`. Las casillas se marcan sólo con evidencia observada y registrada en `odd/tasks/07-integridad.md` (y su espejo en engram, topic `odd/07-integridad/tasks`). Referencias: [spec migraciones](specs/migraciones-esquema/spec.md), [spec autenticación](specs/autenticacion-sesiones/spec.md), [spec persistencia](specs/persistencia-transaccional/spec.md) y [diseño](design.md), decisiones D1–D9.

**Governance CRITICO** (audit trail, `CHANGES.md`): no se escribe código hasta que el usuario apruebe explícitamente este plan (tarea 1.1).

**Strict TDD por comportamiento**: RED (pytest + httpx contra PostgreSQL real migrada con Alembic, que falla por la razón correcta) → GREEN (mínimo, ejecutado) → TRIANGULAR (otro caso con otros datos) → REFACTOR (en verde tras cada paso). Donde el comportamiento ya existe (pruebas de caracterización, design D9) no se fabrica un RED: se registra la excepción con el run observado y su prueba de sensibilidad. Antes de modificar archivos existentes se corren sus pruebas como red de seguridad y se anota el baseline; un fallo previo se reporta como preexistente.

**Unidades de trabajo**: cada grupo 2–5 es un commit Conventional Commit con sus pruebas y documentación (`test(07-integridad): ...`, `docs(07-integridad): ...`, `fix(07-integridad): ...` si la auditoría encuentra un defecto), sin atribución de IA, en la rama del change. ~400 líneas autorales por grupo es sólo una heurística de planificación. Los `.http` siguen D-3 (un bloque por caso `C-xx`, respuesta esperada en comentario, sesiones con `# @name` + `# @no-cookie-jar` + `Cookie:`), corridos tras `python seed.py`. Ninguna migración nueva (D1).

## 1. Aprobación, preparación y red de seguridad

- [x] 1.1 Presentar el plan al usuario y obtener aprobación explícita (governance CRITICO), incluidas las costuras de prueba de D9 y los valores por defecto de las decisiones abiertas: D6 (sin traductor global de `IntegrityError`) y D7 («Y» = id del usuario en los eventos de rol). Verificación: respuesta del usuario registrada en el documento ODD; si elige otra opción en D6/D7, actualizar design/tasks con `/opsx:update` antes de seguir.
- [x] 1.2 Restaurar/cargar las skills del registro `.atl/skill-registry.md` que aplican (`alembic`, `sqlalchemy`, `sqlmodel`, `supabase-postgres-best-practices`, `postgresql-table-design`, `python-error-handling`, `tdd`, `python-testing-patterns`, `work-unit-commits`); verificar que sus `SKILL.md` existen en `.claude/skills/` (o `.agents/skills/`) o anotar la resolución degradada.
- [x] 1.3 Crear `odd/tasks/07-integridad.md` (objetivo, tareas con IDs estables, ruta por tarea inline/delegada con la evidencia del disparador de delegación, pronóstico de líneas, estrategia de entrega) y su espejo en engram; correr la suite completa sobre la base de test y registrar el baseline (aprobados, omitidos, advertencias conocidas). Verificación: documento leído de vuelta y conteos del run anotados.

## 2. Evidencia C-14: `test/solo_agregado.sql` verificado por la suite

- [x] 2.1 RED: `test/pytest/integridad/test_solo_agregado_sql.py` (con `__init__.py` y fixture que siembra con `seed.sembrar` sobre `base_migrada`) lee `test/solo_agregado.sql` según D3 y espera exactamente 7 sentencias: `SQLSTATE` 23001 en las seis primeras, 23503 en la séptima y conteos/valores sin cambios. Verificación: el run falla porque el archivo no existe.
- [x] 2.2 GREEN: escribir `test/solo_agregado.sql` según D2 (encabezado con precondición y comandos venv/Docker sin credenciales, `\set ON_ERROR_STOP off`, seis `UPDATE`/`DELETE` sobre `id = 1` de las tres tablas con cambios realistas, alta con estado inexistente y valores válidos en lo demás, `SELECT` final de conteos; cada sentencia con su resultado esperado en un comentario). Verificación: la prueba del 2.1 pasa.
- [x] 2.3 TRIANGULAR: caso negativo del detector — con la base migrada **sin sembrar**, las seis sentencias no se rechazan (0 filas) y la prueba lo reporta como precondición incumplida, no como éxito; documentar la regla «sin `;` dentro de literales» en el encabezado. Verificación: ambos casos en verde.
- [x] 2.4 Correr `psql -a -f test/solo_agregado.sql` contra la base de test recién sembrada y guardar la salida en `docs/evidencias/C-14-solo-agregado.txt` (seis errores del disparador, uno de `orden_trabajo_estado_fkey`, conteos sin cambios). Verificación: archivo leído de vuelta con los siete errores.
- [x] 2.5 README: sección «Caso C-14 (sólo agregado)» con los comandos venv/Docker, la precondición `python seed.py`, cómo tomar la captura de pantalla para la entrega y dónde está la evidencia textual. KB (D-4): DD nueva de consolidación de integridad (D1–D4) y SU de `TRUNCATE`/`session_replication_role` en `knowledge-base/09_decisiones_y_supuestos.md`. Verificación: comandos del README ejecutados tal como están escritos; commit del grupo.

## 3. Sólo agregado venga de donde venga (base y aplicación)

- [x] 3.1 Red de seguridad: correr `test/pytest/test_migraciones.py`, `test/pytest/test_capas.py` y `test/pytest/ordenes/` y anotar el baseline.
- [x] 3.2 Caracterización (D9): en `test/pytest/integridad/`, la API cambia un precio, repone stock e inicia una orden; luego `UPDATE` y `DELETE` por SQL sobre cada línea nueva de `historial_precio_repuesto`, `movimiento_stock` e `historial_estado_orden` → rechazados por el disparador (23001) y filas intactas. Triangular con una terminación exitosa (C-12 sin aviso) cuyas filas tampoco se pueden modificar. Verificación: run en verde registrado como caracterización.
- [x] 3.3 `downgrade -1` (spec `migraciones-esquema`, D1): extender el helper `_alembic` de `test_migraciones.py` para retroceder un paso; tras `downgrade -1` las tres tablas existen, no hay triggers `trg_*_solo_agregado` ni función `solo_agregado`, y un `UPDATE` sobre una fila insertada **es admitido**; un `upgrade head` posterior reinstala los tres triggers. Verificación: prueba en verde; la afirmación «UPDATE admitido» es la contraparte que falla si el trigger quedara.
- [x] 3.4 RN-15 en la aplicación (spec `persistencia-transaccional`, D8): prueba de inspección en `test/pytest/test_capas.py` de que los repositorios de las tres tablas de sólo agregado no definen ni heredan `update`, `delete` ni `soft_delete`; sensibilidad con una clase temporal que sí los tenga. Verificación: inspección en verde y detector que falla con la clase temporal; commit del grupo.

## 4. `intento_acceso`: excepción declarada, exclusiva y probada (C-05)

- [x] 4.1 Red de seguridad: correr `test/pytest/auth/` y `test/pytest/test_capas.py` y anotar el baseline.
- [x] 4.2 RED: prueba que busca en `get_session_intentos`, `UnitOfWorkIntentoAcceso` y el punto de confirmación de `iniciar_sesion` las frases de D5 («única escritura … no comparte la transacción de su petición», «deja filas aunque la petición falle»). Verificación: falla con los comentarios actuales.
- [x] 4.3 GREEN: reescribir esos comentarios/docstrings según D5 sin cambiar código ejecutable. Verificación: la prueba del 4.2 pasa y `test/pytest/auth/` sigue igual al baseline.
- [x] 4.4 Caracterización (D9): prueba AST en `test/pytest/test_capas.py` de que `fabrica_sesiones(` sólo se llama en `get_session` y `get_session_intentos`, y que esta última sólo construye `UnitOfWorkIntentoAcceso`; detector sobre un archivo temporal con una tercera apertura → falla. Verificación: ambos resultados observados.
- [x] 4.5 Caracterización C-05 (spec `autenticacion-sesiones`): en `test/pytest/integridad/`, cinco 401 y un 429 con `Retry-After` del mismo correo/IP; desde una sesión observadora, exactamente seis filas nuevas `exito=false` en orden de llegada y un único evento «Login bloqueado por demasiados intentos» con el correo como actor; ningún evento por los 401. Triangular con otro par correo/IP que no se ve afectado. Verificación: run en verde.
- [x] 4.6 `test/auth.http`: después del sexto intento de C-05, bloque de verificación con la consulta `psql` (`SELECT email, ip, exito FROM intento_acceso WHERE email = 'registro-http@example.com' ORDER BY id;`) y el resultado esperado comentado (todas las filas de ese correo hasta ese bloque —el archivo ya anota nueve: ocho fallidas y una exitosa—, con los cinco fallos y el bloqueado posteriores al éxito de preparación). KB (D-4): SU «error interno antes del resultado no deja fila». Verificación: correr `test/auth.http` tras `python seed.py` y la consulta; commit del grupo.

## 5. RN-20 y `evento_seguridad` auditados

- [x] 5.1 Red de seguridad y auditoría RN-20: correr `test/pytest/test_atomicidad_bloques.py` y `test/pytest/test_repuestos.py` y anotar que la falla inyectada al escribir el historial no deja el precio nuevo (D8). Verificación: resultados del run en el documento ODD.
- [x] 5.2 `test/repuestos.http`: bloque «C-18 / RN-20: PATCH con el mismo precio» (200, precio igual) y lectura de `/repuestos/1/precios` sin línea nueva, con respuestas esperadas comentadas. Verificación: correr el archivo tras `python seed.py`.
- [x] 5.3 Auditoría DD-26 (D7): verificar las siete acciones y sus actores contra el código y el seed (registrar archivo:línea en el documento ODD); si aparece una diferencia que no sea la «Y», corregirla con su prueba RED/GREEN. KB (D-4): SU de la «Y» = id del usuario; actualización de DD-53 (EJ-7 reafirma que no hay traductor global, D6); conciliar RT-SE-10 (`05_reglas_de_negocio.md`) y `04_modelo_de_datos.md` (evento_seguridad) con el evento del 429 de DD-26. Verificación: lectura de vuelta de la KB; commit del grupo.

## 6. Verificación integrada y Definition of Done

- [x] 6.1 Suite pytest completa sobre PostgreSQL de test con esquema de Alembic (incluye `upgrade head → downgrade base → upgrade head` y el nuevo `downgrade -1`); comparar con el baseline del 1.3 sin regresiones. Verificación: aprobados/fallidos/omitidos reales registrados.
- [x] 6.2 DoD manual: `alembic upgrade head → downgrade base → upgrade head` sobre base vacía, `python seed.py`, `test/solo_agregado.sql` con los seis rechazos + el de la FK, `test/auth.http` y `test/repuestos.http` (cada uno tras `python seed.py`) y, al final, `python seed.py` deja el estado inicial. Verificación: salidas registradas en el documento ODD.
- [ ] 6.3 Verificación independiente por un agente nuevo (riesgo CRITICO): disparador en las tres tablas también sobre filas de la API, `downgrade -1` limpio, `solo_agregado.sql` sin efectos, comentarios de la excepción y su costo, única escritura fuera de la transacción, cinco fallos de C-05 en `intento_acceso`, RN-20 en un bloque, acciones DD-26, sin migraciones nuevas, sin secretos ni texto interno en errores. Verificación: dictamen registrado sin inventar evidencia; hallazgos bloqueantes reabren su tarea.
- [ ] 6.4 Conciliar proposal/specs/design/tasks con lo observado, README, `env.example` (sin variables nuevas: verificar) y la KB (`09_decisiones_y_supuestos.md`, `10_preguntas_abiertas.md` si surgió una duda); validar con `openspec validate 07-integridad --strict`. Verificación: validación en verde; commit de cierre de documentación.

## Workflow follow-up

- Con la implementación verificada, ejecutar `/opsx:archive 07-integridad` (no forma parte de esta propuesta).
- En el commit de cierre: marcar `[x]` EJ-7 en `CHANGES.md`, guardar la captura de pantalla de C-14 tomada por una persona, correr `bash scripts/sync-memoria.sh` (Windows: `scripts\sync-memoria.bat`) y hacer push sólo con autorización explícita.
- El relevo a EJ-8 (`08-lecturas-sin-n1-asincronia`) requiere EJ-7 archivado, commiteado y empujado.
