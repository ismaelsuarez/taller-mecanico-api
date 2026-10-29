# Design

## Context

Ver `proposal.md` para motivación y alcance; los comportamientos los fijan los deltas de `specs/migraciones-esquema`, `specs/autenticacion-sesiones` y `specs/persistencia-transaccional`. El diseño hace falta por tres razones: governance **CRITICO** (audit trail), una evidencia de entrega que debe poder ejecutarse a mano (`psql`) y por la suite, y una auditoría que en su mayor parte encuentra comportamiento **ya implementado** (lo que cambia cómo se aplica Strict TDD, D9).

| Evidencia actual (observada en el código) | Consecuencia de diseño |
|---|---|
| `migrations/versions/a1b2c3d4e5f6_solo_agregado.py` ya crea la función `solo_agregado()` (`RAISE ... USING ERRCODE = 'restrict_violation'`, mensaje en español) y tres triggers `BEFORE UPDATE OR DELETE ... FOR EACH ROW`; su docstring declara que se escribió a mano y se leyó antes de aplicarla; el `downgrade` borra triggers y función | D1: **no** hay migración nueva (T-6). Se audita y se prueba; el comentario A-3 ya existe en las dos migraciones |
| `test/pytest/test_migraciones.py` prueba `UPDATE ... SET id = id` / `DELETE` sobre filas insertadas a mano y el downgrade sólo hasta `base` (donde las tablas ya no existen, así que no distingue «trigger quitado» de «tabla quitada») | D2/D3: evidencia con filas del seed y de la API; nuevo escenario de `downgrade -1` |
| `seed.py::_vaciar` usa `TRUNCATE ... RESTART IDENTITY CASCADE` y lo justifica: los triggers `FOR EACH ROW` no se disparan con `TRUNCATE` | D2: `TRUNCATE` queda fuera del disparador a propósito (supuesto nuevo) |
| `orden_trabajo.estado` es FK sin nombre explícito → nombre por defecto de PostgreSQL `orden_trabajo_estado_fkey`; `total` tiene `CHECK total >= 0` | D2: el alta de la sentencia 7 lleva valores válidos en todo salvo `estado`, para que el único rechazo posible sea la FK |
| `MovimientoStockRepository`, `HistorialPrecioRepository` y `HistorialEstadoOrdenRepository` son clases planas con sólo `add` (y lecturas); sólo el último tiene prueba de «sin `update`/`delete`» (EJ-6 3.3) | D8: prueba de inspección para los tres |
| `repuestos/service.py::actualizar_repuesto` cambia precio y agrega la línea con `add_si_hubo_cambio` en el mismo `async with uow`; `test_atomicidad_bloques.py::test_falla_al_escribir_el_historial_no_deja_el_precio_nuevo` y C-18 en `test/repuestos.http` ya lo cubren | D8: RN-20 sin cambio de código; sólo se suma un bloque `.http` |
| `usuarios/router.py::get_session_intentos` abre `request.app.state.fabrica_sesiones()`; el único otro lugar es `core/database.py::get_session`. Comentarios actuales: «otra sesión/transacción… Sus intentos confirmados sobreviven al rollback de la petición normal» y, en el servicio, «confirma en otra transacción/conexión incluso ante rechazo o rollback normal» | D5: el costo no está dicho con las palabras de la consigna («deja filas aunque la petición falle») ni se afirma que sea la única excepción → se reescriben los comentarios y se fija por prueba |
| `service.iniciar_sesion` confirma el intento en los tres desenlaces (200, 401, 429) antes de devolver o lanzar; en el 429 confirma el intento **antes** del evento del UoW normal. `test/pytest/auth/test_intentos.py` y `test_login.py` ya prueban independencia, rollback y persistencia | D5: no se cambia el flujo; se agrega la prueba de C-05 que cuenta las seis filas desde otra sesión |
| Acciones de `evento_seguridad` en el código: registro (`service.py:123`), cambio de contraseña (`:91`), 429 (`:148`), alta de personal (`:204`), rol asignado/revocado (`:248`, `:275`, con el **id** numérico como «Y»), datos iniciales (`seed.py:241`) | D7: coinciden con DD-26; la «Y» la fija un supuesto. `knowledge-base/04_modelo_de_datos.md` y RT-SE-10 no mencionan el evento del 429 que DD-26 y RT-EQ-06 sí incluyen → conciliar la KB |

