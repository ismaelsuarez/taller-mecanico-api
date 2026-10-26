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
docker compose up -d --build       # api (puerto 8000) + db (postgres:16, puerto 5432 sólo en 127.0.0.1)
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

El esquema se crea **sólo con Alembic** (nunca `create_all`); el catálogo de estados y los datos iniciales los carga `seed.py`.

```bash
# Con Docker (recomendado):
docker compose exec api alembic upgrade head
docker compose exec api python seed.py

# Sin Docker (venv activo):
alembic upgrade head
python seed.py
```

Para verificar el ciclo completo de migraciones (sube, baja y vuelve a subir):

```bash
alembic upgrade head
alembic downgrade base
alembic upgrade head
python seed.py          # el seed siempre se corre después de migrar
```

Para recrear la base de test (borra los datos locales de desarrollo):

```bash
docker compose down -v && docker compose up -d
```

`seed.py` es **idempotente**: correrlo dos veces deja el mismo estado. Vacía las tablas con `TRUNCATE` y recarga: catálogo de estados (PENDIENTE, EN_REPARACION, TERMINADA, CANCELADA), 7 usuarios con sus roles, Laura y Jorge con sus vehículos, 4 repuestos con su movimiento «Stock inicial», 2 órdenes de trabajo con sus historiales, el historial de precios del filtro y un evento de seguridad con actor `SISTEMA`. Al final **sincroniza las secuencias de id** con los ids que sembró (DD-38): sin ese paso, el primer alta de la API chocaría con un id ya ocupado. Las contraseñas de prueba viven **sólo** en `seed.py` (no son credenciales reales).

### 4. Tests

```bash
docker compose up -d db             # los tests usan una PostgreSQL real (base POSTGRES_TEST_DB)
pytest -rs                          # con el venv activo
```

Si la base de test no está disponible, los tests que la necesitan se **saltean** con el motivo; antes de cerrar un change tienen que correr con **0 skipped**. Los casos manuales están en `test/*.http` (extensión REST Client de VS Code), con la respuesta esperada en comentarios; **antes de correr cada archivo corré `python seed.py`** (D-3), porque los ids esperados salen del seed.

## Endpoints

> **Rutas abiertas hasta EJ-5 (T-11):** todavía no hay login; desde EJ-4 se suma `/auth` y desde EJ-5 estos grupos quedan protegidos por roles.

### Salud (públicas siempre)

| Método | Ruta | Qué responde |
|---|---|---|
| GET | `/health/live` | 200 mientras el proceso esté vivo (no consulta la base) |
| GET | `/health/ready` | 200 si la base contesta, 503 si no |

### Clientes y vehículos

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/clientes` | Alta: 201; documento repetido 409; cuerpo inválido 422 |
| GET | `/clientes/{id}` | Detalle con los vehículos vigentes: 200 / 404 |
| POST | `/clientes/{id}/vehiculos` | Alta: 201; cliente inexistente 404; patente vigente repetida 409; 422 |
| DELETE | `/vehiculos/{id}` | Baja lógica: 204; con órdenes abiertas 409; ya baja o inexistente 404 |

### Repuestos

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/repuestos` | Listado paginado de vigentes con `?page`, `?size` y `?q` (busca «contiene» en la descripción) |
| POST | `/repuestos` | Alta con `stock_inicial`: 201; código vigente repetido 409; 422 |
| GET | `/repuestos/{id}` | Detalle: 200 / 404 |
| PATCH | `/repuestos/{id}` | Parcial de `descripcion` y/o `precio` con línea de historial: 200 / 404 / 422 |
| DELETE | `/repuestos/{id}` | Baja lógica: 204 siempre que esté vigente; 404 si ya baja o no existe |
| POST | `/repuestos/{id}/reponer` | Reposición de stock: 200 / 404 / 422 |
| GET | `/repuestos/{id}/movimientos` | Movimientos de stock en orden cronológico: 200 / 404 |
| GET | `/repuestos/{id}/precios` | Historial de precios en orden cronológico: 200 / 404 |

Todos los listados devuelven el envoltorio `{items, total, page, size, pages}`; `size` va de 1 a 100 (20 por defecto) y una página fuera de rango responde 422 con el mensaje «La página N no existe: hay M».

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
