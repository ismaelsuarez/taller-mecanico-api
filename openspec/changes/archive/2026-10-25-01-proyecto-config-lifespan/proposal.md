# Proposal

## Why

Es el primer relevo del equipo ([EJ-1] en `CHANGES.md`, Ejercicio 1 de la consigna, 8 pts). Hoy el repositorio sólo tiene la fundación (KB, roadmap, reglas): no existe una aplicación que levante, ni configuración, ni base de datos. Todo el resto de los ejercicios necesita un proyecto con la estructura obligatoria, configuración leída del entorno sin secretos en el código, recursos de base creados en el ciclo de vida correcto y sondas de salud. Además, la consigna marca como bloqueante de la corrección un proyecto que no levanta o que tiene credenciales en el repositorio.

## What Changes

- Esqueleto completo de la estructura obligatoria (`main.py`, `seed.py`, `app/core/*`, `app/modules/{health,usuarios,clientes,repuestos,ordenes}/`, `migrations/`, `test/`), con módulos todavía vacíos documentados.
- Configuración con `Settings` (pydantic-settings) desde variables de entorno o `.env` no versionado: URL asincrónica de la base armada a partir de `POSTGRES_*`; `JWT_SECRET` y `POSTGRES_PASSWORD` sin valor por defecto (si faltan, la aplicación no arranca); resto de variables de DD-30 con sus defaults. La clave de firma es fija: nunca se genera al arrancar.
- Ciclo de vida: el motor asincrónico (con pool configurable) y la fábrica de sesiones se crean en el `lifespan` y se guardan en el estado de la app; una sesión por petición (`expire_on_commit=False`) que se cierra al terminar; hash ficticio del login calculado una sola vez al arrancar; `dispose()` del motor al apagar.
- Endpoints de salud: `GET /health/live` (no toca la base) y `GET /health/ready` (`SELECT 1`; 503 si la base no responde).
- Entorno del equipo con Docker (DD-32): `Dockerfile` multi-stage, `.dockerignore` y `docker-compose.yml` con `api` + `db` (`postgres:16`) y base de test; credenciales sólo desde `.env`.
- `env.example` sin secretos, `requirements.txt` con el stack y `README.md` con las dos formas de levantar el proyecto (Docker y venv), incluido cómo generar la clave de firma.
- Runner de tests: pytest + httpx contra una PostgreSQL real de test (`test/pytest/`), y `test/health.http` con las respuestas esperadas.

## Capabilities

### New Capabilities

- `configuracion-aplicacion`: cómo la aplicación obtiene su configuración del entorno, qué variables son obligatorias, cuáles tienen valor por defecto y qué pasa cuando falta un secreto.
- `salud-servicio`: sondas de vida y de preparación que distinguen un proceso vivo de uno listo para atender (base de datos disponible).

### Modified Capabilities

<!-- Ninguna: es el primer change y no hay specs previas en openspec/specs/. -->

## Impact

- **Código nuevo**: `main.py`, `seed.py` (vacío por ahora), `app/core/{config,database,security,dependencies,repository,paginacion,unit_of_work}.py`, `app/modules/health/router.py` y los paquetes vacíos de los demás módulos.
- **Infraestructura**: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, script de inicialización de la base de test.
- **Dependencias**: FastAPI (`fastapi[standard]`), SQLModel, SQLAlchemy 2.0 async, asyncpg, Alembic, pydantic-settings, bcrypt, PyJWT; para tests, pytest, pytest-asyncio y httpx.
- **Documentación**: `README.md` (puesta en marcha), `env.example`.
- **Tests**: `test/pytest/` (configuración y salud) y `test/health.http`.
- **Sin migraciones ni modelos**: el esquema llega en EJ-2.
