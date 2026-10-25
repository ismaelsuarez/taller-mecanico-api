# Tasks

> Ciclo TDD (regla E-2, Strict TDD): en cada grupo con comportamiento, primero el test en rojo, después el código mínimo, después refactor con los tests en verde. Comando de tests: `pytest` (desde la raíz, con el venv activo o `docker compose exec api pytest`).

## 1. Esqueleto y dependencias

- [x] 1.1 Crear la estructura obligatoria completa (T-1): `main.py`, `seed.py` (docstring "se completa en EJ-2"), `app/__init__.py`, `app/core/{__init__,config,database,security,dependencies,repository,paginacion,unit_of_work}.py` (los sin contenido, con docstring que indique el EJ que los completa), `app/modules/__init__.py`, `app/modules/health/{__init__,router}.py`, y en los 4 módulos de dominio (`usuarios`, `clientes`, `repuestos`, `ordenes`) `__init__.py` más los 6 archivos de capa (`models`, `schemas`, `repository`, `unit_of_work`, `service`, `router`) con docstring que indique qué entidades viven ahí y qué EJ los completa; `migrations/README.md` (apunta a EJ-2) y `test/`. Verificación: `find app -name '*.py' | sort` lista los 40 archivos esperados y `python -c "import app.modules.usuarios.service"` no falla.
- [x] 1.2 Crear `requirements.txt` con el stack de la consigna (mínimos `>=`: fastapi[standard], sqlmodel, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, bcrypt, pyjwt) y dependencias de test (pytest, pytest-asyncio, httpx). Verificación: `uv venv --python 3.12 && uv pip install -r requirements.txt` termina sin errores.
- [x] 1.3 Configurar pytest (`pytest.ini`: `testpaths = test/pytest`, `asyncio_mode = auto`) y un test de humo que importe la app. Verificación: `pytest` corre y el test de humo pasa.

## 2. Configuración (spec `configuracion-aplicacion`)

- [x] 2.1 RED: tests en `test/pytest/test_configuracion.py` para: lectura de `.env`, prioridad del entorno sobre `.env`, falta de `JWT_SECRET` (error nombra la variable), falta de `POSTGRES_PASSWORD`, el error no contiene el valor de la otra contraseña, clave idéntica en dos cargas, URL `postgresql+asyncpg` con host/puerto/base/usuario, defaults de DD-30 y `POSTGRES_PORT=abc` rechazado. Verificación: `pytest test/pytest/test_configuracion.py` falla por falta de implementación.
- [x] 2.2 GREEN: implementar `Settings` y `obtener_settings()` en `app/core/config.py` (D1, D2), con secretos `SecretStr` sin default y `@computed_field` de la URL. Verificación: `pytest test/pytest/test_configuracion.py` pasa completo.
- [x] 2.3 Crear `env.example` con todas las variables de DD-30, `JWT_SECRET` y `POSTGRES_PASSWORD` vacías y el comando para generar la clave. Verificación: test que compara los campos de `Settings` con las claves de `env.example` y comprueba que los secretos están vacíos; `git check-ignore .env` responde `.env`.

## 3. Ciclo de vida y base de datos

- [x] 3.1 RED: tests del lifespan: al entrar al contexto existen en `app.state` `settings`, `motor`, `fabrica_sesiones` y `hash_ficticio` (un hash bcrypt válido); importar `main` sin variables de entorno no falla (nada se crea al importar); al salir el motor queda liberado. Verificación: los tests fallan.
- [x] 3.2 GREEN: implementar `crear_motor`, `crear_fabrica_sesiones` y `get_session` en `app/core/database.py` (D3), `configurar_semaforo_bcrypt` y `hashear_password` con `to_thread` + semáforo del módulo en `app/core/security.py` (D5) y el `lifespan` en `main.py` (que llama a `configurar_semaforo_bcrypt` antes de calcular el hash ficticio) con el `APIRouter` `rutas_abiertas` (D4). Verificación: los tests de 3.1 pasan, más un test de que `hashear_password` sin semáforo configurado lanza `RuntimeError` con mensaje claro.

