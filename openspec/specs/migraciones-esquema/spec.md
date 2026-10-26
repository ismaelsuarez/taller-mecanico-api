# migraciones-esquema Specification

## Purpose
Garantiza que el esquema de la base se cree y modifique exclusivamente con Alembic en su plantilla asincrónica, con una migración autogenerada para las tablas y una segunda migración escrita a mano que instala el disparador de sólo agregado sobre las tres tablas de auditoría; sin credenciales en la configuración de migraciones y con el ciclo completo upgrade/downgrade/upgrade.

## Requirements

### Requirement: Esquema creado sólo con Alembic

El esquema MUST crearse únicamente mediante migraciones de Alembic. MUST NO usarse `create_all` en ningún punto del ciclo de vida de la aplicación ni del seed. La plantilla de Alembic MUST ser la asincrónica.

#### Scenario: create_all no se usa
- **WHEN** se busca en el código de la aplicación y del seed la llamada a `create_all`
- **THEN** no hay resultados

#### Scenario: Plantilla asincrónica
- **WHEN** se revisa la configuración de Alembic (`migrations/env.py`)
- **THEN** usa el patrón asincrónico (motor y conexión asíncronos)

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

`alembic upgrade head` sobre una base vacía, seguido de `alembic downgrade base` y de un `upgrade head` nuevo, MUST funcionar sin errores y dejar el mismo esquema en ambos upgrades. El downgrade MUST eliminar también el disparador y su función.

#### Scenario: Upgrade, downgrade, upgrade
- **WHEN** se ejecutan en secuencia `alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head` sobre una base vacía
- **THEN** los tres comandos terminan sin error y el esquema final es idéntico al del primer upgrade

#### Scenario: Downgrade limpia el disparador
- **WHEN** se ejecuta `alembic downgrade base` después de las dos migraciones
- **THEN** la función y el disparador de sólo agregado ya no existen en la base

### Requirement: Configuración de migraciones sin credenciales

`alembic.ini` y los archivos de la plantilla MUST NOT contener credenciales de la base. La URL de conexión MUST obtenerse desde la misma configuración de la aplicación (variables de entorno / `.env`).

#### Scenario: alembic.ini sin secretos
- **WHEN** se revisa `alembic.ini`
- **THEN** no contiene usuario, contraseña ni URL de la base con credenciales

#### Scenario: URL desde Settings
- **WHEN** se ejecuta una migración con las variables de entorno del proyecto definidas
- **THEN** Alembic se conecta usando la URL armada desde `POSTGRES_*` / `Settings`
