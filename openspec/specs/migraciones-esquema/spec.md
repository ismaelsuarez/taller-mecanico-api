# migraciones-esquema Specification

## Purpose
Garantiza que el esquema de la base se cree y modifique exclusivamente con Alembic en su plantilla asincrónica, con una migración autogenerada para las tablas y una segunda migración escrita a mano que instala el disparador de sólo agregado sobre las tres tablas de auditoría; sin credenciales en la configuración de migraciones y con el ciclo completo upgrade/downgrade/upgrade.

## Requirements

### Requirement: Esquema creado sólo con Alembic

El esquema MUST crearse únicamente mediante migraciones de Alembic, también en las fixtures de integración de modelos, repositorios y API. MUST NO usarse `create_all` en la aplicación, el seed ni esas fixtures. La plantilla de Alembic MUST ser la asincrónica.

#### Scenario: create_all no se usa
- **WHEN** se busca en el código de la aplicación, del seed y de las fixtures de integración una llamada a `create_all`
- **THEN** no hay resultados

#### Scenario: Integración con el esquema real
- **WHEN** se prepara una fixture PostgreSQL para modelos, repositorios o API
- **THEN** se aplican las migraciones hasta `head`, incluidos los tres disparadores de sólo agregado, sobre una base de test separada de desarrollo

#### Scenario: Plantilla asincrónica
- **WHEN** se revisa la configuración de Alembic (`migrations/env.py`)
- **THEN** usa el patrón asincrónico (motor y conexión asíncronos)

#### Scenario: Migraciones sin interferencia con los registros del llamador
- **WHEN** Alembic se ejecuta dentro de un proceso que ya configuró sus handlers
- **THEN** conserva esos handlers y no deshabilita los loggers existentes; la CLI en un proceso sin configuración conserva los diagnósticos de `alembic.ini`

### Requirement: Migración inicial con todas las tablas

La primera migración MUST crear las 13 tablas con sus columnas, restricciones, índices (incluidos los tres índices únicos parciales y los índices de cada FK) y la tabla `estado_orden` vacía. MUST llevar un comentario que declare que la migración fue leída antes de aplicarla.

#### Scenario: Migración 1 deja el esquema completo
- **WHEN** se ejecuta `alembic upgrade head` sobre una base vacía
- **THEN** las 13 tablas existen con sus restricciones e índices, y `estado_orden` no tiene filas

#### Scenario: Comentario de lectura previa
- **WHEN** se abre el archivo de la migración 1
- **THEN** contiene un comentario que indica que se leyó antes de aplicarla

### Requirement: Disparador de sólo agregado instalado por migración escrita a mano

Una segunda migración, escrita a mano (no autogenerada), MUST crear una función y un disparador sobre `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto` que rechace todo `UPDATE` y `DELETE` sobre esas tablas, venga de donde venga (aplicación, psql u otro rol). MUST llevar un comentario que declare que se leyó antes de aplicarla.

#### Scenario: UPDATE rechazado
- **WHEN** se intenta ejecutar un `UPDATE` sobre cualquiera de las tres tablas de auditoría
- **THEN** la base rechaza la operación con el error del disparador

#### Scenario: DELETE rechazado
- **WHEN** se intenta ejecutar un `DELETE` sobre cualquiera de las tres tablas de auditoría
- **THEN** la base rechaza la operación con el error del disparador

#### Scenario: INSERT permitido
- **WHEN** se inserta una fila nueva en cualquiera de las tres tablas de auditoría
- **THEN** la base la admite

#### Scenario: Disparador sobre filas creadas por la aplicación
- **WHEN** la aplicación (o el seed) ha insertado filas en las tablas de auditoría y luego se intenta un `UPDATE` o `DELETE` sobre esas filas desde psql
- **THEN** la base rechaza la operación

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

### Requirement: Configuración de migraciones sin credenciales

`alembic.ini` y los archivos de la plantilla MUST NOT contener credenciales de la base. La URL de conexión MUST obtenerse desde la misma configuración de la aplicación (variables de entorno / `.env`).

#### Scenario: alembic.ini sin secretos
- **WHEN** se revisa `alembic.ini`
- **THEN** no contiene usuario, contraseña ni URL de la base con credenciales

#### Scenario: URL desde Settings
- **WHEN** se ejecuta una migración con las variables de entorno del proyecto definidas
- **THEN** Alembic se conecta usando la URL armada desde `POSTGRES_*` / `Settings`

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
