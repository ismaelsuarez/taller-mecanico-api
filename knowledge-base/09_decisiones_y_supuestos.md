# Decisiones y Supuestos

## Decisiones documentadas (tomadas por la consigna)

### DD-01 — Roles en tabla propia con vigencia
**Decisión**: `usuario` no tiene columna `rol`; los roles son filas vigentes de `asignacion_rol`.
**Contexto**: el admin asigna y revoca roles con vencimiento; hay que saber quién tuvo qué rol y hasta cuándo.
**Alternativas consideradas**: columna `rol` en `usuario`; roles sólo en el token.
**Justificación**: la autorización se decide en la base en cada petición; revocar quita el permiso a una sesión abierta (5.9).
**Trade-offs aceptados**: una consulta extra por petición protegida.

### DD-02 — Catálogo `estado_orden` en lugar de CHECK
**Decisión**: tabla de referencia con PK `codigo`, apuntada por FK, cargada por `seed.py`; en código, un enum.
**Contexto**: los estados son una lista fija que el sistema necesita para funcionar.
**Alternativas consideradas**: `CHECK (estado IN (...))`.
**Justificación**: la base sigue rechazando estados inexistentes (por FK) y cada estado tiene datos propios (`es_final`, `posicion`) que la API muestra y las consultas cruzan. PK `codigo` para que se lea igual en psql y en la API.
**Trade-offs aceptados**: agregar un estado obliga a tocar catálogo, enum y servicio.

### DD-03 — Índices únicos parciales para patente y código
**Decisión**: `UNIQUE (patente) WHERE borrado_en IS NULL` y `UNIQUE (codigo) WHERE borrado_en IS NULL`.
**Justificación**: con borrado lógico, un UNIQUE común impediría registrar un auto vendido.

### DD-04 — Token sólo en cookie HttpOnly
**Decisión**: el JWT viaja sólo en `Set-Cookie`; no en el cuerpo ni en `Authorization`.
**Justificación**: no accesible desde JS; C-03 exige 401 con `Authorization: Bearer`.

### DD-05 — Intento de acceso en transacción propia
**Decisión**: es la única escritura que no comparte la transacción de su petición.
**Justificación**: el fallo que se quiere contar es el mismo que revierte la transacción de la petición (6.8.1).
**Trade-offs aceptados**: deja filas aunque la petición falle (se declara en un comentario).

### DD-06 — Sólo agregado por disparador
**Decisión**: disparador instalado por una migración escrita a mano.
**Alternativas consideradas**: quitar permisos de UPDATE/DELETE al rol de base (6.9).
**Justificación**: el TP usa un solo rol de base; cualquiera de los dos alcanza.

### DD-07 — Aviso al cliente con `BackgroundTasks`
**Decisión**: tarea en el mismo proceso, después de la respuesta, sólo si se confirmó.
**Trade-offs aceptados**: si el proceso se reinicia, el aviso se pierde y no hay reintento (se resuelve en cap. 8).

### DD-08 — Sin control de concurrencia en el stock
**Decisión**: no se bloquean filas al terminar órdenes.
**Trade-offs aceptados**: posible actualización perdida (cap. 7).

### DD-09 — Recursos creados en el lifespan
**Decisión**: motor y fábrica en `app.state` desde el lifespan; nunca al importar.
**Justificación**: un recurso construido al importar se crea antes que el bucle de eventos (EA-08).

### DD-10 — Dos grupos de rutas para el cambio obligatorio
**Decisión**: grupo abierto + grupo protegido con el control montado una vez.
**Justificación**: FastAPI suma dependencias y no las resta (5.10).

### DD-11 — Idioma de la KB y del código de dominio
**Decisión** (de esta KB): la KB se escribe en español porque la consigna, los nombres de tablas/columnas obligatorios y las rutas están en español.
**Resuelto** (ver DD-12): identificadores no fijados por la consigna en español.