## 4. Salud (spec `salud-servicio`)

- [x] 4.1 RED: tests en `test/pytest/test_salud.py`: `live` 200 con base disponible y con base inalcanzable; `ready` 200 con base disponible y 503 con base inalcanzable (puerto sin servicio); el cuerpo del 503 no contiene texto de la base, la dirección de conexión ni la contraseña; `ready` llamado más veces que `DB_POOL_SIZE` responde siempre 200; tras varios 503 la base vuelve y responde 200. Verificación: los tests fallan.
- [x] 4.2 GREEN: implementar `app/modules/health/router.py` (D4) e incluirlo en `rutas_abiertas`. Verificación: con `db` levantada, `pytest -rs test/pytest/test_salud.py` pasa con **0 skipped**.
- [x] 4.3 Crear `test/health.http` con `live` y `ready`, cada uno con la respuesta esperada en un comentario (incluido el 503 con la base detenida). Verificación: ejecutado en REST Client contra la app levantada, las respuestas coinciden con los comentarios.

## 5. Docker y entorno del equipo

- [x] 5.1 Crear `Dockerfile` multi-stage (`python:3.12-slim`, usuario no-root) y `.dockerignore` (excluye `.env`, `.venv`, `.git`, `.engram`, `.agents`, caches). Verificación: `docker build -t taller-api .` termina y `docker run --rm taller-api id -u` no devuelve 0.
- [x] 5.2 Crear `docker-compose.yml` (`db` postgres:16 con `env_file: .env`, volumen, healthcheck y `docker/postgres/init/01-crear-base-test.sh` montado en `/docker-entrypoint-initdb.d/`, que crea `POSTGRES_TEST_DB`; `api` con `env_file: .env`, `POSTGRES_HOST=db`, `depends_on` con `service_healthy`, puerto 8000) sin ningún secreto escrito. Verificación: con un `.env` completo y el volumen vacío (`docker compose down -v`), `docker compose up -d --build`, `curl -s localhost:8000/health/ready` → 200, y `docker compose exec db psql -U "$POSTGRES_USER" -lqt` lista la base de test; `grep -iE 'password:|secret' docker-compose.yml` no muestra valores.
- [x] 5.3 Verificar el arranque fallido: con `JWT_SECRET` vacío, `docker compose up api` (o `uvicorn main:app`) no arranca y el log nombra la variable faltante sin mostrar secretos.

## 6. Documentación y cierre del relevo

- [x] 6.1 Completar `README.md` con la puesta en marcha (Docker y venv con Python 3.12), cómo generar la clave de firma, cómo correr `pytest` y `test/health.http`, la nota de que la base de test sólo se crea con el volumen vacío (`docker compose down -v` para recrearlo) y que Alembic y `seed.py` llegan en EJ-2. Verificación: seguir los pasos del README desde un clon limpio levanta la app y `GET /health/ready` responde 200.
- [x] 6.2 Correr la suite completa y la revisión de secretos. Verificación: con `db` levantada, `pytest -rs` en verde con **0 skipped**; `git grep -nE 'JWT_SECRET *= *["\x27][^"\x27]+|POSTGRES_PASSWORD *= *["\x27][^"\x27]+'` sin resultados en código ni en `alembic.ini`/compose.
- [x] 6.3 Marcar `[EJ-1]` como `[x]` en `CHANGES.md` y anotar en `knowledge-base/09_decisiones_y_supuestos.md` cualquier decisión nueva tomada durante la implementación (regla D-4). Verificación: el checkbox y las notas están en el diff del commit.

## Workflow follow-up

- `/opsx:archive 01-proyecto-config-lifespan`
- Commit (Conventional Commits) → `bash scripts/sync-memoria.sh` → `git push` (relevo al compañero del EJ-2).
