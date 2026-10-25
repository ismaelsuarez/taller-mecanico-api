# Tasks

> TDD: RED antes de cada corrección con comportamiento (F2, F3, F4). Cierre con `pytest -rs`, `db` levantada y 0 skipped.

## 1. Log de la causa del 503 (F2, spec `salud-servicio`)

- [x] 1.1 RED: test que, con la base inalcanzable, verifica que `GET /health/ready` deja un aviso en el logger `app.salud` con el tipo de falla y sin `POSTGRES_PASSWORD` ni `JWT_SECRET`. Verificación: el test falla.
- [x] 1.2 GREEN: registrar `type(error).__name__` en `app/modules/health/router.py`. Verificación: el test pasa y `test_salud.py` sigue en verde.

## 2. Motor liberado si el arranque falla (F3)

- [x] 2.1 RED: test que hace fallar el cálculo del hash ficticio y verifica que el motor creado se liberó (su pool fue reemplazado). Verificación: el test falla.
- [x] 2.2 GREEN: ampliar el `try/finally` del `lifespan` en `main.py`. Verificación: el test pasa y `test_ciclo_de_vida.py` sigue en verde.

## 3. Saltear cuando la base no responde (F4)

- [x] 3.1 RED: test que, con `POSTGRES_TEST_DB` definida y un puerto sin servicio, espera que `requiere_base_de_test()` saltee con un motivo que mencione que la base no responde. Verificación: el test falla.
- [x] 3.2 GREEN: comprobación TCP en `requiere_base_de_test()`. Verificación: el test pasa.

## 4. Base sólo en loopback (F1) y cierre

- [x] 4.1 Publicar el puerto de `db` en `127.0.0.1` en `docker-compose.yml` y mencionarlo en el README. Verificación: tras `docker compose up -d db`, `ss -ltn` muestra `127.0.0.1:5432` y no `0.0.0.0:5432`; `pytest -rs` desde el host sigue conectando.
- [x] 4.2 Suite completa. Verificación: con `db` levantada, `pytest -rs` en verde con 0 skipped.

## Workflow follow-up

- `/opsx:archive fix-advertencias-revision-ej1` → commit → `bash scripts/sync-memoria.sh` → `git push`.
