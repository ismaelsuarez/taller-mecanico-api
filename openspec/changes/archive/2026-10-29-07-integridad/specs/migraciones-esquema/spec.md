# Spec Delta

## ADDED Requirements

### Requirement: Evidencia reproducible del sólo agregado y del catálogo (C-14)

El proyecto MUST entregar `test/solo_agregado.sql`, ejecutable con `psql` sobre la base recién sembrada, con un `UPDATE` y un `DELETE` sobre filas existentes de cada tabla de sólo agregado (seis sentencias rechazadas por el disparador) y el alta de una orden con un estado ausente del catálogo (rechazada por la clave foránea). Cada sentencia MUST llevar su resultado esperado en un comentario y el archivo MUST NO cambiar ningún dato.

#### Scenario: Seis rechazos del disparador
- **WHEN** se ejecuta `test/solo_agregado.sql` con `psql` después de `python seed.py`
- **THEN** cada uno de los seis `UPDATE`/`DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` termina con el error del disparador (violación de restricción) y no con «0 filas afectadas»

#### Scenario: Rechazo por la clave foránea del catálogo
- **WHEN** el mismo archivo intenta insertar una orden de trabajo con un `estado` que no existe en `estado_orden`
- **THEN** la base la rechaza por la clave foránea de `orden_trabajo.estado` (RN-19), no por el disparador ni por un CHECK

#### Scenario: Sentencias independientes y sin efectos
- **WHEN** termina la ejecución del archivo
- **THEN** cada rechazo ocurrió en su propia transacción (un error no impide evaluar la sentencia siguiente) y las cantidades y valores de las tres tablas de auditoría y de `orden_trabajo` son las mismas que antes de correrlo

#### Scenario: Precondición explícita
- **WHEN** se abre el archivo
- **THEN** su encabezado indica que se corre después de `python seed.py`, contra qué base y con qué comando de `psql` (venv y Docker), y que la captura de su salida es la evidencia C-14 de la entrega

#### Scenario: Verificación automática del mismo archivo
- **WHEN** la suite de pruebas ejecuta las sentencias de `test/solo_agregado.sql` sobre una base PostgreSQL de test migrada y sembrada
- **THEN** las seis primeras fallan con el código de violación de restricción del disparador y la última con el de violación de clave foránea

### Requirement: Sólo agregado sobre filas creadas por la API

El disparador MUST rechazar `UPDATE` y `DELETE` también sobre las filas que la API escribe durante su funcionamiento normal (cambio de precio, reposición y transiciones de órdenes), no sólo sobre las del seed o las insertadas a mano.

#### Scenario: Filas recién escritas por la API
- **WHEN** la API cambia un precio, repone stock y hace avanzar una orden, y luego se intenta un `UPDATE` o un `DELETE` sobre cada línea nueva de historial de precio, movimiento y historial de estado
- **THEN** la base rechaza cada intento con el error del disparador y las líneas quedan intactas

## MODIFIED Requirements

### Requirement: Ciclo completo de migraciones

`alembic upgrade head` sobre una base vacía, seguido de `alembic downgrade base` y de un `upgrade head` nuevo, MUST funcionar sin errores y dejar el mismo esquema en ambos upgrades. El downgrade MUST eliminar también el disparador y su función, y retirar sólo la migración 2 MUST dejar las tablas de la migración 1 sin disparador ni función.

#### Scenario: Upgrade, downgrade, upgrade
- **WHEN** se ejecutan en secuencia `alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head` sobre una base vacía
- **THEN** los tres comandos terminan sin error y el esquema final es idéntico al del primer upgrade

#### Scenario: Downgrade limpia el disparador
- **WHEN** se ejecuta `alembic downgrade base` después de las dos migraciones
- **THEN** la función y el disparador de sólo agregado ya no existen en la base

#### Scenario: Downgrade de un paso retira sólo el disparador
- **WHEN** desde `head` se retrocede únicamente la migración 2 (`alembic downgrade -1`)
- **THEN** las tres tablas de auditoría siguen existiendo, no queda ninguno de los tres disparadores ni la función, y un `UPDATE` sobre esas tablas deja de ser rechazado; un nuevo `alembic upgrade head` vuelve a instalar los tres disparadores
