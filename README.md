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

## Primitivas de autenticación (EJ-4)

`app/core/security.py` ofrece los helpers de bcrypt y JWT. **Están disponibles registro, login, `GET /auth/yo`, `POST /auth/logout` y `POST /auth/cambiar-password`**. Desde EJ-5 el CRUD y las rutas de datos exigen sesión y rol (ver más abajo); `actor_temporal` fue eliminado.

| Interfaz pública | Uso |
|---|---|
| `configurar_semaforo_bcrypt(max_concurrencia: int) -> None` | Inicialización del lifespan; el seed conserva su configuración independiente. No reconfigurar por petición. |
| `async hashear_password(texto: str, rondas: int) -> str` | Genera sal y hash en un hilo, bajo el semáforo compartido. Firma existente conservada. |
| `async verificar_password(texto: str, password_hash: str) -> bool` | Mismo trabajo bcrypt para el hash del usuario o `app.state.hash_ficticio`; no genera otro hash ficticio. |
| `emitir_token(usuario_id: int, roles: list[str], settings: Settings, *, emitido_en: datetime \| None = None) -> str` | Firma `sub` textual, `iat` fraccional, `exp` y roles informativos; devuelve el token al llamador, nunca una respuesta HTTP. |
| `verificar_token(token: str, settings: Settings) -> ClaimsSesion` | Verifica firma, algoritmo configurado, presencia/tipos y vigencia. Devuelve `{sub, iat, exp, roles}` sin truncar los tiempos. |

Registro/login/cambio validan las contraseñas (máximo **72 bytes UTF-8**) antes de bcrypt y liberan las transacciones durante ese trabajo. El hash ficticio se calcula una sola vez en el lifespan. Los helpers no crean motores, hashes, configuración ni claves al importar.

JWT reutiliza `JWT_SECRET` **fijo**, `JWT_ALGORITHM` y `ACCESS_TOKEN_EXPIRE_SECONDS`; bcrypt reutiliza `BCRYPT_ROUNDS` y `BCRYPT_MAX_CONCURRENCY`. No hay nuevas variables. `COOKIE_SECURE` configura la emisión y eliminación de cookies, no estas primitivas.

`TokenInvalido` rechaza tokens con firma/claims inválidos o vencidos con un mensaje humano. `sub` identifica al usuario como entero positivo textual; `roles` es una lista de textos, no una autorización. `iat` y `exp` deben ser números finitos (no cadenas ni booleanos); se comparan sin convertirlos a enteros. No se exige issuer ni audience.

Emitir sólo **después del commit**. `emitido_en` admite fechas con zona horaria (por defecto, ahora UTC) y debe ser igual o posterior al cambio de contraseña persistido. `get_usuario_actual` compara `claims["iat"] < password_cambiada_en.timestamp()` sin truncar y comprueba usuario activo/roles actuales. El token se transporta sólo en `access_token`, nunca en JSON ni se autentica desde `Authorization`.

Pruebas focalizadas: `test/pytest/auth/test_bcrypt.py` y `test_jwt.py`, con bcrypt/PyJWT reales, límite concurrente, salud disponible y reloj controlado para instantes dentro del mismo segundo.

### Login limitado y auditado (OPSX 4.2–4.3)

`POST /auth/login` recibe `{email, password}` sin extras ni normalización del correo; contraseña de hasta 72 bytes UTF-8. No acepta credenciales desde `Authorization`.

| Resultado | Respuesta |
|---|---|
| 200 | `{"mensaje":"Sesión iniciada","debe_cambiar_password":false,"expira_en_segundos":1800}`; bandera del usuario y duración configurada. Cookie con los mismos atributos que registro, sin token/hash en JSON. |
| 401 | `{"detail":"El correo o la contraseña no son correctos."}` tanto para correo inexistente como contraseña incorrecta. |
| 401, inactivo con contraseña correcta | `{"detail":"Tu cuenta está desactivada. Comunicate con el taller para reactivarla."}` |
| 429 | `{"detail":"Demasiados intentos. Volvé a intentar más tarde."}` con `Retry-After`; sin buscar credenciales ni ejecutar bcrypt. |
| 422 | Formato humano sin eco de entrada, sin bcrypt ni escrituras. |

OpenAPI documenta estos cuatro estados y `Retry-After`. Los rechazos no emiten cookie nueva.

