# Design

## Context

Correcciones de las 4 advertencias de la revisión del EJ-1 (ver `proposal.md`). El código afectado es el del EJ-1: `docker-compose.yml`, `main.py` (lifespan), `app/modules/health/router.py` y `test/pytest/conftest.py`.

## Goals / Non-Goals

**Goals:** cerrar las 4 advertencias sin cambiar la API ni la configuración.

**Non-Goals:** las 4 sugerencias de la revisión (`url_base_datos` en `model_dump`, `pg_isready -h`, pool compartido de la sonda, cierre del cliente en `ProxyTCP`).

## Decisions

### F1 — Puerto de la base sólo en loopback
`ports: "127.0.0.1:${POSTGRES_PORT:-5432}:5432"`. El venv y pytest siguen llegando por `localhost`; la api llega por la red interna del compose (`db:5432`), que no depende del puerto publicado. *Alternativa*: no publicar el puerto (rompe el camino venv y los tests desde el host).

### F2 — Log de la causa del 503
Logger `app.salud` y `logger.warning("La sonda de preparación respondió 503: %s", type(error).__name__)`. Se registra **sólo el nombre de la excepción**, no su mensaje ni la traza: el mensaje de asyncpg/SQLAlchemy puede incluir host, puerto, usuario o la sentencia, y no se gana nada que el tipo no diga (`ConnectionRefusedError`, `InvalidPasswordError`, `TimeoutError`). *Alternativa*: `exc_info=True` (más ruido y riesgo de exponer datos de conexión en el log).

### F3 — Liberar el motor si el arranque falla
En el `lifespan`, el `try/finally` pasa a envolver todo lo que viene después de `crear_motor` (semáforo, hash ficticio y `yield`), así `motor.dispose()` corre también si el arranque falla o se cancela.

### F4 — Saltear cuando la base no responde
`requiere_base_de_test()` además intenta una conexión TCP a `POSTGRES_HOST:POSTGRES_PORT` con 1 s de límite; si falla, saltea con el motivo. Es una comprobación barata y suficiente para distinguir "no hay base" de un fallo real del test. La verificación de cierre sigue exigiendo 0 skipped con la base levantada.

## Risks / Trade-offs

- [Un compañero accedía a la base de Docker desde otra máquina de la red] → ya no puede; es el objetivo de R1-001. Si lo necesita, cambia el bind en su copia local.
- [Un test con base que falla por un motivo distinto a la conectividad podría saltearse] → sólo se saltea si la conexión TCP falla; cualquier otro error sigue fallando.
