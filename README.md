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

`seed.py` es **idempotente**: correrlo dos veces deja el mismo estado. El vaciado y la recarga se confirman en un único **Unit of Work**; si falla la carga o el commit, se revierte toda la operación. El seed crea y cierra la sesión, y calcula los hashes antes de abrir la transacción. Vacía las tablas con `TRUNCATE` y recarga: catálogo de estados (PENDIENTE, EN_REPARACION, TERMINADA, CANCELADA), 7 usuarios con sus roles, Laura y Jorge con sus vehículos, 4 repuestos con su movimiento «Stock inicial», 2 órdenes de trabajo con sus historiales, el historial de precios del filtro y un evento de seguridad con actor `SISTEMA`. Al final **sincroniza las secuencias de id** con los ids que sembró (DD-38): sin ese paso, el primer alta de la API chocaría con un id ya ocupado. Las contraseñas de prueba viven **sólo** en `seed.py` (no son credenciales reales).

### 4. Tests

```bash
docker compose up -d db             # los tests usan una PostgreSQL real (base POSTGRES_TEST_DB)
pytest -rs                          # con el venv activo
```

Las fixtures de integración aplican **Alembic hasta `head`**, incluidos los tres disparadores de sólo agregado; no crean tablas con `create_all`. Reconstruyen el esquema entre pruebas: usá una `POSTGRES_TEST_DB` exclusiva y distinta de desarrollo. La fixture migrada verifica que la conexión apunte a la base de test asignada antes de limpiar.

Si la base de test no está disponible, los tests que la necesitan se **saltean** con el motivo; antes de cerrar un change tienen que correr con **0 skipped**. Los casos manuales están en `test/*.http` (extensión REST Client de VS Code), con la respuesta esperada en comentarios; **antes de correr cada archivo corré `python seed.py`** (D-3), porque los ids esperados salen del seed.

### Errores de entrada

Los datos inválidos responden **422** con mensajes en español, por ejemplo:

```json
{"detail": [{"msg": "Completá el documento."}]}
```

La respuesta no repite los datos enviados ni incluye ubicaciones o códigos internos de validación. Los errores de dominio **404/409** conservan `{"detail": "mensaje"}`; una página inexistente también conserva ese formato textual con estado **422**. OpenAPI describe ambos formatos de 422.

## Primitivas de autenticación (EJ-4 en curso)

`app/core/security.py` ofrece los helpers de bcrypt y JWT. **Está implementado sólo `POST /auth/registro`**; login, identidad (`/auth/yo`), logout y cambio de contraseña siguen pendientes. El CRUD y `actor_temporal` continúan abiertos hasta EJ-5.

| Interfaz pública | Uso |
|---|---|
| `configurar_semaforo_bcrypt(max_concurrencia: int) -> None` | Inicialización del lifespan; el seed conserva su configuración independiente. No reconfigurar por petición. |
| `async hashear_password(texto: str, rondas: int) -> str` | Genera sal y hash en un hilo, bajo el semáforo compartido. Firma existente conservada. |
| `async verificar_password(texto: str, password_hash: str) -> bool` | Mismo trabajo bcrypt para el hash del usuario o `app.state.hash_ficticio`; no genera otro hash ficticio. |
| `emitir_token(usuario_id: int, roles: list[str], settings: Settings, *, emitido_en: datetime \| None = None) -> str` | Firma `sub` textual, `iat` fraccional, `exp` y roles informativos; devuelve el token al llamador, nunca una respuesta HTTP. |
| `verificar_token(token: str, settings: Settings) -> ClaimsSesion` | Verifica firma, algoritmo configurado, presencia/tipos y vigencia. Devuelve `{sub, iat, exp, roles}` sin truncar los tiempos. |

Los futuros servicios deben validar las contraseñas (máximo **72 bytes UTF-8**) antes de bcrypt y liberar las transacciones durante ese trabajo. El hash ficticio se calcula una sola vez en el lifespan. Los helpers no crean motores, hashes, configuración ni claves al importar.

JWT reutiliza `JWT_SECRET` **fijo**, `JWT_ALGORITHM` y `ACCESS_TOKEN_EXPIRE_SECONDS`; bcrypt reutiliza `BCRYPT_ROUNDS` y `BCRYPT_MAX_CONCURRENCY`. No hay nuevas variables. `COOKIE_SECURE` configura la cookie del registro, no estas primitivas.