### DD-12 — Identificadores de código en español
**Decisión**: los identificadores que la consigna no fija (servicios, métodos, variables) van en español; los nombres técnicos que la consigna da en inglés (`get_by_id`, `soft_delete`, `flush`…) se respetan tal cual.
**Contexto**: tablas, columnas, rutas y varios nombres (`get_usuario_actual`, `requiere_rol`) ya están en español en la consigna.
**Alternativas consideradas**: identificadores nuevos en inglés.
**Justificación**: un solo idioma de dominio por módulo; menos traducción mental al leer la consigna.
**Trade-offs aceptados**: convive con algunos nombres técnicos en inglés impuestos por la consigna.

### DD-13 — Tests: `.http` para la entrega + pytest para TDD
**Decisión**: los `.http` de `test/` cubren C-01..C-19 (entrega). Además, pytest + httpx contra una PostgreSQL real de test, en `test/pytest/`, para el ciclo RED/GREEN.
**Contexto**: la consigna sólo pide `.http`; la configuración del equipo exige TDD con un runner automático.
**Alternativas consideradas**: sólo `.http` (TDD como excepción manual).
**Justificación**: TDD real y sin mocks de la base; los `.http` siguen siendo la evidencia que se corrige.
**Trade-offs aceptados**: más trabajo por change; requiere una base de test. EJ-1 configura el runner.

### DD-14 — Actores del seed (resuelve SU-01)
**Decisión**: las escrituras del seed llevan un `usuario_id` real y coherente con las reglas: stock inicial e historial de precio del filtro → `admin@example.com`; alta de las órdenes 1 y 2 (`null → PENDIENTE`) → `recepcion@example.com`; inicio de la orden 2 (`PENDIENTE → EN_REPARACION`) → `mecanico@example.com` (el asignado).
**Contexto**: `usuario_id` no es nulo en `movimiento_stock`, `historial_precio_repuesto` ni `historial_estado_orden`; `SISTEMA` sólo es texto en `evento_seguridad.actor`.
**Alternativas consideradas**: todo con admin@; hacer la columna nullable (se desvía de la consigna).
**Justificación**: el historial de `GET /ordenes/2` cuenta una historia coherente con RN-11; coincide con el ejemplo de la consigna (`usuario_id: 3` = recepción crea la orden).

### DD-15 — Ítems de la orden 1 del seed (resuelve IN-03)
**Decisión**: orden 1 `PENDIENTE`, falla «Cambio de aceite y filtro», 1 × Filtro de aceite (8500.00) + 4 × Aceite 5W30 por litro (12000.00) → total **56500.00**.
**Justificación**: cumple RN-10; al estar pendiente no toca el stock de los ejemplos; deja lista una orden de 2 ítems para C-15.

### DD-16 — Bujía del seed
**Decisión**: código `BUJ-014`, descripción «Bujía de encendido», precio **6500.00**, stock 2 (id 3). Orden 2: falla «Falla de encendido», 4 bujías → total **26000.00**, `mecanico_id` = mecanico@example.com.
**Justificación**: sigue el patrón de códigos de la consigna (`FIL-001`, `FRE-010`, `ACE-530`); ningún caso depende del valor exacto, pero fijarlo da respuestas esperadas iguales para todo el equipo.

### DD-17 — Cuerpo y sesión de `POST /auth/registro`
**Decisión**: cuerpo plano `{email, password, nombre, documento, telefono}` (`extra="forbid"`; `nombre` se usa para el usuario y para la ficha de cliente). Responde **201 con `Set-Cookie access_token`** (misma cookie que el login: `HttpOnly`, `SameSite=Lax`, `Max-Age`, `Secure` configurable), emitida **después** de que el UoW confirma; el cuerpo de la respuesta nunca trae el token. Si el UoW revierte (409), no se emite cookie ni quedan filas.
**Origen**: pedido verbal del docente («tiene que usar cookies») + elección del equipo del contrato más robusto.
**Alternativas consideradas**: registro sin sesión (login aparte); cuerpo anidado `{usuario, cliente}`.
**Trade-offs aceptados**: el registro también emite token; se registra el alta en `evento_seguridad`.

