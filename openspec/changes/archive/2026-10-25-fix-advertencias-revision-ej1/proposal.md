# Proposal

## Why

La revisión nativa del EJ-1 (`review-cf431af11a3fca38`) se aprobó con 4 advertencias no bloqueantes que conviene resolver antes del relevo al EJ-2: una expone la base de datos a la red, otra deja sin diagnóstico las caídas de la base, otra puede dejar el motor sin liberar si el arranque falla, y la última hace que los tests fallen en lugar de saltearse cuando la base no responde (contradice el diseño D7 del EJ-1).

## What Changes

- **R1-001** — `docker-compose.yml` publica PostgreSQL sólo en `127.0.0.1` (antes, en todas las interfaces de red).
- **R4-ready-sin-log** — `GET /health/ready` registra en el log del servidor la causa de cada 503, sin incluirla en la respuesta ni registrar secretos.
- **R3-lifespan-dispose-unguarded** — si el arranque falla después de crear el motor, el motor se libera igual.
- **R3-skip-not-reachability** — los tests que necesitan base se saltean con un motivo claro cuando la base no responde, no sólo cuando falta `POSTGRES_TEST_DB`.

Fuera de alcance: las 4 sugerencias (💡) de la misma revisión.

## Capabilities

### New Capabilities

<!-- Ninguna. -->

### Modified Capabilities

- `salud-servicio`: se agrega el requisito de registrar la causa de un 503 de la sonda de preparación.

## Impact

- `docker-compose.yml`, `app/modules/health/router.py`, `main.py`, `test/pytest/conftest.py`, tests en `test/pytest/`.
- `README.md` (la base de Docker queda accesible sólo desde la propia máquina).
- Sin cambios de API ni de configuración.