## Goals / Non-Goals

**Goals:** que la corrección del criterio «Integridad» (10 %) encuentre, ejecutable y con evidencia guardada, el disparador en las tres tablas, el historial de precios en la misma transacción y el intento de acceso en su propia sesión; que cada hallazgo de la auditoría quede corregido o registrado como decisión/supuesto (D-4), sin ampliar el alcance en silencio.

**Non-Goals:** nuevas migraciones, tablas, columnas o endpoints; permisos por rol de base (DD-06); control de concurrencia del stock y traductor global de `IntegrityError` (D6); bloquear `TRUNCATE` (D2); `BackgroundTasks` y C-15 (EJ-8).

## Decisions

### D1 — Consolidar, no recrear el disparador

El change no escribe una migración nueva ni toca las dos existentes: T-6 asigna la creación a EJ-2 y la consigna evalúa «el disparador de la segunda migración». Se audita el archivo (comentario de lectura previa A-3 presente en ambas migraciones, `downgrade` como inverso exacto) y se ejercita con el ciclo `upgrade head → downgrade base → upgrade head` del DoD más el nuevo `downgrade -1`.
**Alternativa descartada**: reescribir la migración 2 (p. ej. para cubrir `TRUNCATE` o nombrar la FK). Cambiaría una migración ya aplicada en el repositorio compartido y en las bases del equipo sin que la consigna lo pida.
**Conflicto registrado**: el pedido de planificación mencionaba «la segunda migración escrita a mano» como entregable de este change; `CHANGES.md` (T-6, scope de EJ-7) prevalece: ya existe y no se recrea.

### D2 — Forma de `test/solo_agregado.sql`

- Encabezado con precondición (`python seed.py` antes), comandos de ejecución para venv (`psql -h ... -U ... -d ... -a -f test/solo_agregado.sql`) y Docker (`docker compose exec -T db psql -U ... -d ... -a < test/solo_agregado.sql`), sin credenciales (variables de entorno, S-6). `-a` hace que la salida muestre cada sentencia junto a su error: es la evidencia.
- `\set ON_ERROR_STOP off` explícito y autocommit de `psql`: cada sentencia es su propia transacción, así un rechazo no aborta las siguientes.
- Las seis sentencias apuntan a filas **existentes** del seed (`WHERE id = 1` en las tres tablas: historial de estado de la orden 1, movimiento «Stock inicial» del filtro, línea 8000 → 8500 del filtro) con cambios realistas (`SET hasta_estado = 'CANCELADA'`, `SET cantidad = 99`, `SET precio_nuevo = 1`). Un `UPDATE`/`DELETE` que no encuentra filas **no** dispara un trigger `FOR EACH ROW` y terminaría en «0 filas» sin rechazo: por eso la precondición y el `id` fijo.
- Sentencia 7: `INSERT INTO orden_trabajo (vehiculo_id, estado, falla, creada_en, total) VALUES (1, 'INEXISTENTE', ..., now(), 0)` — todo válido salvo `estado`, de modo que sólo puede fallar la FK `orden_trabajo_estado_fkey` (el mensaje exacto depende del idioma del servidor; el comentario esperado cita el nombre de la restricción y el `SQLSTATE` 23503).
- Cierre con un `SELECT` de conteos de las cuatro tablas para mostrar en la captura que nada cambió.
- `TRUNCATE` no está cubierto: el disparador es por fila y la consigna pide `UPDATE` y `DELETE`; el seed depende de `TRUNCATE` para recargar. Un superusuario también puede desactivar triggers (`session_replication_role = replica`); el TP usa un solo rol y DD-06 acepta ese límite. Ambos se registran como supuesto (SU nuevo), no se corrigen.

### D3 — La suite ejecuta el mismo archivo