### DD-18 — Cuerpo de `POST /usuarios` (resuelve SU-13)
**Decisión**: `{email, nombre, password_provisoria, rol}` con `rol ∈ {ADMIN, RECEPCION, MECANICO}` (`CLIENTE` → 422: los clientes entran por el registro). Se crea con `debe_cambiar_password = true`. Usuario + `asignacion_rol` (`otorgada_por` = admin actual) + `evento_seguridad` en **un solo UoW**.
**Alternativas consideradas**: alta sin rol + `POST /usuarios/{id}/roles` aparte.
**Justificación**: evita usuarios de personal huérfanos sin rol; una sola operación atómica.

### DD-19 — Todo commit pasa por un Unit of Work, incluido `intento_acceso`
**Decisión**: ningún código confirma fuera de un UoW. La escritura de `intento_acceso`, que la consigna exige en sesión y transacción propias (Ej. 7, 6.8.1), usa un **UoW dedicado de intentos de acceso** con su propia sesión, que se confirma siempre.
**Origen**: pedido verbal del docente («los flujos de commit sí o sí tienen que estar en la unidad de trabajo») compatibilizado con la consigna.
**Trade-offs aceptados**: un UoW extra en el módulo `usuarios`; el comentario del código declara la excepción de transacción y su costo (deja filas aunque la petición falle).

### DD-20 — Clave de firma del JWT fija
**Decisión**: `JWT_SECRET` se lee del entorno (`.env`), sin valor por defecto, y **nunca** se genera al arrancar.
**Origen**: consigna (pág. 3–4, sección 5.12) + pedido verbal del docente.
**Justificación**: una clave generada en cada arranque invalida todas las sesiones al reiniciar (todos se tienen que volver a loguear) y con dos procesos cada uno rechaza los tokens del otro.

> **Criterio del equipo para DD-21..DD-32** (revisión del 2026-10-25): ante cada hueco se eligió la opción más sólida pensando en el sistema en producción, sin contradecir la consigna.

### DD-21 — Repuesto dado de baja con órdenes abiertas
**Decisión**: `DELETE /repuestos/{id}` siempre se permite (204), aunque el repuesto esté en órdenes abiertas. Las órdenes **ya creadas** con ese repuesto se inician, terminan y cancelan normalmente: terminar lo carga con `get_by_id_including_deleted` y descuenta su stock. Sólo se bloquea su uso en órdenes **nuevas** (409, RN-16).
**Justificación**: la tabla de la consigna no lista 409 para esta baja; RN-16 restringe sólo las órdenes nuevas.

### DD-22 — Baja de un recurso ya dado de baja → 404
**Decisión**: `DELETE /vehiculos/{id}` y `DELETE /repuestos/{id}` sobre un recurso ya dado de baja responden **404**.
**Justificación**: para la API el recurso no existe (`get_by_id` filtra los dados de baja; RN-16 «deja de aparecer»). DELETE sigue siendo idempotente por su efecto (RFC 9110). Coherente con `GET` → 404 y no revela registros ocultos.

### DD-23 — `stock_inicial ≥ 0`
**Decisión**: `POST /repuestos` acepta `stock_inicial ≥ 0` (default 0). Si es 0 no se crea movimiento (CHECK `cantidad <> 0`); negativo → 422.
**Justificación**: dar de alta repuestos sin stock es habitual; el historial de movimientos sigue explicando el stock exacto. Resuelve SU-14.

### DD-24 — Login de un usuario inactivo
**Decisión**: contraseña incorrecta o correo inexistente (cuenta activa o inactiva) → **401** con el mensaje genérico «El correo o la contraseña no son correctos.». Contraseña **correcta** con cuenta inactiva → **401** con «Tu cuenta está desactivada. Comunicate con el taller para reactivarla.». Siempre se verifica el hash (mismo tiempo) y el intento se anota con `exito = false`.
**Origen**: pedido del usuario («información más clara al usuario, lenguaje humano») compatibilizado con RN-09.
**Justificación**: el mensaje específico sólo lo ve quien demostró conocer la contraseña, así que no permite enumerar cuentas. Se usa 401 porque la consigna no lista 403 para `/auth/login`. Reemplaza SU-04.

