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
- Las fixtures de integración preparan el esquema con Alembic hasta `head`, incluidos los disparadores; no usan `create_all` (DD-43).
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

### DD-38 — El seed sincroniza las secuencias después de insertar ids explícitos (EJ-3)
**Decisión**: al final de `_cargar`, `seed.py` hace `setval` de las secuencias de `usuario`, `cliente`, `vehiculo`, `repuesto` y `orden_trabajo` hasta `max(id)` de cada tabla (en la misma transacción del seed).
**Contexto**: `TRUNCATE ... RESTART IDENTITY` (DD-36) deja cada secuencia en 1 con `is_called = false` y los INSERT del seed llevan ids explícitos, que no la avanzan. Lo descubrió el primer bloque de `test/clientes_vehiculos.http`: el primer `POST /clientes` intentaba `id = 1`, chocaba con la clave primaria sembrada y la traducción de `IntegrityError` devolvía un 409 engañoso («Ya existe un cliente con ese documento.») en lugar de 201.
**Justificación**: sin este paso, después de correr `seed.py` **ninguna** alta de la API funcionaba (rompía C-02, C-10 y C-19); es idempotente porque corre después de cada `TRUNCATE`.
**Trade-offs aceptados**: la lista de tablas es fija en el código; si un día otra tabla recibe ids explícitos en el seed hay que agregarla (el comentario del paso 11 lo advierte). Las tablas con ids implícitos no la necesitan: sus propios INSERT ya dejan la secuencia en su lugar.

### DD-39 — Las excepciones de dominio las traduce la aplicación, no cada router (EJ-3)
**Decisión**: `app/core/errores.py` define `ErrorDeDominio` con `NoEncontrado` (→ 404) y `EnConflicto` (→ 409); los servicios las lanzan sin conocer FastAPI y `main.py` llama `registrar_traductores(app)` una sola vez.
**Contexto**: D8 pide separar el dominio del HTTP; RN-18/S-9 exigen mensaje propio en español y que ninguna entrada inválida termine en 500.
**Justificación**: un solo punto de traducción para los 13 endpoints (los routers no repiten `try/except`) y los servicios siguen siendo testables sin HTTP. Los mensajes salen de `str(error)`: nunca texto de la base.

### DD-40 — Los query params de un listado van como campos del modelo `Query` (EJ-3)
**Decisión**: cada listado subclasea `ParametrosPagina` (p. ej. `ParametrosRepuestos`, que agrega `q`) en vez de declarar el filtro como parámetro suelto del handler.
**Contexto**: con FastAPI 0.162, si un handler declara `params: Annotated[Modelo, Query()]`, **todos** los query de la petición se validan contra ese modelo; con `extra="forbid"` un `q` declarado aparte cae como «extra» y responde 422 «Extra inputs are not permitted» en lugar de filtrar.
**Justificación**: conserva `extra="forbid"` en los contratos de entrada también en query (S-4) y evita el 422 falso. Ojo al repetirlo en EJ-6: `GET /ordenes` con filtros usa el mismo patrón.

### DD-41 — Límites numéricos coherentes con PostgreSQL (auditoría EJ-1..3)
**Decisión**: precios positivos finitos, representables exactamente en `NUMERIC(10,2)` (0.01..99999999.99), sin redondeo silencioso; ceros finales equivalentes admitidos. Stock inicial 0..2147483647 y reposición 1..2147483647.
**Justificación**: RN-18 exige rechazar entradas incompatibles con 422 antes de persistir. Si una cantidad válida sumada al stock existente supera el límite, corresponde 409 por conflicto con lo guardado, sin modificar stock ni movimientos (RT-PG-04).

### DD-42 — Validación HTTP humana sin eco de entrada (auditoría EJ-1..3)
**Decisión**: `RequestValidationError` se traduce centralmente a `{"detail": [{"msg": "mensaje humano"}]}`. Se usan etiquetas conocidas en español; lo desconocido recibe un mensaje genérico seguro. No se devuelven entrada, ubicaciones técnicas, categorías del validador ni contexto interno. OpenAPI describe el nuevo formato y el `detail` textual que conserva la paginación.
**Justificación**: DD-25/S-9. Se conservan sin cambios los 404/409 de dominio y el 422 de página inexistente. Evitar el eco también impide que futuras validaciones de autenticación devuelvan contraseñas.

