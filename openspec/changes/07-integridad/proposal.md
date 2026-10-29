# Proposal

## Why

EJ-1..6 están archivados y publicados. El Ejercicio 7 (10 pts, governance **CRITICO**: audit trail) evalúa tres garantías que el código ya construyó en piezas pero que nadie demostró ni auditó como conjunto: el disparador de sólo agregado de la migración 2 (EJ-2, T-6), el historial de precios en la misma transacción (EJ-3/6, RN-20) y la escritura de `intento_acceso` en su propia sesión (EJ-4, T-7). Falta la evidencia de entrega que la consigna exige (`test/solo_agregado.sql` y la captura `psql` de C-14), y la auditoría encontró huecos concretos: el comentario del código no declara con todas las letras la excepción y su costo («deja filas aunque la petición falle»), nada prueba que esa sea la **única** escritura fuera de la transacción de su petición, el downgrade de la migración 2 sólo se prueba hasta `base` (donde las tablas ya no existen) y los repositorios de `movimiento_stock` e `historial_precio_repuesto` no tienen una prueba que fije que sólo agregan.

## What Changes

- **Evidencia C-14**: nuevo `test/solo_agregado.sql`, ejecutable con `psql` después de `python seed.py`: un `UPDATE` y un `DELETE` reales sobre filas existentes de `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (los seis rechazados por el disparador) y el alta de una orden con un estado que no está en el catálogo (rechazada por la clave foránea), cada sentencia con su resultado esperado en un comentario y sin cambiar ningún dato. Una prueba pytest ejecuta **ese mismo archivo** contra PostgreSQL real sembrada y verifica los siete rechazos por su `SQLSTATE`. Se guarda la salida textual de `psql` como evidencia (`docs/evidencias/`) y el README explica cómo producir la captura.
- **Sólo agregado venga de donde venga**: pruebas sobre filas creadas por la API en la misma corrida (no sólo por el seed o por SQL a mano) y una prueba de `downgrade` de **un paso** (de la migración 2 a la 1) que deja las tablas sin disparador ni función y vuelve a instalarlos en el `upgrade`. Sin migraciones nuevas: el disparador no se vuelve a crear (T-6).
- **Repositorios de sólo agregado**: `HistorialEstadoOrdenRepository`, `MovimientoStockRepository` e `HistorialPrecioRepository` quedan fijados por prueba: sólo `add`, sin `update`/`delete` (RN-15 también en la capa de aplicación).
- **RN-20 auditado**: se confirma (con las pruebas existentes de EJ-6 2.4 y C-18) que precio y línea de historial van en un solo bloque; `test/repuestos.http` suma el caso «PATCH con el mismo precio no deja línea».
- **`intento_acceso` auditado (RT-SE-09, DD-05/19)**: comentario del código que declara la excepción de transacción y su costo en el UoW dedicado y en su dependencia; prueba de inspección de que la fábrica de sesiones sólo se abre en `get_session` y en `get_session_intentos`, y de que la segunda sólo alimenta a `UnitOfWorkIntentoAcceso`; prueba HTTP de C-05 que cuenta los cinco fallos (más el sexto bloqueado) en `intento_acceso` desde otra sesión. `test/auth.http` suma la consulta `psql` de verificación de C-05 con el resultado esperado.
- **`evento_seguridad` contra DD-26**: auditoría de las siete acciones; sin cambio de comportamiento salvo que aparezca una diferencia.
- Se corrige sólo lo que la auditoría encuentre; **no se agregan endpoints, tablas, columnas ni migraciones**.

**Fuera de alcance:** control de concurrencia del stock y un traductor global de `IntegrityError`/`CHECK` a 409 (DD-08, DD-53; ver design D6), el segundo mecanismo de sólo agregado por permisos del rol de base (la consigna no lo pide, DD-06), bloquear `TRUNCATE` (el seed lo usa; ver design D2), `BackgroundTasks` y evidencia C-15 (EJ-8).

## Capabilities

### New Capabilities

Ninguna. Las garantías de EJ-7 ya tienen dueño en specs vigentes; este change las completa allí en lugar de crear una capacidad paralela.

### Modified Capabilities

- `migraciones-esquema`: se agrega el requisito de la evidencia C-14 (`test/solo_agregado.sql`: seis rechazos del disparador y uno de la clave foránea, sin efectos) y el ciclo de migraciones suma el escenario de downgrade de un paso que quita disparador y función dejando las tablas.
- `autenticacion-sesiones`: «Intentos persistidos independientemente del resultado» pasa a exigir que sea la única escritura fuera de la transacción de su petición, que el código lo declare junto con su costo, y que C-05 deje los cinco fallos observables en `intento_acceso`.
- `persistencia-transaccional`: se agrega el requisito de que los repositorios de las tres tablas de sólo agregado sólo ofrezcan `add`.

## Impact

- **Código**: comentarios en `app/modules/usuarios/{router,unit_of_work,service}.py` (sin cambio de comportamiento previsto). Cualquier otra corrección sale de la auditoría y se registra antes de escribirla.
- **Persistencia**: sin migraciones ni cambios en `seed.py`; se usan las dos migraciones de EJ-2 tal como están.
- **Pruebas/entregables**: nuevo `test/solo_agregado.sql`; ampliación de `test/auth.http` (C-05) y `test/repuestos.http` (C-18/RN-20); pytest nuevo en `test/pytest/integridad/` y ampliación de `test/pytest/test_migraciones.py` y `test/pytest/test_capas.py`; evidencia textual en `docs/evidencias/`.
- **Documentación**: README (cómo correr `solo_agregado.sql` y capturar C-14), KB `09_decisiones_y_supuestos.md` (DD/SU nuevas, D-4) y conciliación de RT-SE-10 / `04_modelo_de_datos.md` con DD-26.
- **Riesgo**: CRITICO (audit trail). La implementación arranca sólo con aprobación humana explícita del plan; cierre con verificación independiente.
- **Aceptación**: C-14 completo, C-05 (cinco fallos en `intento_acceso`), C-18 (atomicidad del cambio de precio); `alembic upgrade head → downgrade base → upgrade head` y `python seed.py` en verde.
- **Fuentes**: `docs/TP_Cap1a6_Consigna.pdf` (Ejercicio 7, C-14, evidencia de entrega, criterio «Integridad» 10 %), `CHANGES.md` (EJ-7, T-6, T-7), KB 04/05/09/11; DD-05, DD-06, DD-08, DD-19, DD-26, DD-46, DD-53.
