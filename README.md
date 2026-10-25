# Taller Mecánico API

API REST asincrónica para un taller mecánico: clientes y vehículos, órdenes de trabajo, stock de repuestos y control de acceso por roles. Trabajo práctico integrador de **Programación III (UTN)**, capítulos 1 a 6, con FastAPI, SQLModel, SQLAlchemy 2.0 async, PostgreSQL 16 y Alembic.

## Puesta en marcha

### 1. Configuración (`.env`)

```bash
cp env.example .env
chmod 600 .env
```

Completá en `.env` los dos valores obligatorios (sin ellos la aplicación **no arranca**):

- `POSTGRES_PASSWORD`: la contraseña de tu base local.
- `JWT_SECRET`: la clave de firma de los tokens. Generala **una sola vez** y no la cambies (si cambia, todas las sesiones dejan de valer):

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(64))"
  ```

> `.env` nunca se sube al repositorio. `env.example` es sólo la plantilla y no lleva secretos.

### 2a. Con Docker (recomendado para el equipo)

```bash
docker compose up -d --build       # api (puerto 8000) + db (postgres:16, puerto 5432)
curl localhost:8000/health/ready   # {"estado":"listo"}
```

La primera vez que se crea el volumen de la base se crea también la base de test (`POSTGRES_TEST_DB`). Ese script **sólo corre con el volumen vacío**: si levantaste `db` antes de tener `POSTGRES_TEST_DB` en el `.env`, recrealo con `docker compose down -v && docker compose up -d` (borra los datos locales de desarrollo).

### 2b. Sin Docker (entorno virtual)

Usá **Python 3.12** (la misma versión que la imagen Docker; con 3.13 o 3.14 algunas dependencias pueden no tener paquetes listos).

```bash
python3.12 -m venv .venv            # o: uv venv --python 3.12
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt     # o: uv pip install -r requirements.txt
uvicorn main:app --reload           # o: fastapi dev main.py
```

Necesitás una PostgreSQL 16 accesible con los datos del `.env` (`POSTGRES_HOST=localhost`). La forma más simple es levantar sólo la base de Docker: `docker compose up -d db`.

### 3. Esquema y datos iniciales

`alembic upgrade head` y `python seed.py` llegan en **EJ-2** (`02-modelos-migraciones-seed`). Con Docker se corren dentro del contenedor: `docker compose exec api alembic upgrade head` y `docker compose exec api python seed.py`.

### 4. Tests

```bash
docker compose up -d db             # los tests usan una PostgreSQL real (base POSTGRES_TEST_DB)
pytest -rs                          # con el venv activo
```

Si la base de test no está disponible, los tests que la necesitan se **saltean** con el motivo; antes de cerrar un change tienen que correr con **0 skipped**. Los casos manuales están en `test/*.http` (extensión REST Client de VS Code), con la respuesta esperada en comentarios.

### Salud del servicio

| Ruta | Responde |
|---|---|
| `GET /health/live` | 200 mientras el proceso esté vivo (no consulta la base) |
| `GET /health/ready` | 200 si la base contesta, 503 si no |

## Primer uso después de clonar (una sola vez)

```bash
git clone https://github.com/ismaelsuarez/taller-mecanico-api.git
cd taller-mecanico-api
bash scripts/setup.sh
```

`scripts/setup.sh`:

1. Activa los hooks versionados (`git config core.hooksPath .githooks`). Desde ahí, **cada `git pull` importa automáticamente la memoria de engram** del equipo (`engram sync --import`).
2. Restaura las skills del proyecto desde `skills-lock.json` en `.agents/skills/` (con enlaces relativos en `.claude/skills/`). No dependen de rutas de ninguna máquina.
3. Importa la memoria de engram que está en `.engram/`.

Requisitos: Git, Node.js (para `npx`) y [engram](https://github.com/Gentleman-Programming/engram). Si falta alguno, el script avisa y sigue.

**Windows**: corré `bash scripts/setup.sh` desde **Git Bash** (viene con Git for Windows); los hooks de git también corren con ese bash. Para exportar la memoria antes de un push podés usar `scripts\sync-memoria.bat` desde `cmd` o PowerShell. El `.gitattributes` del repo mantiene los `.sh` con fin de línea LF y los `.bat` con CRLF.

> Git no activa hooks al clonar (es una protección de seguridad); por eso este paso es manual y se hace una sola vez.

## Flujo de trabajo del equipo (relevos)

Los 8 ejercicios de la consigna son 8 changes **estrictamente secuenciales** (`EJ-1` → `EJ-8`). Uno trabaja a la vez:

```
git pull                                   # trae el código y, por el hook, la memoria de engram
/opsx:propose 0N-nombre-del-change         # ver CHANGES.md
/opsx:apply
# Definition of Done del change (ver CHANGES.md)
/opsx:archive 0N-nombre-del-change
git commit ...                             # incluye el checkbox [x] en CHANGES.md
bash scripts/sync-memoria.sh               # exporta y commitea tu memoria (Windows: scripts\sync-memoria.bat)
git push                                   # relevo al siguiente compañero
```

## Dónde está cada cosa

| Ruta | Contenido |
|---|---|
| [docs/](docs/) | Consigna original del trabajo práctico (fuente de verdad) |
| [knowledge-base/](knowledge-base/README.md) | Base de conocimiento: dominio, modelo de datos, reglas, decisiones del equipo |
| [CHANGES.md](CHANGES.md) | Roadmap de los 8 changes y regla de relevo |
| [AGENTS.md](AGENTS.md) / [CLAUDE.md](CLAUDE.md) | Instrucciones y reglas duras para agentes de IA |
| `openspec/` | Specs y changes de OpenSpec |
| `.agents/skills/`, `skills-lock.json` | Skills del proyecto |
| `.engram/` | Memoria del proyecto (engram), compartida por el equipo |
| `.githooks/`, `scripts/` | Hooks de git y scripts de setup y sincronización de memoria |
