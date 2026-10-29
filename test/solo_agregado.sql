-- ============================================================================
-- C-14 / EJ-7 — Las tablas de auditoría son de sólo agregado (RN-15, RN-19)
-- ============================================================================
-- Qué demuestra: la base rechaza UPDATE y DELETE sobre historial_estado_orden,
-- movimiento_stock e historial_precio_repuesto (seis sentencias, rechazadas por el
-- disparador de la segunda migración, SQLSTATE 23001) y rechaza el alta de una orden con
-- un estado que no está en el catálogo (una sentencia, rechazada por la clave foránea
-- orden_trabajo_estado_fkey, SQLSTATE 23503). Ninguna sentencia cambia datos.
--
-- PRECONDICIÓN: correr `python seed.py` ANTES (y, antes de eso, `alembic upgrade head`); los tres
-- comandos (alembic, seed y psql) trabajan sobre la base POSTGRES_DB. Un disparador FOR EACH ROW
-- no se ejecuta si el UPDATE/DELETE no encuentra filas: sobre una base sin sembrar las seis
-- primeras sentencias terminarían en «0 filas» sin rechazo, y eso NO sería evidencia. Todas
-- apuntan a la fila id = 1 de cada tabla, que existe tras el seed. Se recomienda apuntar
-- POSTGRES_DB a la base de test; sobre la de desarrollo tampoco cambia datos.
--
-- CÓMO CORRERLO (-a muestra cada sentencia junto a su error: esa salida es la evidencia):
--   Docker Compose del equipo (el servicio db ya tiene las variables del .env):
--     docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -a' < test/solo_agregado.sql
--   Contenedor de PostgreSQL sin compose (PG_CONTENEDOR = su nombre en `docker ps`; no hace falta psql en el host):
--     docker exec -e POSTGRES_DB -i "$PG_CONTENEDOR" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -a' < test/solo_agregado.sql
--   psql instalado en el host (la contraseña sale de PGPASSWORD; no va en este archivo):
--     psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -a -f test/solo_agregado.sql
--
-- EVIDENCIA DE ENTREGA: la captura de pantalla de esa salida es la evidencia C-14. La salida
-- textual de referencia está en docs/evidencias/C-14-solo-agregado.txt.
--
-- REGLAS DE ESTE ARCHIVO (la prueba pytest lo lee con un separador simple): los comentarios
-- ocupan líneas enteras, no hay `;` dentro de literales y cada sentencia termina en `;`.
-- La prueba test/pytest/integridad/test_solo_agregado_sql.py ejecuta exactamente estas sentencias.
-- ============================================================================

-- Sin esto, un error cortaría el resto del script: cada sentencia es su propia transacción
-- (autocommit de psql) y un rechazo no impide evaluar la siguiente.
\set ON_ERROR_STOP off

-- ---------------------------------------------------------------------------
-- 1. UPDATE sobre historial_estado_orden (la línea de la orden 1)
-- Esperado: ERROR  La tabla historial_estado_orden es de sólo agregado: no se puede modificar ni borrar.  (SQLSTATE 23001, disparador)
UPDATE historial_estado_orden SET hasta_estado = 'CANCELADA' WHERE id = 1;

-- 2. DELETE sobre historial_estado_orden
-- Esperado: ERROR  La tabla historial_estado_orden es de sólo agregado: no se puede modificar ni borrar.  (SQLSTATE 23001, disparador)
DELETE FROM historial_estado_orden WHERE id = 1;

-- 3. UPDATE sobre movimiento_stock (el «Stock inicial» del filtro)
-- Esperado: ERROR  La tabla movimiento_stock es de sólo agregado: no se puede modificar ni borrar.  (SQLSTATE 23001, disparador)
UPDATE movimiento_stock SET cantidad = 99 WHERE id = 1;

-- 4. DELETE sobre movimiento_stock
-- Esperado: ERROR  La tabla movimiento_stock es de sólo agregado: no se puede modificar ni borrar.  (SQLSTATE 23001, disparador)
DELETE FROM movimiento_stock WHERE id = 1;

-- 5. UPDATE sobre historial_precio_repuesto (la línea 8000 a 8500 del filtro)
-- Esperado: ERROR  La tabla historial_precio_repuesto es de sólo agregado: no se puede modificar ni borrar.  (SQLSTATE 23001, disparador)
UPDATE historial_precio_repuesto SET precio_nuevo = 1 WHERE id = 1;

-- 6. DELETE sobre historial_precio_repuesto
-- Esperado: ERROR  La tabla historial_precio_repuesto es de sólo agregado: no se puede modificar ni borrar.  (SQLSTATE 23001, disparador)
DELETE FROM historial_precio_repuesto WHERE id = 1;

-- 7. Alta de una orden con un estado que no existe en el catálogo estado_orden (RN-19).
-- Todo lo demás es válido (vehículo 1 del seed, total >= 0): sólo puede fallar la clave foránea.
-- Esperado: ERROR  insert or update on table "orden_trabajo" violates foreign key constraint "orden_trabajo_estado_fkey"  (SQLSTATE 23503, clave foránea; el texto exacto depende del idioma del servidor)
INSERT INTO orden_trabajo (vehiculo_id, estado, falla, creada_en, total)
VALUES (1, 'INEXISTENTE', 'Alta con un estado que no está en el catálogo', now(), 0);

-- ---------------------------------------------------------------------------
-- Cierre: las cantidades no cambiaron. Para la captura: este SELECT es lo último que se ve.
-- Esperado (base recién sembrada): historial_estado_orden = 3, movimiento_stock = 4, historial_precio_repuesto = 1, orden_trabajo = 2
SELECT
    (SELECT count(*) FROM historial_estado_orden) AS historial_estado_orden,
    (SELECT count(*) FROM movimiento_stock) AS movimiento_stock,
    (SELECT count(*) FROM historial_precio_repuesto) AS historial_precio_repuesto,
    (SELECT count(*) FROM orden_trabajo) AS orden_trabajo;
