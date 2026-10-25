# Design

## Context

Proyecto vacío salvo la fundación (ver `proposal.md` → Why). Restricciones que dan forma al enfoque:

- Estructura de directorios **obligatoria** de la consigna (`knowledge-base/08_arquitectura_propuesta.md`); manda sobre cualquier plantilla (regla A-2).
- Stack mínimo fijado por la consigna: Python 3.12, FastAPI 0.111, SQLModel 0.0.24, SQLAlchemy 2.0 async, asyncpg 0.30, PostgreSQL 16, Alembic 1.13, pydantic-settings 2.0, bcrypt 4.0, PyJWT 2.8.
- Reglas duras aplicables: B-5 (todo `async def`, bcrypt fuera del bucle), B-6 (recursos en el lifespan), S-6 y S-7 (secretos sin default, clave fija), S-9 (mensajes en español claro), E-1 (identificadores en español), E-2 (pytest contra PostgreSQL real).
- Decisiones del equipo: DD-13 (tests), DD-20 (clave fija), DD-30 (variables), DD-32 (Docker app + base).
- Máquina de desarrollo actual: Python del sistema 3.14, `uv`, Docker y Docker Compose disponibles; no hay `psql` local.

## Goals / Non-Goals

**Goals:**
- Un proyecto que levanta con Docker (`docker compose up`) y con venv, con la misma configuración.
- Recursos de base creados sólo cuando ya existe el bucle de eventos, y liberados al apagar.
- Base de tests automática (pytest) que los siguientes relevos reutilizan sin reconfigurar nada.

**Non-Goals:**
- Modelos, migraciones o contenido de `seed.py` (EJ-2). En este change Alembic no se inicializa: la carpeta `migrations/` queda vacía con un `README` que apunta a EJ-2.
- Autenticación, emisión o verificación de tokens (EJ-4). `security.py` sólo trae lo que necesita el hash ficticio.
- Grupos de rutas abierta/protegida con su control (EJ-5); acá sólo se prepara el lugar donde se montan.

## Decisions

### D1 — `Settings` único con secretos como `SecretStr` obligatorios
`app/core/config.py` define `Settings(BaseSettings)` con `env_file=".env"`, y `JWT_SECRET` y `POSTGRES_PASSWORD` como `SecretStr` **sin default** (campo requerido). pydantic-settings ya da la prioridad entorno > `.env` y valida tipos (puerto no numérico → error que nombra la variable).
- La URL (`url_base_datos`) es un `@computed_field` que arma `postgresql+asyncpg://...` con `URL.create` de SQLAlchemy, para escapar caracteres especiales de la contraseña.
- `SecretStr` evita que el valor aparezca en `repr`, logs o mensajes de validación.
- Se obtiene con una función `obtener_settings()` cacheada (`lru_cache`) que se llama **desde el lifespan**, no al importar; así los tests pueden cambiar el entorno y limpiar la caché.
- *Alternativas*: `os.environ` manual (pierde validación de tipos); `DATABASE_URL` completa (la consigna exige variables sueltas).

### D2 — Fallo de arranque legible
Si `Settings` no valida, el lifespan deja que el error se propague: uvicorn no termina de arrancar. El `ValidationError` de pydantic se envuelve en un `RuntimeError` con un mensaje en español que lista sólo los **nombres** de las variables faltantes o inválidas (nunca valores).
- *Alternativa*: validar al importar `main.py` (contradice B-6 y rompe los tests que importan la app sin entorno).

### D3 — Motor y fábrica de sesiones en el lifespan
`app/core/database.py` expone `crear_motor(settings)` y `crear_fabrica_sesiones(motor)`; **no** crea nada a nivel de módulo. El `lifespan` de `main.py`:
1. obtiene `Settings`;
2. crea el motor con `pool_size=DB_POOL_SIZE`, `echo=SQL_ECHO` y `pool_pre_ping=True`;
3. crea `async_sessionmaker(motor, expire_on_commit=False)`;
4. calcula una vez el hash ficticio (D5);
5. guarda todo en `app.state` (`settings`, `motor`, `fabrica_sesiones`, `hash_ficticio`);
6. al salir, `await motor.dispose()`.

`get_session(request)` es una dependencia `async` con `async with request.app.state.fabrica_sesiones() as sesion: yield sesion`. El gestor de contexto cierra la sesión aunque el handler falle, lo que cumple el requisito de "una sesión por petición".
- `pool_pre_ping` evita que una conexión muerta tras una caída de la base deje `/health/ready` en 503 cuando la base ya volvió.

### D4 — Sondas de salud sin tocar la sesión en `live`
`app/modules/health/router.py`:
- `GET /health/live` → `{"estado": "vivo"}`, sin dependencias de base.
- `GET /health/ready` → usa `get_session`, ejecuta `SELECT 1` con `asyncio.wait_for` (timeout de 2 s) y devuelve `{"estado": "listo"}`; ante `SQLAlchemyError`, `OSError` o `TimeoutError` responde 503 con `{"estado": "no listo", "detalle": "La base de datos no está disponible en este momento."}`. Nunca se devuelve el texto de la excepción.
- El timeout evita que un host inalcanzable deje la sonda colgada.
- En `main.py` el router de salud se incluye en un `APIRouter` llamado `rutas_abiertas`, así EJ-5 sólo agrega el grupo protegido (T-11).