### DD-25 — Mensajes de error en lenguaje humano
**Decisión**: todo mensaje de error dirigido al usuario está en español claro, sin jerga técnica, sin nombres de tablas, columnas o restricciones, sin trazas ni códigos internos. Ej.: «Ya existe un cliente con ese documento.» en lugar del texto del `IntegrityError`.
**Origen**: pedido del usuario. Refuerza RN-18.

### DD-26 — Acciones de `evento_seguridad`
**Decisión**: se registran, con `accion` en español claro: «Alta de usuario cliente (registro)» (actor: correo del nuevo usuario), «Alta de personal con rol X» (actor: admin), «Rol X asignado a Y» / «Rol X revocado a Y» (actor: admin), «Cambio de contraseña» (actor: el usuario), «Login bloqueado por demasiados intentos» (en el 429; actor: correo intentado) y «Carga de los datos iniciales» (actor: `SISTEMA`). Los logins comunes no: ya quedan en `intento_acceso`.
**Justificación**: lo que pide la consigna más la señal de ataque que un admin quiere ver en `GET /eventos`, sin ruido.

### DD-27 — El personal ve cualquier orden
**Decisión**: ADMIN, RECEPCION y MECANICO ven el detalle de cualquier orden (`GET /ordenes/{id}`). El 403 por orden ajena (RN-17) aplica sólo a quien no es personal.
**Justificación**: el mecánico necesita ver las órdenes `PENDIENTE` para tomarlas; coherente con `GET /ordenes`. La restricción fuerte está en terminar (RN-11). Resuelve SU-03.

### DD-28 — `/mis-*` y vehículos dados de baja
**Decisión**: `/mis-vehiculos` muestra sólo los vigentes; `/mis-ordenes` muestra todas las órdenes de los vehículos del cliente, incluidas las de vehículos dados de baja. El dueño sigue viendo el detalle de esas órdenes (200).
**Justificación**: RN-16 («deja de aparecer» / «sus órdenes viejas siguen»). Al registrar de nuevo la patente se crea otra fila de `vehiculo`, así que comprador y vendedor no ven el historial del otro.

### DD-29 — Motivos de `movimiento_stock` y cuerpo de `/reponer`
**Decisión**: «Stock inicial» (alta), «Salida por orden de trabajo #N» (terminación; además con `orden_id`), ambos armados por el servidor. `POST /repuestos/{id}/reponer` recibe `{cantidad (> 0), motivo? (≤ 120 caracteres)}`; sin motivo → «Reposición». Responde 200 con el repuesto y su stock.
**Justificación**: trazabilidad real (factura, remito, ajuste) sin dejar que el cliente invente salidas.

### DD-30 — Variables de entorno
**Decisión**: `POSTGRES_USER`, `POSTGRES_PASSWORD` (sin default), `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_TEST_DB` (base de pytest), `JWT_SECRET` (sin default, fijo), `JWT_ALGORITHM` (`HS256`), `ACCESS_TOKEN_EXPIRE_SECONDS` (`1800`), `COOKIE_SECURE` (`false`; `true` en producción), `BCRYPT_ROUNDS` (`12`), `BCRYPT_MAX_CONCURRENCY` (`4`), `DB_POOL_SIZE` (`5`), `SQL_ECHO` (`false`). Resuelve SU-12.

### DD-31 — El ADMIN que termina no cambia `mecanico_id`
**Decisión**: `mecanico_id` conserva al mecánico que inició (quien hizo el trabajo). Quién cerró queda en `historial_estado_orden.usuario_id` y en los movimientos de esa terminación.

### DD-32 — Docker: app + base
**Decisión**: `Dockerfile` multi-stage (Python 3.12 slim, usuario no-root) + `docker-compose.yml` con `api` (uvicorn) y `db` (`postgres:16`, volumen, healthcheck, base de test). Credenciales desde `.env`, nunca en el compose. El README documenta también la puesta en marcha con venv que exige la consigna. Lo arma EJ-1.
**Alternativas consideradas**: sólo la base en Docker; sin Docker.
**Justificación**: entorno idéntico para todo el equipo en los relevos.
**Trade-offs aceptados**: más trabajo en EJ-1 y dos caminos de arranque que mantener documentados.