`test/pytest/integridad/test_solo_agregado_sql.py` lee `test/solo_agregado.sql`, descarta líneas de comentario (`--`) y metacomandos de `psql` (`\`), separa por `;` de fin de sentencia y ejecuta cada una en su propia transacción sobre `base_migrada` sembrada con `seed.sembrar`. Afirma el `SQLSTATE` del error original: `23001` (restrict_violation) en las seis primeras y `23503` (foreign_key_violation) en la séptima, y que los conteos/valores no cambiaron. Así la evidencia manual y la automática no pueden divergir. Regla del archivo para que el parser simple alcance: sin `;` dentro de literales y una sentencia por bloque.
**Alternativa descartada**: invocar el binario `psql` desde pytest. Agrega una dependencia del cliente en la máquina/CI; la ejecución manual ya produce la evidencia visual.

### D4 — Evidencia guardada

Se versiona la salida textual de `psql -a` en `docs/evidencias/C-14-solo-agregado.txt` (producida por el agente en el apply, contra la base de test sembrada). La **captura de pantalla** que pide la entrega la toma una persona al ejecutar el mismo comando; el README explica cómo y dónde guardarla. No se inventa una captura.

### D5 — `intento_acceso`: comentario exacto y prueba de exclusividad

- Comentarios reescritos (sin cambio de comportamiento) en `get_session_intentos`, `UnitOfWorkIntentoAcceso` y en el punto de `iniciar_sesion` donde se confirma: «Única escritura del sistema que no comparte la transacción de su petición (consigna Ej. 7, RT-SE-09, DD-05/DD-19): el fallo que se quiere contar es el mismo que revierte la petición. Costo: deja filas aunque la petición falle, y usa otra conexión.»
- Prueba de inspección por AST en `test/pytest/test_capas.py`: las únicas llamadas a `fabrica_sesiones(` en `app/` y `main.py` están en `get_session` y `get_session_intentos`, y `get_session_intentos` sólo se usa para construir `UnitOfWorkIntentoAcceso`. Se acompaña de un test del detector sobre un archivo temporal (patrón de `test_el_detector_de_commit_ve_una_llamada_real`) para que no sea una afirmación vacía. La prueba del comentario busca las frases clave en esos tres lugares.
- Prueba HTTP de C-05 en `test/pytest/integridad/`: seis logins fallidos del mismo correo/IP; desde una sesión observadora, seis filas nuevas `exito=false` en orden y un único evento de bloqueo.
- Sin cambio de flujo. Supuesto nuevo: si falla algo interno **antes** de conocer el resultado (búsqueda del usuario o bcrypt), la petición termina en 500 sin fila de intento, porque no hay resultado que anotar; una entrada rechazada por validación (422) tampoco es un intento (ya en la spec vigente).

### D6 — `IntegrityError`/`CHECK` sin traductor global: ni EJ-7 ni EJ-8

La observación de la verificación de EJ-6 (DD-53) es que dos terminaciones **simultáneas** podrían esquivar la guarda del punto único y chocar con `CHECK stock >= 0` → 500. No entra en EJ-7: su alcance (CHANGES.md y consigna Ej. 7) es RN-15, RN-20 y `intento_acceso`; la carrera es concurrencia, excluida por DD-08 (cap. 7). Tampoco en EJ-8 (N+1, asincronía, aviso). Además el error del disparador no es alcanzable desde la API: ningún repositorio de las tablas de sólo agregado ofrece modificar o borrar (D8). Se deja como **decisión para el usuario**: un manejador genérico de último recurso `IntegrityError` → 409 con mensaje humano sería defensa en profundidad para S-5, pero es alcance nuevo y podría ocultar errores de programación detrás de un 409; por defecto **no** se agrega.

### D7 — `evento_seguridad` contra DD-26

Las siete acciones coinciden en texto y actor. La «Y» de «Rol X asignado a Y» / «revocado a Y» es el **id numérico** del usuario (EJ-5, ya documentado en `test/autorizacion.http`); DD-26 no la fija. Se registra como supuesto y no se cambia: pasar al correo alteraría un contrato observable de EJ-5 y sus `.http`. La KB se concilia: `04_modelo_de_datos.md` (evento_seguridad) y RT-SE-10 suman el «Login bloqueado por demasiados intentos» que DD-26 y RT-EQ-06 ya incluyen.

### D8 — RN-15 en la capa de aplicación y RN-20 sin cambios

Prueba de inspección: los repositorios de las tres tablas de sólo agregado no definen ni heredan `update`, `delete` ni `soft_delete` (no heredan de `BaseRepository`). RN-20 queda auditado con la prueba de falla inyectada de EJ-6 y C-18; `test/repuestos.http` suma «PATCH con el mismo precio → 200 y sin línea nueva» (RN-20, escenario vigente de `catalogo-repuestos`). La prueba «sólo agregado sobre filas de la API» (spec `migraciones-esquema`) usa la API real: cambio de precio, reposición e inicio de una orden; luego `UPDATE`/`DELETE` por SQL sobre esas filas nuevas.

### D9 — Strict TDD en un change de auditoría

| Prueba | Estado esperado del primer run | Cómo se prueba que puede fallar |
|---|---|---|
| `solo_agregado.sql` ejecutado por pytest | **RED** (el archivo no existe) | — |
| Comentario de excepción y costo | **RED** (frases ausentes) | — |
| Repositorios de sólo agregado sin `update`/`delete` | Caracterización (verde) | Detector sobre una clase temporal con `update` → falla |
| Fábrica de sesiones sólo en dos lugares | Caracterización (verde) | Detector sobre un archivo temporal con una tercera llamada → falla |
| C-05 cuenta seis filas | Caracterización (verde) | Afirmar primero una cantidad equivocada no vale; se registra como caracterización con evidencia del run |
| Filas de la API rechazadas / `downgrade -1` | Caracterización (verde) | En `downgrade -1` la afirmación «UPDATE ya no rechazado» es la contraparte: si el trigger quedara, falla |

Cuando el comportamiento ya existe, no se fabrica un RED: se declara la excepción en el documento ODD con el run observado y la prueba de sensibilidad. Las costuras (seams) a probar son las de la tabla; se confirman con el usuario junto con la aprobación del plan (governance CRITICO).

## Risks / Trade-offs

- [El parser simple de D3 rompe si alguien agrega `;` dentro de un literal o un bloque `DO $$`] → regla escrita en el encabezado del archivo; la prueba falla de forma visible (cantidad de sentencias ≠ 7).
- [El mensaje de la FK sale en otro idioma según `lc_messages`] → la evidencia se valida por `SQLSTATE` y nombre de restricción, no por texto.
- [Correr `solo_agregado.sql` contra la base de desarrollo] → no cambia datos (todas las sentencias se rechazan); el encabezado igual recomienda la base de test.
- [`TRUNCATE` y superusuario esquivan el disparador] → aceptado y registrado (D2); la consigna sólo exige `UPDATE`/`DELETE` y un solo rol.
- [La carrera de dos terminaciones sigue pudiendo dar 500] → aceptado por DD-08/DD-53; decisión del usuario (D6).
- [Las pruebas de caracterización pasan sin haber visto RED] → excepción declarada con prueba de sensibilidad (D9); la verificación independiente la revisa.
- [`downgrade -1` en la fixture deja la base a mitad] → la fixture `base_para_migraciones` ya limpia al salir; la prueba termina con `upgrade head`.

## Migration Plan

Sin migraciones. DoD: `alembic upgrade head → downgrade base → upgrade head` sobre base vacía, `python seed.py`, `test/solo_agregado.sql` con los siete rechazos, `.http` del ejercicio tras `python seed.py`. Rollback: revertir los commits del change (sólo pruebas, comentarios, evidencia y docs).

## Supuestos y decisiones para la KB (D-4, se escriben en el apply)

- **DD nueva** — Consolidación de integridad (EJ-7): sin migración nueva; forma y verificación automática de `test/solo_agregado.sql`; evidencia textual versionada y captura humana (D1–D4).
- **SU nuevo** — `TRUNCATE` y `session_replication_role` no están cubiertos por el disparador; el seed depende de `TRUNCATE` (D2).
- **SU nuevo** — Un error interno antes de conocer el resultado del login no deja fila en `intento_acceso` (D5).
- **SU nuevo** — En «Rol X asignado/revocado a Y», «Y» es el id numérico del usuario (D7).
- **Actualización de DD-53** — EJ-7 reafirma que no hay traductor global de `IntegrityError` (D6), salvo decisión contraria del usuario.
- **Conciliación** — RT-SE-10 y `04_modelo_de_datos.md` (evento_seguridad) con DD-26 (evento del 429).

## Open Questions

- D6: ¿agregar un manejador genérico `IntegrityError` → 409 como defensa en profundidad? Por defecto no; si el usuario lo pide, se suma una tarea al grupo 3 sin cambiar las specs de este change.
- D7: ¿la «Y» de los eventos de rol debería ser el correo en lugar del id? Por defecto se mantiene el id (contrato de EJ-5).
