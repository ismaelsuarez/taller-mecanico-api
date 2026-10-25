# Funcionalidades

Organizadas por **épica** (≈ ejercicio de la consigna) y luego por **historia de usuario**. Los puntos de cada ejercicio están entre paréntesis.

---

## Épica 1: Proyecto, configuración y ciclo de vida (Ej. 1 · 8 pts)

### US-001 — Configuración desde el entorno
**Como** desarrollador **quiero** que la configuración se lea con `Settings` (pydantic-settings) desde el entorno o `.env` **para** no tener secretos en el código.

**Criterios de aceptación**:
- [ ] La URL de la base se arma con un `@computed_field` desde `POSTGRES_*`, con driver asincrónico.
- [ ] La clave de firma y la contraseña de la base no tienen valor por defecto: si faltan, la app no arranca.
- [ ] El tamaño del pool, el costo de bcrypt, la duración del token y `Secure` de la cookie se declaran en la configuración.
- [ ] Existe `env.example` con todas las variables y ningún secreto; `.env` no se versiona.

**Reglas relacionadas**: RT-SE-01, RT-SE-08

### US-002 — Ciclo de vida de recursos
**Como** desarrollador **quiero** crear el motor y la fábrica de sesiones en el lifespan **para** que existan cuando ya hay bucle de eventos.

**Criterios de aceptación**:
- [ ] Motor asincrónico y fábrica de sesiones creados en el `lifespan` y guardados en `app.state` (no al importar).
- [ ] `get_session` toma la fábrica de `app.state`, entrega una sesión por petición con `expire_on_commit=False` y la cierra al terminar.
- [ ] El lifespan calcula una vez el hash ficticio del login.
- [ ] Al apagar, `engine.dispose()`.

### US-003 — Salud
**Como** operador **quiero** sondas de vida y de preparación **para** distinguir proceso vivo de proceso listo.

**Criterios de aceptación**:
- [ ] `GET /health/live` responde 200 y no toca la base.
- [ ] `GET /health/ready` ejecuta `SELECT 1`; 200 si responde, **503** si la base no contesta.

---

## Épica 2: Modelos, relaciones y migraciones (Ej. 2 · 14 pts)

### US-004 — Modelos con restricciones
**Como** desarrollador **quiero** los modelos del dominio con todas sus restricciones **para** que la base garantice la integridad.

**Criterios de aceptación**:
- [ ] Todas las tablas/columnas con los nombres obligatorios ([04](04_modelo_de_datos.md)).
- [ ] Tres índices únicos parciales con `postgresql_where` (`asignacion_rol`, `vehiculo.patente`, `repuesto.codigo`).
- [ ] El estado de la orden y los del historial son FKs a `estado_orden`, no un CHECK.
- [ ] Navegación en los dos extremos de cada relación que se lea; `Usuario.cliente` devuelve un objeto.
- [ ] Índice en cada FK; fechas `timestamptz`; dinero `NUMERIC`/`Decimal`.

**Reglas relacionadas**: RN-01, RN-03, RN-19

### US-005 — Migraciones con Alembic
**Como** desarrollador **quiero** crear el esquema sólo con Alembic **para** tenerlo versionado.

**Criterios de aceptación**:
- [ ] Plantilla asincrónica; no se usa `create_all`.
- [ ] Migración 1 autogenerada con todas las tablas; migración 2 escrita a mano con el disparador de sólo agregado sobre las tres tablas.
- [ ] Cada migración lleva un comentario que dice que se leyó antes de aplicarla.
- [ ] `upgrade head` → `downgrade base` → `upgrade head` funciona sobre base vacía.
- [ ] El catálogo queda vacío tras las migraciones.

**Reglas relacionadas**: RN-15

### US-006 — Datos iniciales
**Como** evaluador **quiero** correr `python seed.py` **para** dejar la base en el estado inicial conocido antes de cada archivo de prueba.