### DD-33 — Un secreto vacío cuenta como faltante (EJ-1)
**Decisión**: `JWT_SECRET` y `POSTGRES_PASSWORD` exigen al menos un carácter: vacíos, la aplicación no arranca y el error nombra la variable.
**Contexto**: `env.example` trae los secretos vacíos a propósito; copiarlo como `.env` sin completarlo dejaba la variable *definida pero vacía*, y la app arrancaba firmando tokens con una clave vacía.
**Justificación**: detectado durante la implementación de EJ-1; cubierto por `test_un_secreto_vacio_cuenta_como_faltante` y verificado con Docker (sale con código 3 y no muestra secretos).

### DD-34 — Convenciones de los tests automáticos (EJ-1)
**Decisión**: para todos los changes siguientes:
- `test/` y `test/pytest/` **no** llevan `__init__.py`: `test` chocaría con el paquete `test` de la biblioteca estándar de Python. Las utilidades compartidas se importan con `from conftest import ...` (pytest agrega esa carpeta al path; `pytest.ini` define `pythonpath = .`).
- La fixture `configurar_entorno` fuerza `JWT_SECRET` de test, apunta `POSTGRES_DB` a `POSTGRES_TEST_DB` (nunca a la base de desarrollo) y baja `BCRYPT_ROUNDS` a 4 para que los tests sean rápidos.
- `aplicacion_iniciada()` corre el lifespan real (httpx `ASGITransport` no lo dispara solo); `cliente_http(app)` da el cliente.
- Para simular caídas de la base se usa un puerto sin servicio o el `ProxyTCP` de `test_salud.py`; no hace falta detener Docker.
- Cierre de cada change: `pytest -rs` con `db` levantada y **0 skipped**.
**Contexto**: el venv del proyecto es Python 3.12 (`uv venv --python 3.12`); quedó instalado bcrypt 5, que **lanza una excepción con contraseñas de más de 72 bytes** (lo valida el contrato en EJ-4).

### DD-35 — Correcciones de la revisión del EJ-1
**Decisión**: se corrigieron las 4 advertencias de la revisión `review-cf431af11a3fca38` (change `fix-advertencias-revision-ej1`): PostgreSQL de Docker publicado sólo en `127.0.0.1`; `/health/ready` registra en el logger `app.salud` el **tipo** de falla de cada 503 (nunca el mensaje ni secretos); el motor se libera aunque el arranque falle después de crearlo; los tests con base se saltean si la base no responde.
**Pendiente (sugerencias no bloqueantes, para cuando toque esos archivos)**: `url_base_datos` aparece en `Settings.model_dump()` con la contraseña (no serializar ni loguear `settings`); `pg_isready` del healthcheck sin `-h 127.0.0.1`; la sonda de preparación comparte el pool de la app; `ProxyTCP` de los tests no cierra el lado cliente si falla la conexión a la base.

### DD-36 — El seed limpia con `TRUNCATE`, no con `DELETE` (EJ-2)
**Decisión**: `seed.py` vacía las tablas con `TRUNCATE TABLE ... RESTART IDENTITY CASCADE` (en orden inverso a las dependencias) antes de recargar.
**Contexto**: los disparadores de sólo agregado (RN-15) son `BEFORE UPDATE OR DELETE ... FOR EACH ROW`; un `DELETE` normal sobre `historial_estado_orden`, `movimiento_stock` o `historial_precio_repuesto` los dispara y la segunda corrida del seed fallaba.
**Justificación**: `TRUNCATE` es a nivel de sentencia y no dispara triggers `FOR EACH ROW`, así que el seed puede recargar las tablas de auditoría sin desinstalar el disparador (que además es la garantía que la consigna pide en runtime). `RESTART IDENTITY` deja los ids del seed predecibles (orden 1, orden 2, repuestos 1..4).
**Trade-offs aceptados**: `TRUNCATE` necesita privilegios de owner; acá corre con el mismo rol que creó las tablas.