| Interfaz en `app/modules/usuarios/` | Contrato |
|---|---|
| `repository.IntentoAccesoRepository.consultar_ventana(email: str, ip: str, ahora: datetime) -> VentanaIntentos` (async) | Una consulta con parámetros ligados devuelve `fallos: int` y `fallo_mas_antiguo: datetime \| None`; `ahora` lleva zona horaria. |
| `unit_of_work.UnitOfWorkIntentoAcceso(sesion: AsyncSession)` | Expone `intentos`; `add` sólo hace flush. Confirma al salir del bloque; revierte y propaga fallos de operación/flush/commit, sin cerrar la sesión. |
| `router.get_session_intentos(request)` → `construir_uow_intentos(sesion)` / `UowIntentosDep` | Dependencia separada crea/cierra otra sesión y entrega el UoW **sin abrir** al servicio de login. No se conecta al registro. |

[D3 / DD-46](knowledge-base/09_decisiones_y_supuestos.md#dd-46--ventana-de-intentos-ej-4-d3): ventana **(ahora − 60 s, ahora]**, sólo fallos posteriores al último éxito del mismo par correo/IP. El historial permanece; las filas bloqueadas guardadas como `exito=false` también cuentan. El servicio decide bloqueo con `fallos >= 5` y calcula `Retry-After = max(1, ceil((fallo_mas_antiguo + 60 s - ahora).total_seconds()))`. No promete acceso al vencer ese plazo: debe consultar otra vez, sin bloqueo fijo adicional.

La excepción transaccional cuesta **otra conexión/transacción** y conserva intentos confirmados aunque la petición normal revierta. No usa tareas de fondo, locks ni garantías globales de concurrencia. El evento «Login bloqueado por demasiados intentos» (actor: correo intentado) se confirma en el UoW normal, después del intento. Si falla ese evento, el intento permanece. El login no bloqueado no duplica su intento como evento.

El servicio cierra las lecturas cortas con UoW antes de bcrypt real/ficticio y conserva sólo primitivas. Precarga roles y filtra los revocados/vencidos para el JWT. Cada resultado válido confirma su intento antes de devolver éxito/401/429; un fallo de persistencia obligatoria no entrega sesión ni cookie.

**Pruebas automatizadas:** `test/pytest/auth/test_login.py` usa HTTP ASGI, PostgreSQL/Alembic, bcrypt real y lecturas independientes: éxito, ambos 401, sexto bloqueo, rollback, validación y OpenAPI. Mide tres verificaciones reales/ficticias por camino, sin umbral absoluto ni esperas artificiales. Incluye bordes de 60 s, intentos futuros excluidos, reset por último éxito sin borrar (también fechas iguales), aislamiento de correo exacto/IP, conteo de nuevos 429, Retry-After mínimo, 72 bytes válidos y JSON/correo inválidos. `test_intentos.py` conserva además la cobertura del repositorio.

**Casos manuales:** `test/auth.http` conserva C-02 y agrega C-04/C-05 con sesiones nombradas, sin cookie jar implícito. Definí `REGISTRO_PASSWORD` y `LOGIN_PASSWORD_INCORRECTA` distintas, de hasta 72 bytes; ejecutá seed sobre la misma base aislada de prueba que usa la API. Corré el archivo en orden, con los seis intentos C-05 dentro de 60 s. Deben quedar nueve intentos (ocho fallidos y uno exitoso), un evento de registro y un evento bloqueado adicionales al seed; ningún intento se borra. **Evidencia de esta unidad:** los 12 bloques C-02/C-04/C-05 se ejecutaron por TCP tras Alembic/seed en bases aisladas. La suite completa y su verificación independiente dieron 531 pruebas aprobadas, ninguna omitida y 18 advertencias conocidas de la clave JWT de test. El diferencial contra `b3a903a` conservó 75 solicitudes por versión y 15 operaciones OpenAPI existentes sin diferencias no solicitadas. Esa evidencia corresponde a T4 (registro/login), no a T5, cambio de contraseña o EJ-5.

### Identidad y logout (OPSX 5.1–5.3)

- `GET /auth/yo` exige exclusivamente cookie: devuelve `usuario: {id,email,nombre,debe_cambiar_password}`, `roles_vigentes` y `roles_token`, sin secretos ni cookie nueva. Los roles actuales se precargan y excluyen revocados/vencidos; tener cero roles o cambio pendiente no impide esta consulta.
- Cookie ausente (también Bearer sin cookie), JWT inválido/vencido, usuario inexistente/inactivo o emisión anterior al último cambio → **401** `{"detail":"La sesión no es válida. Volvé a iniciar sesión."}`. Se conserva la fracción original; igualdad con el cambio es válida.
- `POST /auth/logout` es público, incluso con cookie inválida/ausente: **200** `{"mensaje":"Sesión cerrada"}` y eliminación con Path=/, sin Domain, HttpOnly, SameSite=Lax, Secure configurable, Max-Age=0 y Expires pasado. No modifica la base ni revoca copias del JWT: pueden seguir válidas hasta expirar/cambiar contraseña.
- OpenAPI publica yo 200/401 y logout 200, ambos con el 422 heredado del montaje común. El RBAC y el bloqueo global por contraseña pendiente se describen en la sección de autorización (EJ-5).

`test_identidad.py`/`test_logout.py` verifican HTTP ASGI y PostgreSQL/Alembic reales: claims, estado actual, frontera ±1 microsegundo, roles cambiados, eliminación y ausencia de escrituras. Focalizadas T5 + expectativa OpenAPI previa: **33 aprobadas, 0 omitidas**. La suite completa y la ejecución host solicitada por el verificador independiente dieron **563 aprobadas, 0 omitidas y 76 advertencias conocidas** de la clave JWT de fixture. Los **22 bloques TCP** pasaron tras Alembic/seed en bases aisladas. El diferencial contra `9cb3f16` conservó 15 solicitudes por versión a los tres consumidores de `actor_temporal`, con códigos, cuerpos, encabezados y efectos auditados equivalentes. Sólo normaliza fechas previamente validadas; compara stderr bajo el mismo formato sin frames de traceback. El dictamen independiente cubre T5, no cambio de contraseña, EJ-5 ni cierre global de EJ-4.

`test/auth.http` conserva C-01/C-03 y yo/logout junto con C-02/C-04/C-05 y C-09 parcial (28 bloques en total). Para el bloque Bearer, copiá sólo el JWT de `loginCliente` a la variable local `TOKEN_SOLO_BEARER`, nunca al archivo. Las otras sesiones usan cookies nombradas y `# @no-cookie-jar`; el bloque posterior al logout omite deliberadamente toda cookie.

### Cambio de contraseña (OPSX 6.1–6.3)

`POST /auth/cambiar-password` exige la cookie de sesión existente, también si hay cambio pendiente. Recibe `{password_actual,password_nueva}`, ambos de texto y hasta 72 bytes UTF-8, sin extras. No añade complejidad ni normalización.

- **200**: `{"mensaje":"Contraseña actualizada","debe_cambiar_password":false,"expira_en_segundos":1800}`; duración configurada, nunca token/hash en JSON.
- **401**: contraseña actual incorrecta → `{"detail":"La contraseña actual no es correcta."}`; sesión ausente/inválida/vencida/revocada o usuario inactivo → mensaje de identidad existente.
- **422**: validación humana sin eco, bcrypt ni escrituras. OpenAPI publica 200/401/422.

La lectura termina antes de verificar/calcular bcrypt (hilo y semáforo existentes). Hash, fecha UTC con microsegundos, bandera falsa y evento «Cambio de contraseña» con el correo del usuario se confirman en un único UoW. Fallar una escritura/commit revierte todo, sin llamar al emisor de cookie. Sólo después se entrega `access_token` de reemplazo con los atributos habituales, roles vigentes e `iat` igual a la fecha persistida: la cookie anterior deja de valer inmediatamente, incluso dentro del mismo segundo. No hay locks/CAS ni garantías nuevas de concurrencia.

**Evidencia funcional:** RED HTTP 404 del implementador; verificación final focalizada de cambio + registro: 45 aprobadas sin omisiones, incluidas las aserciones de rollback. La ejecución host preparada por el verificador independiente aprobó **595 pruebas, 0 omitidas y 132 advertencias conocidas de clave JWT de fixture**, más los **28 bloques TCP** sobre PostgreSQL migrada/seed aislados. El diferencial contra `c36b50e` aprobó 48 solicitudes por versión a registro/login, con Secure activado/desactivado y comparación de exit/stdout/stderr; sólo normaliza sales bcrypt verificadas, fechas conscientes de zona y JWT/tiempos previamente validados. El dictamen independiente aprueba 6.1–6.3, sin atribuirle el RED histórico ni una revisión nativa.

**C-09 parcial ejecutado por TCP:** `test/auth.http` conserva los 22 bloques anteriores y agrega seis (28 total). Definí `PASSWORD_PENDIENTE` con la contraseña de `nuevo@example.com` del seed y `PASSWORD_NUEVA` distinta, efímera y de hasta 72 bytes; nunca las guardes en el archivo. Usa una cuenta distinta de la bloqueada por C-05, cookies nombradas y sin cookie jar. Al terminar se esperan 12 intentos (9 fallidos/3 exitosos) y cuatro eventos incluido seed. El bloqueo global **403** y el RBAC completan C-09 en EJ-5 (ver sección siguiente); el archivo `test/autorizacion.http` los demuestra.

## Autorización por roles (EJ-5)

`app/core/dependencies.py` implementa los controles en este orden (DD-50): **identidad** (`get_usuario_actual`, 401 ante cualquier fallo de cookie/firma/vigencia) → **cambio obligatorio** (`cambio_pendiente_bloqueado`, dependencia del grupo protegido montada una sola vez en `main.py`, 403 si `debe_cambiar_password`) → **rol** (`requiere_rol(*roles)`, 403 si falta el rol vigente; consulta `asignacion_rol` **en cada petición**, sin caché y sin mirar el JWT — RN-04). Sin sesión siempre hay 401 antes que cualquier 403.

| Ruta | Quién |
|---|---|
| `POST /clientes`, `GET /clientes/{id}`, `POST /clientes/{id}/vehiculos`, `DELETE /vehiculos/{id}` | ADMIN, RECEPCION |
| `GET /repuestos`, `GET /repuestos/{id}` | ADMIN, RECEPCION, MECANICO |
| `POST/PATCH/DELETE /repuestos`, `/reponer`, `/movimientos`, `/precios` | ADMIN |
| `POST /usuarios`, `GET/POST /usuarios/{id}/roles`, `DELETE /usuarios/{id}/roles/{rol}`, `GET /eventos` | ADMIN |
| `GET /mis-vehiculos`, `GET /mis-ordenes` | Cualquier sesión (sólo lo propio; vacío sin ficha — SU-11) |

El alta de personal (`POST /usuarios`) crea usuario + asignación de rol (`otorgada_por` = admin) + evento en un solo UoW, con `debe_cambiar_password = true` (DD-18). Revocar un rol escribe `revocada_en` sin borrar la fila y surte efecto en la siguiente petición de la sesión abierta (C-07); la autoprotección RN-05 impide revocar el propio ADMIN o quedar sin administradores. Los eventos de seguridad se consultan paginados en `GET /eventos` (ADMIN).

El helper `es_personal_o_dueno` (`app/modules/ordenes/service.py`) queda listo para el 403 de orden ajena de EJ-6 (T-8). El reemplazo del actor temporal garantiza que `movimiento_stock` e `historial_precio_repuesto` firman con el usuario autenticado; sin sesión no se escribe nada.

**Pruebas:** `test/pytest/autorizacion/` (104 pruebas: schemas, identidad, protección de rutas, roles, alta personal, eventos/lo propio) y `test/autorizacion.http` (C-06 parcial, C-07, C-08, C-09 completo). C-18 (recepción 403 al cambiar precio sin línea de historial) vive en `test/repuestos.http`. La suite completa dio **697 aprobadas + 2 fallos ambientales conocidos de Windows/loopback** (sin relation con el producto; ver `odd/tasks/05-autorizacion.md` L2).

## Endpoints

> **Desde EJ-5 (T-11)** `main.py` monta dos grupos: abierto (`/health/*`, `/auth/*`) y protegido (el resto), con el control de cambio de contraseña pendiente montado una sola vez sobre el grupo protegido. Las rutas de datos exigen sesión y el rol de la matriz RBAC (`knowledge-base/03_actores_y_roles.md`).

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

Sólo tras confirmar se emite `access_token`: HttpOnly, SameSite=Lax, Path=/, sin Domain, Max-Age igual a la duración y Secure según `COOKIE_SECURE`. El cuerpo nunca incluye token ni hash. La cookie también permite consultar `/auth/yo`; los tests verifican ambas rutas con JWT y base reales.

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