### DD-43 — Fixtures de integración con las migraciones reales (auditoría EJ-1..3)
**Decisión**: las fixtures de API, modelos y repositorios crean su esquema con Alembic hasta `head`, no con `create_all`. Incluyen los tres disparadores de sólo agregado. Se ejecutan únicamente en bases de test reconstruibles y separadas de desarrollo.
**Justificación**: A-3 rige también para las pruebas; un esquema creado desde el metadata no instala la segunda migración y permite que pruebas verdes oculten diferencias con el entorno real.
**Integración**: Alembic respeta los handlers de logging del llamador; sólo configura `alembic.ini` cuando no hay handlers y no deshabilita loggers existentes. El comportamiento anterior también rompía la captura de salud en una secuencia original de migraciones; quedan cubiertos la captura del 503 y los diagnósticos CLI.

### DD-44 — El seed usa el Unit of Work existente (auditoría EJ-1..3)
**Decisión**: el proceso del seed crea/cierra la sesión y abre el UoW existente para vaciar y recargar en una única transacción. El hash permanece antes de la transacción. No hay confirmación externa mediante `conexion.begin()`.
**Justificación**: B-8/DD-19 exige que toda confirmación pase por UoW. Se mantiene la atomicidad e idempotencia ya exigidas; un fallo de recarga revierte también el vaciado.