### DD-37 — Las migraciones de EJ-2 van en dos revisiones encadenadas (EJ-2)
**Decisión**: `f8513bf4e6fc` (autogenerada: las 13 tablas) y `a1b2c3d4e5f6` (escrita a mano: `solo_agregado()` + los tres `trg_<tabla>_solo_agregado`). `alembic.ini` no lleva `sqlalchemy.url`; `migrations/env.py` arma la URL desde `cargar_settings().url_base_datos` e importa los modelos de los 4 módulos.
**Justificación**: Alembic no compara funciones ni triggers, así que el autogenerate no los ve; separarlos deja el diff de la migración 2 minimalista y revisable a mano (A-3). El test de migraciones corre los comandos de Alembic en un hilo (`asyncio.to_thread` + `ThreadPoolExecutor`) porque `env.py` llama `asyncio.run`.
**Trade-offs aceptados**: dos migraciones que suben y bajan juntas; el `downgrade` de la 1 debe ir después del de la 2 (orden inverso, automático en Alembic).

## Supuestos inferidos

### SU-01 — FKs de `usuario_id` en historiales y movimientos
**Supuesto**: `historial_estado_orden.usuario_id`, `movimiento_stock.usuario_id` y `historial_precio_repuesto.usuario_id` son FK a `usuario.id`, no nulas.
**Origen**: tabla del modelo (no marcadas "(nulo)"); la Figura 1 no las dibuja.
**Resolución del seed**: ver DD-14.

### SU-02 — `otorgada_por` es FK a usuario
**Supuesto**: `asignacion_rol.otorgada_por` → `usuario.id`, nulo para asignaciones del seed/registro.
**Origen**: nombre de la columna. **Riesgo**: bajo.

### SU-03 — "El personal" = ADMIN, RECEPCION, MECANICO
**Origen**: tabla de endpoints (`GET /ordenes/{id}`). Confirmado por DD-27.

### SU-04 — ~~Usuario inactivo en login → 401 con el mismo cuerpo~~
**Reemplazado por DD-24.**

### SU-05 — Contraseña actual incorrecta en el cambio → 401
**Origen**: códigos del endpoint (200, 401, 422). **Riesgo**: bajo.

### SU-06 — Referencias inválidas en el cuerpo → 409, no 404
**Supuesto**: `vehiculo_id`/`repuesto_id` inexistentes o dados de baja en `POST /ordenes` → 409.
**Origen**: C-10 ("con un repuesto inexistente, 409") y la regla "404 si el **recurso de la ruta** no existe".

### SU-07 — Repuestos repetidos en el alta → 422
**Origen**: RN-10, garante "DTO". **Riesgo**: bajo.

### SU-08 — Movimiento de salida con cantidad negativa
**Supuesto**: salidas por orden con `cantidad < 0`; reposición y stock inicial con `cantidad > 0`.
**Origen**: CHECK `cantidad <> 0` (admite ambos signos).

### SU-09 — Búsqueda `q` es "contiene", sin distinguir mayúsculas
**Origen**: C-16 (`q=freno` encuentra «Pastillas de freno delanteras»). Implementación probable: `ILIKE` con parámetro ligado.

### SU-10 — Conteo de RN-08 "desde el último éxito"
**Supuesto**: se cuentan fallos de (correo, IP) en los últimos 60 s posteriores al último login correcto de ese par. `Retry-After` = segundos hasta que el fallo más viejo de la ventana salga de ella.

### SU-11 — `/mis-*` para usuarios sin ficha de cliente
**Supuesto**: responden 200 con lista vacía.

### SU-12 — Nombres de variables de entorno no fijados
Resuelto por DD-30.

### SU-13 — Alta de personal con `debe_cambiar_password = true`
**Origen**: "con contraseña provisoria" (`POST /usuarios`) + usuario `nuevo@example.com` del seed. Formalizado en DD-18.

### SU-14 — `POST /repuestos` con `stock_inicial = 0` no genera movimiento
Confirmado por DD-23.