**Criterios de aceptación**:
- [ ] Vacía las tablas y carga el catálogo primero.
- [ ] Carga usuarios, clientes, vehículos, repuestos (con movimiento «Stock inicial»), órdenes 1 y 2, historial de precios y el evento `SISTEMA` ([04](04_modelo_de_datos.md#seed-data-inicial-seedpy)).

---

## Épica 3: Contratos y CRUD (Ej. 3 · 10 pts)

### US-007 — Contratos estrictos
**Como** desarrollador **quiero** contratos separados con `extra="forbid"` **para** que nadie se registre con un rol ni edite el stock por PATCH.

**Criterios de aceptación**:
- [ ] Ninguna respuesta incluye `password_hash`.
- [ ] PATCH con `exclude_unset`.
- [ ] Códigos 201/204/404/409/422 según la convención.
- [ ] Ninguna entrada inválida termina en 500.

**Reglas relacionadas**: RT-PG-01..04, RN-18

### US-008 — Listados paginados
**Como** usuario del personal **quiero** listados paginados **para** navegar resultados grandes.

**Criterios de aceptación**:
- [ ] Envoltorio `{items, total, page, size, pages}`; `page ≥ 1`; `size` 1..100 (def. 20).
- [ ] Página fuera de rango → 422 («La página N no existe: hay M»); cero resultados → una página vacía.
- [ ] `total` con los mismos filtros.

**Reglas relacionadas**: RT-PG-05

### US-009 — Gestión de clientes y vehículos (RECEPCION, ADMIN)
- [ ] `POST /clientes` (201/409/422), `GET /clientes/{id}` con sus vehículos (200/404).
- [ ] `POST /clientes/{id}/vehiculos` (201/404/409/422); patente duplicada entre vigentes → 409.
- [ ] `DELETE /vehiculos/{id}`: borrado lógico, 204; con órdenes abiertas → 409.

**Reglas relacionadas**: RN-01, RN-16

### US-010 — Catálogo de repuestos (ADMIN; lectura también RECEPCION, MECANICO)
- [ ] `GET /repuestos?q=&page=&size=` busca por descripción con parámetros ligados; excluye dados de baja.
- [ ] `GET /repuestos/{id}`.
- [ ] `POST /repuestos` con `stock_inicial ≥ 0` → movimiento «Stock inicial» si es > 0 (DD-23).
- [ ] `PATCH /repuestos/{id}` sólo descripción y precio; cambio de precio → línea en historial en la misma transacción; precio igual → sin línea.
- [ ] `DELETE /repuestos/{id}` borrado lógico (204 aunque esté en órdenes abiertas; ya dado de baja → 404; DD-21, DD-22).
- [ ] `POST /repuestos/{id}/reponer` `{cantidad > 0, motivo? ≤120}` (200/404/422) → movimiento positivo vía punto único de escritura de stock (DD-29).
- [ ] `GET /repuestos/{id}/movimientos`, `GET /repuestos/{id}/precios`.

**Reglas relacionadas**: RN-01, RN-14, RN-16, RN-20

---

## Épica 4: Autenticación (Ej. 4 · 16 pts)

### US-011 — Auto-registro de clientes
**Como** cliente **quiero** registrarme solo **para** consultar mis vehículos y órdenes.

**Criterios de aceptación**:
- [ ] Crea usuario + rol `CLIENTE` + ficha de cliente en un solo UoW (201).
- [ ] Correo o documento repetido → 409 con mensaje propio y sin filas sueltas.
- [ ] No se apropia de una ficha existente.
- [ ] Contraseña ≤ 72 bytes (422 si se pasa); hash calculado antes de abrir la transacción.
- [ ] Cuerpo `{email, password, nombre, documento, telefono}`; mandar `rol` → 422.
- [ ] 201 con `Set-Cookie access_token` emitida después del commit; sin cookie si da 409.

**Reglas relacionadas**: RN-01, RN-02, RT-SE-03, RT-SE-04, RT-SE-13 (DD-17)

### US-012 — Login con cookie
**Como** usuario **quiero** iniciar sesión **para** usar la API.

**Criterios de aceptación**:
- [ ] Primero el límite de intentos (5 fallos / 60 s por correo+IP → 429 + `Retry-After`, sin hash).
- [ ] Verificación contra el hash real o el ficticio; mismo cuerpo y tiempo exista o no el correo (401). Cuenta inactiva con contraseña correcta → 401 «Tu cuenta está desactivada…» (DD-24).
- [ ] JWT con `sub`, `iat`, `exp`, roles vigentes, en cookie `access_token` (HttpOnly, SameSite=Lax, Max-Age, Secure configurable).
- [ ] Cuerpo: `{ "mensaje": "Sesión iniciada", "debe_cambiar_password": false, "expira_en_segundos": 1800 }` (sin token).
- [ ] Cada intento se anota en `intento_acceso` en su propia sesión/transacción.

**Reglas relacionadas**: RN-08, RN-09, RT-SE-05..07, RT-SE-09

### US-013 — Logout, quién soy y cambio de contraseña
- [ ] `POST /auth/logout` borra la cookie (200).
- [ ] `GET /auth/yo` devuelve el usuario, sus roles vigentes y los que dice el token.
- [ ] `POST /auth/cambiar-password` (contraseña actual + nueva, ≤ 72 bytes): anota `password_cambiada_en`, limpia `debe_cambiar_password`, emite una cookie nueva válida; las anteriores dan 401 aunque sean del mismo segundo.

**Reglas relacionadas**: RN-06, RN-07

---

## Épica 5: Autorización (Ej. 5 · 14 pts)

### US-014 — Usuario actual y roles vigentes
- [ ] `get_usuario_actual` → 401 sin cookie, token inválido/vencido, usuario inexistente/inactivo o `iat` anterior a `password_cambiada_en`.
- [ ] `requiere_rol` → 403; consulta los roles vigentes en la base en cada petición.

**Reglas relacionadas**: RN-04, RN-07

### US-015 — Administración de personal y roles (ADMIN)
- [ ] `POST /usuarios`: alta de personal `{email, nombre, password_provisoria, rol}` (rol de personal; `CLIENTE` → 422), `debe_cambiar_password = true`, usuario + rol + evento en un solo UoW (DD-18).
- [ ] `GET /usuarios/{id}/roles`, `POST /usuarios/{id}/roles` (vencimiento opcional, con zona y futuro, si no 422), `DELETE /usuarios/{id}/roles/{rol}` (revoca sin borrar).
- [ ] Reasignar un rol vencido cierra la fila anterior y abre una nueva; rol abierto duplicado → 409.
- [ ] Autoprotección: el admin no se revoca su ADMIN; nunca quedan cero admins vigentes (409).
- [ ] `GET /eventos` paginado; acciones registradas según DD-26.

**Reglas relacionadas**: RN-03, RN-05, RT-SE-10, RT-SE-11

### US-016 — Cambio obligatorio de contraseña
- [ ] Dos grupos de rutas en `main.py`; el protegido lleva el control montado una sola vez.
- [ ] Con cambio pendiente: 403 en todo lo protegido; `/auth/*` y `/health/*` funcionan.

**Reglas relacionadas**: RN-06

### US-017 — Lo propio
**Como** cliente **quiero** ver sólo mis vehículos y órdenes.
- [ ] `GET /mis-vehiculos`, `GET /mis-ordenes` (paginado).
- [ ] `GET /ordenes/{id}` de una orden ajena → 403.

**Reglas relacionadas**: RN-17

---

## Épica 6: Repositorios y Unit of Work (Ej. 6 · 20 pts)

### US-018 — Jerarquía de repositorios
- [ ] `BaseRepository[T]` recibe sesión y clase del modelo; ofrece al menos `get_by_id`, `get_all`, `count`, `add`, `update`, `delete`.
- [ ] `SoftDeleteRepository[T]` hereda, filtra los dados de baja y agrega `get_by_id_including_deleted` y `soft_delete`.
- [ ] `add`/`update` hacen `flush()`, nunca `commit()`.
- [ ] Un repositorio por entidad, métodos nombrados por lo que traen, precarga declarada en el método.
- [ ] Repositorio del catálogo de sólo lectura que no hereda de `BaseRepository`.

### US-019 — Unit of Work
- [ ] `UnitOfWork` base: gestor de contexto asincrónico; commit al salir, rollback con excepción, no cierra la sesión.
- [ ] Un UoW por módulo que compone sus repositorios con la misma sesión.
- [ ] El router lo construye (dependencia) y lo pasa sin abrir; el servicio lo abre con `async with`.
- [ ] RN-02, RN-13 y RN-20, cada una en un solo bloque.
- [ ] Punto único de escritura de stock usado por reposición y terminación.

**Reglas relacionadas**: RT-TX-01..04, RN-14

### US-020 — Órdenes de trabajo
- [ ] `POST /ordenes` (RECEPCION, ADMIN): nace `PENDIENTE`, ≥1 ítem, sin repetidos, precio copiado, total calculado, primera línea de historial; repuesto inexistente/dado de baja o vehículo dado de baja → 409 y no queda la orden; catálogo vacío → 409.
- [ ] `GET /ordenes` filtrable por `estado` (enum) y paginado; `GET /ordenes/{id}` con vehículo, cliente, ítems, repuesto de cada ítem e historial.
- [ ] `POST /ordenes/{id}/iniciar` (MECANICO): `PENDIENTE → EN_REPARACION`, queda asignado.
- [ ] `POST /ordenes/{id}/terminar` (mecánico asignado o ADMIN): descuenta stock, un movimiento por ítem, línea de historial, todo o nada (409 si falta stock).
- [ ] `POST /ordenes/{id}/cancelar` (RECEPCION, ADMIN o dueño): 403 antes que 409; sólo desde `PENDIENTE`.
- [ ] `GET /estados-orden` por posición.

**Reglas relacionadas**: RN-10..13, RN-16, RN-19

---

## Épica 7: Integridad (Ej. 7 · 10 pts)

### US-021 — Sólo agregado
- [ ] El disparador de la migración 2 rechaza cualquier UPDATE o DELETE sobre las tres tablas, venga de donde venga (C-14, `test/solo_agregado.sql`).

### US-022 — Intento de acceso en su propia transacción
- [ ] Cada login (correcto o fallido) se anota en `intento_acceso` con un UoW dedicado (sesión propia) que se confirma siempre, con comentario que lo declara y su costo (DD-19).

**Reglas relacionadas**: RN-15, RT-SE-09

---

## Épica 8: Lecturas sin N+1 y asincronía (Ej. 8 · 8 pts)

### US-023 — Carga anticipada
- [ ] Toda respuesta con datos de relaciones usa carga anticipada declarada en el repositorio; nada depende de la carga perezosa.
- [ ] El detalle de una orden usa un número fijo de consultas (mismo número con 2 y con 4 ítems).

### US-024 — Aviso en segundo plano
- [ ] Al terminar una orden se agenda con `BackgroundTasks` el aviso: `await asyncio.sleep(0.5)` + mensaje en el registro; corre después de la respuesta y sólo si se confirmó.
- [ ] Todos los handlers `async def`, sin llamadas bloqueantes.

**Reglas relacionadas**: RT-TX-05..07
