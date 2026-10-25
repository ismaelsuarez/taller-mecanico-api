# configuracion-aplicacion Specification

## Purpose

Define cómo la aplicación obtiene su configuración del entorno, qué valores son obligatorios y cómo se protegen los secretos, de modo que el proyecto nunca contenga credenciales y que las sesiones sobrevivan a los reinicios.

## Requirements

### Requirement: Configuración leída del entorno

La aplicación MUST leer su configuración desde variables de entorno o desde un archivo `.env` en la raíz del proyecto, que no se versiona. Una variable de entorno definida MUST tener prioridad sobre el valor del archivo `.env`.

#### Scenario: Valores tomados del archivo .env
- **WHEN** el archivo `.env` define `POSTGRES_DB=taller` y no existe esa variable en el entorno
- **THEN** la aplicación usa `taller` como nombre de la base

#### Scenario: El entorno pisa al archivo .env
- **WHEN** el archivo `.env` define `SQL_ECHO=false` y el entorno define `SQL_ECHO=true`
- **THEN** la aplicación muestra las consultas SQL en la consola

### Requirement: Secretos obligatorios sin valor por defecto

`JWT_SECRET` y `POSTGRES_PASSWORD` MUST ser obligatorias y no tener valor por defecto en el código. Si falta alguna, la aplicación MUST NOT arrancar y MUST indicar en un mensaje claro qué variable falta, sin mostrar el valor de ningún secreto.

#### Scenario: Falta la clave de firma
- **WHEN** se inicia la aplicación sin `JWT_SECRET` en el entorno ni en `.env`
- **THEN** la aplicación no arranca y el error menciona que falta `JWT_SECRET`

#### Scenario: Falta la contraseña de la base
- **WHEN** se inicia la aplicación sin `POSTGRES_PASSWORD`
- **THEN** la aplicación no arranca y el error menciona que falta `POSTGRES_PASSWORD`

#### Scenario: Un secreto vacío cuenta como faltante
- **WHEN** `.env` se copió de `env.example` sin completar y trae `JWT_SECRET=` vacío
- **THEN** la aplicación no arranca y el error menciona que falta `JWT_SECRET`

#### Scenario: El error no expone secretos
- **WHEN** la aplicación no arranca porque falta `JWT_SECRET` pero `POSTGRES_PASSWORD` está definida
- **THEN** el mensaje de error no contiene el valor de `POSTGRES_PASSWORD`

### Requirement: Clave de firma fija entre reinicios

La clave de firma de los tokens MUST salir siempre de `JWT_SECRET` y MUST NOT generarse ni completarse con un valor aleatorio al arrancar, para que reiniciar el servidor no invalide las sesiones de los usuarios.

#### Scenario: La clave no cambia al reiniciar
- **WHEN** la aplicación se inicia dos veces con el mismo `JWT_SECRET`
- **THEN** la clave de firma configurada es idéntica en ambos arranques

### Requirement: Dirección de la base armada desde variables sueltas

La dirección de conexión a la base MUST armarse a partir de `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` y `POSTGRES_DB`, con un controlador asincrónico de PostgreSQL. MUST NOT existir una variable con la dirección completa.

#### Scenario: Dirección asincrónica
- **WHEN** las variables son `POSTGRES_USER=taller`, `POSTGRES_PASSWORD=x`, `POSTGRES_HOST=db`, `POSTGRES_PORT=5432`, `POSTGRES_DB=taller`
- **THEN** la dirección resultante usa el esquema `postgresql+asyncpg` y apunta a `db:5432/taller` con el usuario `taller`

### Requirement: Valores por defecto de las variables no sensibles

Las variables no sensibles MUST tener estos valores por defecto cuando no están definidas: `POSTGRES_USER=taller`, `POSTGRES_DB=taller`, `POSTGRES_HOST=localhost`, `POSTGRES_PORT=5432`, `JWT_ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_SECONDS=1800`, `COOKIE_SECURE=false`, `BCRYPT_ROUNDS=12`, `BCRYPT_MAX_CONCURRENCY=4`, `DB_POOL_SIZE=5`, `SQL_ECHO=false`. `POSTGRES_TEST_DB` MUST ser opcional para la aplicación y sólo la exigen los tests automáticos.

#### Scenario: Defaults aplicados
- **WHEN** sólo están definidas `JWT_SECRET` y `POSTGRES_PASSWORD`
- **THEN** la aplicación arranca con duración de token de 1800 segundos, costo de bcrypt 12, pool de 5 conexiones y sin eco de SQL

### Requirement: Valores de configuración inválidos

Un valor que no corresponde al tipo de la variable (por ejemplo, un texto donde se espera un número) MUST impedir el arranque con un mensaje que nombre la variable inválida.

#### Scenario: Puerto no numérico
- **WHEN** `POSTGRES_PORT=abc`
- **THEN** la aplicación no arranca y el error menciona `POSTGRES_PORT`

### Requirement: Plantilla de configuración sin secretos

El repositorio MUST incluir un `env.example` con todas las variables de configuración y ningún secreto real: `JWT_SECRET` y `POSTGRES_PASSWORD` MUST quedar vacías, con la indicación de cómo generar la clave de firma. El archivo `.env` MUST estar excluido del control de versiones.

#### Scenario: Plantilla completa y vacía de secretos
- **WHEN** se revisa `env.example`
- **THEN** contiene todas las variables de la configuración y `JWT_SECRET` y `POSTGRES_PASSWORD` no tienen valor

#### Scenario: .env no se versiona
- **WHEN** se crea un archivo `.env` en la raíz del proyecto
- **THEN** git lo ignora