`TokenInvalido` rechaza tokens con firma/claims inválidos o vencidos con un mensaje humano. `sub` identifica al usuario como entero positivo textual; `roles` es una lista de textos, no una autorización. `iat` y `exp` deben ser números finitos (no cadenas ni booleanos); se comparan sin convertirlos a enteros. No se exige issuer ni audience.

Emitir sólo **después del commit**. `emitido_en` admite fechas con zona horaria (por defecto, ahora UTC) y debe ser igual o posterior al cambio de contraseña persistido. La futura dependencia comparará `claims["iat"] < password_cambiada_en.timestamp()` sin truncar y comprobará usuario activo/roles actuales: **esas comprobaciones de base y la revocación HTTP todavía no están implementadas**. El token sólo deberá transportarse en `access_token`, nunca en JSON ni en `Authorization`.

Pruebas focalizadas: `test/pytest/auth/test_bcrypt.py` y `test_jwt.py`, con bcrypt/PyJWT reales, límite concurrente, salud disponible y reloj controlado para instantes dentro del mismo segundo.

## Endpoints

> **Rutas abiertas hasta EJ-5 (T-11):** todavía no hay login; desde EJ-4 se suma `/auth` y desde EJ-5 estos grupos quedan protegidos por roles.

### Salud (públicas siempre)

| Método | Ruta | Qué responde |
|---|---|---|
| GET | `/health/live` | 200 mientras el proceso esté vivo (no consulta la base) |
| GET | `/health/ready` | 200 si la base contesta, 503 si no |

### Registro público (C-02)

`POST /auth/registro` recibe `{email, password, nombre, documento, telefono}` sin extras; `nombre` se usa también en la ficha. La contraseña admite hasta **72 bytes UTF-8** (36 `ñ`), sin requisitos nuevos de complejidad ni normalización de correo (DD-45).

- **201**: `{"mensaje":"Registro completado","debe_cambiar_password":false,"expira_en_segundos":1800}`; la duración real sale de `ACCESS_TOKEN_EXPIRE_SECONDS`.
- **409**: `{"detail":"Ya existe un usuario con ese correo."}` o `{"detail":"Ya existe un cliente con ese documento."}`. No vincula fichas existentes, aunque no tengan usuario.
- **422**: formato humano descrito arriba, sin eco de contraseñas.

El hash precede cualquier transacción. Usuario, rol CLIENTE, ficha y evento «Alta de usuario cliente (registro)» (actor: correo nuevo) se confirman juntos. Un fallo revierte el conjunto, incluso si falla el commit, y no entrega cookie.

Sólo tras confirmar se emite `access_token`: HttpOnly, SameSite=Lax, Path=/, sin Domain, Max-Age igual a la duración y Secure según `COOKIE_SECURE`. El cuerpo nunca incluye token ni hash. La consulta HTTP de identidad aún está pendiente; los tests verifican la cookie con el verificador JWT real.

Ejemplo ejecutable: `test/auth.http`, con contraseña efímera desde `REGISTRO_PASSWORD`. Corré seed antes del archivo **sólo sobre una base de test**, con API y seed apuntando a esa misma base. Pruebas automatizadas: `test/pytest/auth/test_registro{,_uow}.py` (HTTP, lectura independiente y fallo de commit).

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
| POST | `/repuestos/{id}/reponer` | Reposición de stock: 200 / 404 / 409 (supera el máximo de existencias) / 422 |
| GET | `/repuestos/{id}/movimientos` | Movimientos de stock en orden cronológico: 200 / 404 |
| GET | `/repuestos/{id}/precios` | Historial de precios en orden cronológico: 200 / 404 |

Los precios del alta y PATCH admiten valores exactos entre **0.01 y 99999999.99**, con hasta dos decimales significativos: no se redondean entradas como `0.001`. Los ceros finales equivalentes (`12.3400`) sí se admiten. `stock_inicial` va de **0 a 2147483647** y la cantidad de reposición de **1 a 2147483647**. Fuera de esos límites se responde **422**, sin escrituras; si una cantidad válida sumada al stock actual supera el máximo, se responde **409** sin modificar stock ni movimientos.

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