### DD-45 — Contratos JSON complementarios de autenticación (EJ-4, D1)
**Decisión del equipo / supuesto complementario**: adoptar las formas propuestas en [D1](../openspec/changes/04-autenticacion/design.md#d1--formas-json-complementarias-propuestas), sin atribuir a la consigna las claves que no fija. Los contratos viven en `app/modules/usuarios/schemas.py`.

| Operación prevista | Entrada | Salida prevista |
|---|---|---|
| Registro 201 | `{email, password, nombre, documento, telefono}` | `{"mensaje":"Registro completado","debe_cambiar_password":false,"expira_en_segundos":1800}` |
| Login 200 | `{email, password}` | `{"mensaje":"Sesión iniciada","debe_cambiar_password":false,"expira_en_segundos":1800}` |
| Cambio 200 | `{password_actual, password_nueva}` | `{"mensaje":"Contraseña actualizada","debe_cambiar_password":false,"expira_en_segundos":1800}` |
| Logout 200 | Sin cuerpo requerido | `{"mensaje":"Sesión cerrada"}` |
| Yo 200 | Sin cuerpo | `{"usuario":{"id":1,"email":"persona@example.com","nombre":"Persona","debe_cambiar_password":false},"roles_vigentes":["CLIENTE"],"roles_token":["CLIENTE"]}` |

**Límites de entrada**: todos los campos indicados son requeridos, de texto, y los extras se rechazan (`extra="forbid"`, también `rol`). Cada campo destinado a bcrypt acepta como máximo **72 bytes UTF-8**, no caracteres: 72 ASCII / 36 `ñ` se admiten; 73 ASCII / 37 `ñ` se rechazan. No se agregan complejidad, longitud mínima de contraseña ni normalización de correo. El correo conserva sus caracteres (1..255); registro reutiliza `ClienteCrear`: nombre 1..255, documento y teléfono 1..50. El validador nunca copia la contraseña al mensaje; la traducción HTTP segura sigue DD-42.

**Salidas**: `SesionLectura` sirve a registro/login/cambio, `MensajeLectura` a logout e `IdentidadLectura` contiene `UsuarioLectura` y las dos listas de roles. Ninguna proyecta hash ni token. `1800` es sólo un ejemplo: la duración la proveerá la configuración y la bandera de login/yo reflejará al usuario. Los roles vigentes y los emitidos se mantienen separados, aunque difieran.

**Estado de implementación**: los contratos y fixtures PostgreSQL/Alembic acompañan registro/login, JWT y emisión de cookies ya implementados. Identidad, logout y cambio de contraseña ya implementan estas salidas; la verificación funcional integrada del cambio está aprobada (DD-48). El CRUD y `actor_temporal` continúan sin autorización hasta EJ-5.
**Justificación**: nombres explícitos para cambio/identidad y respuestas sin secretos, coherentes con DD-17; evita inventar otro DTO de CRUD o incluir el JWT en JSON.

### DD-46 — Ventana de intentos (EJ-4, D3)
**Decisión del equipo / detalle complementario aprobado**: aplicar [D3](../openspec/changes/04-autenticacion/design.md#d3--intentos-independientes-y-límite-de-login), que precisa RN-08/SU-10 sin atribuir sus bordes a la consigna. Una consulta obtiene cantidad y fecha mínima de fallos del par exacto `(email, ip)` en **(ahora − 60 s, ahora]**, estrictamente posteriores a su último éxito no futuro. No normaliza el correo ni elimina filas; un éxito con la misma fecha excluye el fallo de esa fecha.

**Bloqueo en login**: con cinco o más fallos, no consultar ni verificar credenciales. `Retry-After = max(1, ceil(segundos hasta que salga el fallo vigente más antiguo))`; una petición posterior reevalúa el conteo. Los resultados bloqueados se guardan como `exito=false` y cuentan igual que los otros fallos: el encabezado no garantiza acceso ni crea un plazo fijo nuevo.

**Persistencia**: el router entrega `UnitOfWorkIntentoAcceso` sin abrir mediante una dependencia que crea/cierra una sesión distinta. Sólo ese UoW confirma los intentos. Cuesta otra conexión/transacción y sus filas confirmadas sobreviven al rollback normal (DD-05/19); fallar la propia escritura/confirmación revierte y propaga el error. El evento del 429 pertenece al UoW normal; no se generaliza la excepción a eventos ni se usan tareas de fondo.

**Estado de implementación**: sobre la consulta/UoW/dependencias de OPSX4.1, login integra umbral previo a credenciales/bcrypt, Retry-After, evento bloqueado y traductores 401/429 explícitos. Las lecturas cierran su fase con UoW antes de bcrypt y conservan sólo primitivas; la dependencia sigue siendo dueña de la sesión. Las pruebas HTTP con PostgreSQL/Alembic verifican los bordes temporales, reset/aislamiento, persistencia y ausencia de cookie cuando falla un commit obligatorio. C-02/C-04/C-05 se ejecutaron por TCP tras Alembic/seed (12 bloques). La verificación independiente de esta unidad confirmó 531 pruebas aprobadas sin omisiones y un diferencial de 75 solicitudes por versión, 15 operaciones y 12 rutas existentes sin diferencias no solicitadas contra `b3a903a`; se registraron 18 advertencias conocidas de la clave JWT de fixtures. Esta evidencia cubre 4.2/4.3, no las tareas posteriores de identidad/logout/cambio ni el cierre global de EJ-4. No hay garantía global frente a logins concurrentes, locks, Redis, migraciones ni cambios de configuración.

### DD-47 — Identidad y cierre de cookie (EJ-4, D4/D5)
**Decisión complementaria aprobada**: emisión y eliminación comparten Path=/, sin Domain, HttpOnly, SameSite=Lax y Secure configurable. Logout público devuelve D1 y elimina con Max-Age=0/Expires pasado, sin escrituras ni revocación central de JWT copiados. Identidad usa el mensaje seguro existente «La sesión no es válida. Volvé a iniciar sesión.» para todos sus 401.

**Implementación**: `get_usuario_actual` vive en `app/core/dependencies.py`, lee sólo `request.cookies` y construye el UoW sin abrir; el servicio lo abre, el repositorio precarga roles y la dependencia de sesión conserva su cierre. Compara el `iat` original con `password_cambiada_en.timestamp()` (UTC, sin truncar); igualdad válida. Roles vigentes excluyen revocados/vencidos; los emitidos son informativos. No añade políticas JWT ni normalización. El nuevo lookup por id trata valores fuera de INTEGER como usuario inexistente: la PK migrada no puede contenerlos y enlazarlos a asyncpg producía 500.

**Evidencia acotada**: 33 pruebas HTTP ASGI/PostgreSQL/Alembic focalizadas aprobadas, sin omisiones; incluyen ±1 microsegundo, identidad mínima, rechazo sin eco/escrituras, roles actuales, cookies Secure on/off y JWT copiado tras logout. La suite completa y la ejecución host solicitada por el verificador independiente aprobaron 563 pruebas sin omisiones, con 76 advertencias conocidas de la clave JWT de fixture; los 22 bloques TCP de `test/auth.http` pasaron tras Alembic/seed aislados. El diferencial contra `9cb3f16` confirmó 15 solicitudes por versión a los tres consumidores del actor temporal: 12 escrituras atribuidas al admin del seed y tres errores históricos por admin ausente sin escrituras. Exit/stdout/stderr coinciden bajo normalización validada de fechas y formato de errores sin frames de traceback. El dictamen independiente es PASS para 5.1–5.3, no cierre global de EJ-4 ni aprobación nativa. Esta unidad no protegió CRUD ni `actor_temporal`, ni implementó cambio de contraseña/RBAC.

### DD-48 — Cambio de contraseña y mensaje complementario (EJ-4, D1/D2/D4)
**Decisión complementaria / D-4**: SU-05 fija 401 para contraseña actual incorrecta, pero no su texto. Se usa «La contraseña actual no es correcta.», sin eco ni nueva política. Las sesiones rechazadas conservan el mensaje de DD-47. No agrega complejidad, normalización, locks ni bloqueo global 403 de EJ-5.

**Implementación**: lectura breve con UoW cerrado antes de bcrypt real; sólo el hash primitivo atraviesa esa fase. El mismo UoW de usuarios confirma hash nuevo, `password_cambiada_en` UTC fraccional, bandera falsa y evento «Cambio de contraseña» con el correo del usuario. El router entrega la cookie sólo después del commit, usando esa fecha persistida como `iat` (igualdad válida); los roles informativos se recargan para el cambio, no se copian del JWT anterior. Reutiliza repositorios y helpers existentes, sin migración.

**Evidencia acotada**: RED HTTP 404 del implementador; verificación final focalizada de cambio + registro: 45 aprobadas, 0 omitidas, incluidas las aserciones adicionales de evento flusheado/emisor no llamado. El host ejecutó una sola secuencia preparada por el verificador independiente: suite completa **595 aprobadas, 0 omitidas, 132 advertencias conocidas de fixture JWT** (122.34 s), **28 bloques TCP** tras migración/seed aislados (12 intentos, cuatro eventos) y diferencial de **48 solicitudes por versión** contra `c36b50e` para registro/login con Secure activado/desactivado. Exit/stdout/stderr coinciden normalizando únicamente sales bcrypt verificadas, fechas conscientes de zona y JWT/tiempos validados; no se comparan JWT crudos como si fueran deterministas. Dictamen independiente PASS para 6.1–6.3 y evidencia funcional/seguridad integrada, sin nuevos hallazgos graves. La revisión nativa se registra por separado en ODD; esta evidencia no autoriza EJ-5 ni publicación.

### DD-49 — Contratos de autorización y administración (EJ-5, D1)
**Decisión del equipo / supuesto complementario (D-4)**: adoptar las formas propuestas en [D1](../openspec/changes/05-autorizacion/design.md#d1--formas-de-respuesta-propuestas), sin atribuir a la consigna las claves que no fija. Los contratos viven en `app/modules/usuarios/schemas.py`.

| Operación | Entrada | Salida |
|---|---|---|
| `POST /usuarios` 201 | `{email, nombre, password_provisoria, rol}` — `rol` ∈ ADMIN/RECEPCION/MECANICO (`CLIENTE` → 422) | `UsuarioLectura` de EJ-4 (`{id, email, nombre, debe_cambiar_password}`), sin hash ni contraseña |
| `GET /usuarios/{id}/roles` 200 | Sin cuerpo | `{"items":[{rol, desde, vence_en, otorgada_por}]}` — sólo vigentes, sin paginación |
| `POST /usuarios/{id}/roles` 201 | `{rol, vence_en?}` — `rol` ∈ los cuatro del CHECK; `vence_en` con zona y futuro si viene | La asignación creada: `{rol, desde, vence_en, otorgada_por}` |
| `DELETE /usuarios/{id}/roles/{rol}` 200 | Sin cuerpo | `{"mensaje":"Rol MECANICO revocado"}` (Flujo 5 fija 200, no 204) |
| `GET /eventos` 200 | Query de página | Envoltorio estándar `{items, total, page, size, pages}` con `items: [{id, cuando, actor, accion}]` |
| `GET /mis-vehiculos`, `GET /mis-ordenes` 200 | Query de página | Envoltorio estándar; página fuera de rango → 422 |

Todos con `extra="forbid"`; ningún 401/403 expone texto interno (DD-25). `POST /usuarios/{id}/roles` acepta `CLIENTE`: la restricción `CLIENTE` → 422 pertenece sólo al cuerpo de `POST /usuarios` (DD-18).
**Estado de implementación**: contratos y sus validaciones (`vence_en` con zona y futuro) implementados y probados en el Grupo 1 de EJ-5; los endpoints se implementan en los grupos 4–6.

### DD-50 — Controles de autorización y roles por petición (EJ-5, D2/D3)
**Decisión del equipo / detalle complementario (D-4)**: los tres controles de [D2](../openspec/changes/05-autorizacion/design.md#d2--dependencias-de-autorización-y-dónde-se-aplica-cada-control) y la consulta de roles de [D3](../openspec/changes/05-autorizacion/design.md#d3--roles-vigentes-por-petición-sin-caché):

1. **Identidad** — `get_usuario_actual` (`app/core/dependencies.py`): cookie única; cualquier fallo → 401 con el mensaje seguro de DD-47.
2. **Cambio obligatorio** — dependencia del grupo protegido montada una sola vez en `main.py` (DD-10): `debe_cambiar_password = true` → 403; `/auth/*` y `/health/*` quedan fuera del grupo.
3. **Rol** — `requiere_rol(*roles)`: dependencia de fábrica aplicada **por ruta** según la matriz; consulta los roles vigentes (`revocada_en IS NULL` y `vence_en` nulo o futuro) en **cada petición** con `UsuarioRepository.get_roles_vigentes`, sin caché y sin leer los roles del JWT (RN-04). Devuelve la identidad; sin el rol → 403.

La identidad se resuelve primero: sin sesión siempre hay 401, nunca un 403 por rol. `/mis-*` sólo reciben sesión (RN-17). El coste aceptado de una consulta extra por petición es lo que hace que revocar surta efecto de inmediato (C-07).
**Estado de implementación**: `requiere_rol` y `get_roles_vigentes` implementados y probados en el Grupo 2 de EJ-5; la protección de las rutas existentes llega en el Grupo 3.

### DD-51 — Jerarquía de repositorios, Unit of Work y consultas de órdenes (EJ-6, D3/D4)
**Decisión del equipo / detalle complementario (D-4)**, de [D3 y D4](../openspec/changes/06-repositorios-uow-ordenes/design.md#d3--repositorios-del-módulo-ordenes-y-reubicación-de-consultas):

1. **Rollback en el UoW base**: `UnitOfWork.__aexit__` revierte y propaga si el cuerpo lanza **o si el propio `commit()` falla**; nunca cierra la sesión (B-3). Los `__aexit__` duplicados de `UnitOfWorkUsuario` y `UnitOfWorkIntentoAcceso` se eliminan: el comportamiento es el mismo y ahora lo heredan `clientes`, `repuestos` y `ordenes`.
2. **Una clase por entidad en `ordenes`**: `OrdenRepository`, `ItemOrdenRepository` (hereda de `BaseRepository`; los ítems sólo se agregan dentro del alta de su orden), `HistorialEstadoOrdenRepository` (sólo `add`, sin `update`/`delete`, RN-15) y `EstadoOrdenRepository` (catálogo de sólo lectura, **no** hereda de `BaseRepository`, A-5).
3. **Las consultas sobre `orden_trabajo` viven en `OrdenRepository`**: `es_dueno_del_vehiculo` (reemplaza a `_es_dueno_del_vehiculo` del servicio, sigue valiendo con el vehículo dado de baja, DD-28) y `tiene_abiertas_del_vehiculo` (reemplaza a `VehiculoRepository.tiene_ordenes_abiertas`; abierta = estado que el catálogo no marca `es_final`). `UnitOfWorkCliente` compone `ordenes` con la misma sesión para la baja de vehículos (RN-16, C-19 sin cambio de contrato) y `es_personal_o_dueno` conserva su firma (T-8).
4. **Detalle con precarga declarada**: `OrdenRepository.get_detalle_con_items_e_historial` trae vehículo→cliente, ítems→repuesto (también dado de baja, DD-21) e historial con `populate_existing`, de modo que dentro del mismo bloque refleja los ítems y las líneas recién agregadas. El orden cronológico del historial `(cuando, id)` lo aplica quien serializa, no el repositorio.
5. **Verificación de capas por AST** (`test/pytest/test_capas.py`): único `commit(` en el UoW base, ningún `service.py` construye su UoW, ningún `service.py`/`router.py` de los cuatro módulos con datos ejecuta SQL. `app/modules/health/router.py` (`SELECT 1` de la sonda de preparación) queda fuera porque no es un módulo con datos.
**Estado de implementación**: puntos 1–4 implementados y probados en los Grupos 2–3 de EJ-6; `EstadoOrdenRepository` (sólo lectura, sin herencia de `BaseRepository`) ganó `get_all_por_posicion` y `get_by_codigo` en el Grupo 4.

### DD-52 — Contratos de órdenes y del catálogo (EJ-6, D1)
**Decisión**:
1. `POST /ordenes` acepta sólo `vehiculo_id`, `falla` (1..500) e `items` (≥ 1; cada uno `repuesto_id` y `cantidad` 1..2 147 483 647); `extra="forbid"` en la raíz y en los ítems, y un `repuesto_id` repetido se rechaza con un validador propio (422, sin eco de la entrada). Los ids del cuerpo se acotan a `1..2 147 483 647` para que ningún valor desmedido llegue a la base como un error interno.
2. `OrdenDetalle` repite la forma del ejemplo de la consigna: `{id, estado, patente, total, creada_en, mecanico_id, falla, cliente, items[{repuesto_id, codigo, descripcion, cantidad, precio_unitario, subtotal}], historial[{desde_estado, hasta_estado, usuario_id, cuando}]}`, con `cliente` como **nombre** (texto), dinero con dos decimales, ítems por id (orden del alta) e historial ordenado por `(cuando, id)`.
3. `GET /ordenes` devuelve `Pagina[OrdenResumenLectura]` (el mismo resumen de `/mis-ordenes`) con `ParametrosOrdenes(ParametrosPagina)` y `estado: EstadoOrdenCodigo | None` (StrEnum con los cuatro códigos del seed); un estado no declarado es 422 «Elegí un valor válido para el estado.» sin repetir lo enviado. `total` cuenta con el mismo filtro.
4. `GET /estados-orden` devuelve la lista sin paginar (4 filas fijas) de `{codigo, descripcion, posicion, es_final}`; sólo declara `GET` (cualquier escritura es 405 y OpenAPI sólo publica `GET`).
5. Un `orden_id` de la ruta fuera de `1..2 147 483 647` no puede existir: `GET /ordenes/{id}` responde **404** «Orden no encontrada.» (no 422 ni 500); un id no entero sigue siendo 422.
6. El traductor 422 suma etiquetas (`falla`, `items`, `estado`, `orden_id`) y mensajes para `enum`, `too_short` de la lista de ítems y el validador de repetidos; los errores de ítems anidados caen en el mensaje genérico seguro.
**Origen**: design D1 de `06-repositorios-uow-ordenes`; ejemplo de la consigna en `07_flujos_principales.md` (Flujo 6). **Riesgo**: bajo.

### DD-53 — Guarda de stock en el punto único y tope del total de la orden (EJ-6, D5/D6)
**Decisión**: `RepuestoRepository.registrar_movimiento` valida `stock + cantidad >= 0` **antes** de agregar el movimiento o tocar el stock y, si no alcanza, lanza `StockInsuficiente(EnConflicto)` → 409 con el mensaje «No hay stock suficiente de {descripción} ({código}): hay {n} y se necesitan {m}.». La guarda vive ahí (y no sólo en el servicio de órdenes) para que ningún llamador futuro deje stock negativo; el `CHECK stock >= 0` de la base queda como última defensa. Además, el alta de una orden rechaza con 409 «El total de la orden supera el máximo permitido: revisá las cantidades.» un total mayor a 9 999 999 999.99 (tope de `NUMERIC(12,2)`), nunca un 500. Extiende DD-41 (tope de existencias).
**Origen**: RN-13, RN-14, S-5, S-9. **Riesgo**: bajo.

### DD-54 — Orden de controles de las transiciones y predicado `puede_cancelar` (EJ-6, D2/D7)
**Decisión**, de [D2 y D7](../openspec/changes/06-repositorios-uow-ordenes/design.md#d2--dónde-se-decide-cada-permiso-y-en-qué-orden):

1. **Orden de los controles** (identidad → cambio de contraseña pendiente → rol de ruta → servicio): `iniciar` = `requiere_rol("MECANICO")` → 404 → estado `PENDIENTE` (409); `cancelar` = **sin** `requiere_rol` → 404 → `puede_cancelar` (403) → estado `PENDIENTE` (409); `terminar` = `requiere_rol("MECANICO","ADMIN")` → 404 → asignado o ADMIN vigente (403) → estado `EN_REPARACION` (409) → stock (409). El permiso va antes que el estado (RN-12): un cliente sobre una orden ajena no pendiente recibe 403, no 409.
2. **`puede_cancelar` es un predicado propio**, distinto de `es_personal_o_dueno`: RECEPCION o ADMIN vigentes, o el dueño del vehículo (también con el vehículo dado de baja, DD-28). «Personal» incluye a MECANICO, que **no** cancela (RN-12, matriz): un MECANICO que no sea además RECEPCION/ADMIN/dueño recibe 403 aun siendo el asignado.
3. En `iniciar` y `terminar`, el rol de ruta precede a la existencia de la orden: un ADMIN sin rol MECANICO recibe 403 al iniciar aunque el id no exista. En `cancelar` la existencia precede al permiso (404 antes que 403), porque el permiso depende de la orden.
4. Cada transición es un solo bloque: valida el estado antes de la primera escritura (un 409 no deja nada escrito), cambia `estado`, agrega la línea de historial firmada por quien actúa y relee el detalle con la precarga declarada; responde **200 con el detalle** actualizado. `iniciar` asigna `mecanico_id`; `cancelar` y `terminar` no lo tocan.
5. Mensajes 409 humanos que nombran el estado actual: «La orden ya está terminada: no se puede cancelar.» (también «ya está en reparación», «ya está cancelada», «todavía está pendiente»). Mensaje 403 de cancelar: «No tenés permiso para cancelar esta orden.».
**Origen**: nota de la consigna «la ruta de cancelar no lleva `requiere_rol`», RN-11, RN-12, DD-27, DD-28, DD-31. **Riesgo**: medio (permisos mixtos rol/dueño).

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