### D5 — Hash ficticio calculado en el lifespan
`app/core/security.py` trae en este change sólo lo mínimo:
- `configurar_semaforo_bcrypt(max_concurrencia: int)`: crea el `asyncio.Semaphore` y lo guarda en una variable del módulo (inicialmente `None`). La llama **el lifespan** con `BCRYPT_MAX_CONCURRENCY`; nada se crea al importar.
- `async def hashear_password(texto: str, rondas: int) -> str`: corre `bcrypt.hashpw` con `asyncio.to_thread` dentro del semáforo del módulo. Si el semáforo no fue configurado, lanza `RuntimeError` con un mensaje claro (no crea uno por su cuenta, para no ocultar un lifespan mal armado).
- Así, en EJ-4 `verificar_password` y los servicios reutilizan el mismo semáforo **sin depender de `request.app.state`** ni recibirlo como argumento. Los tests llaman a `configurar_semaforo_bcrypt` en su fixture.

El lifespan llama a `configurar_semaforo_bcrypt(...)` y luego calcula `hash_ficticio = await hashear_password(<texto aleatorio>, BCRYPT_ROUNDS)`. El texto aleatorio **no** es un secreto: sólo sirve para que el login de un correo inexistente tarde lo mismo (RN-09, EJ-4).
- *Alternativas*: leer el semáforo de `app.state` (acopla servicios a la request); recibirlo como parámetro en cada llamada (ensucia todas las firmas de EJ-4).

### D6 — Docker: imagen multi-stage y compose con base de test
- `Dockerfile`: etapa `builder` (`python:3.12-slim`) que instala `requirements.txt` en un venv; etapa final `python:3.12-slim` que copia el venv y el código, crea un usuario sin privilegios y corre `uvicorn main:app --host 0.0.0.0 --port 8000`.
- `docker-compose.yml`: servicio `db` (`postgres:16`, `env_file: .env`, volumen `datos_pg`, healthcheck `pg_isready`, `docker/postgres/init/` montado en `/docker-entrypoint-initdb.d/`) y servicio `api` (`env_file: .env`, `POSTGRES_HOST=db` sobrescrito, `depends_on: db: condition: service_healthy`, puerto 8000).
- `db` usa `env_file: .env`: las variables del proyecto (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) tienen los mismos nombres que espera la imagen oficial, y así el script de init recibe también `POSTGRES_TEST_DB`.
- `docker/postgres/init/01-crear-base-test.sh` crea `POSTGRES_TEST_DB` (si está definida) con el mismo dueño. **La imagen sólo ejecuta estos scripts cuando el volumen de datos está vacío**: si `db` ya se había levantado antes, la base de test no se crea; el README indica `docker compose down -v` para recrear el volumen (borra los datos locales de desarrollo, que `seed.py` vuelve a cargar).
- El compose no contiene ningún secreto escrito: todo sale del `.env`.
- *Alternativa*: sólo la base en Docker (descartada por DD-32).

### D7 — Tests con pytest contra PostgreSQL real
- `test/pytest/conftest.py` arma el entorno de test: toma `.env`, reemplaza `POSTGRES_DB` por `POSTGRES_TEST_DB` y fuerza un `JWT_SECRET` de prueba. Si `POSTGRES_TEST_DB` no está definida o la base no responde, los tests que necesitan base se **saltean con un motivo claro** (no fallan en silencio ni tocan la base de desarrollo).
- El skip es una comodidad para correr tests aislados, **no** una forma de dar por cumplido el change: la verificación de cierre exige correr `pytest -rs` con `db` levantada y **0 skipped**, para que los escenarios de `/health/ready` contra PostgreSQL real se ejecuten de verdad.
- Cliente: `httpx.AsyncClient` con `ASGITransport`, más un gestor que ejecuta el lifespan (`app.router.lifespan_context`), porque `ASGITransport` no dispara el lifespan solo.
- La base caída se simula con un `POSTGRES_PORT` donde no escucha nadie (no hace falta detener Docker).
- `pytest.ini` (o la sección en `pyproject.toml`) con `asyncio_mode = auto` y `testpaths = test/pytest`.
- `test/health.http` documenta las mismas sondas para REST Client, con la respuesta esperada en comentarios.

### D8 — Versión de Python para el venv
Python 3.14 del sistema puede no tener ruedas para algunas dependencias del stack (por ejemplo asyncpg 0.30). El README recomienda crear el venv con **Python 3.12**, igual que la imagen Docker (`uv venv --python 3.12` o `python3.12 -m venv`). `requirements.txt` fija mínimos compatibles (`>=`) con el stack de la consigna.

## Risks / Trade-offs

- [Un compañero sin Docker y sin PostgreSQL local no puede correr los tests de base] → se saltean con un motivo claro; el resto de los tests (configuración, `live`) corre igual.
- [El hash ficticio suma ~300 ms al arranque] → es una sola vez y lo exige la consigna.
- [`pool_pre_ping` agrega un ida y vuelta por checkout] → costo despreciable frente a no recuperarse de una caída.
- [Python 3.14 local sin ruedas de asyncpg] → el README documenta Python 3.12; Docker lo resuelve igual.
- [Dos caminos de arranque (Docker y venv) pueden desincronizarse] → ambos leen el mismo `.env` y el mismo `requirements.txt`; el README los documenta lado a lado.

## Migration Plan

No aplica: es el primer código del proyecto. Rollback = revertir el commit del change.
