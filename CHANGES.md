# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **Taller Mecánico** (API REST asincrónica FastAPI + PostgreSQL, TP Programación III · UTN, Cap. 1 a 6).
> Hay **8 changes, uno por ejercicio de la consigna**, en el orden exacto de la consigna. Cada change lo implementa **un solo integrante del equipo, en su turno**; al terminarlo hace `commit + push` y recién entonces continúa el siguiente compañero.
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

---

## Cómo usar este documento

1. Identificá el siguiente change con `Estado: [ ]` cuyo anterior esté en `[x]` (siempre es el primero pendiente: el orden es estricto).
2. Antes de empezar, `git pull` (el hook importa la memoria de engram del equipo; la primera vez después de clonar corré `bash scripts/setup.sh`) y leé los archivos de "Leer antes" de ese change en `knowledge-base/`, más las preguntas abiertas (`10_preguntas_abiertas.md`) que el change lista como bloqueantes.
3. Ejecutá `/opsx:propose <nombre-del-change>` (por ejemplo `/opsx:propose 01-proyecto-config-lifespan`) y luego `/opsx:apply`.
4. Verificá el "Definition of Done / handoff" del change (ver abajo), ejecutá `/opsx:archive <nombre-del-change>`, hacé **commit + push** y avisá al equipo.
5. Marcá el checkbox del change (`[x]`) en este archivo como parte del mismo commit. El siguiente compañero arranca recién después de ese push.

### Regla de relevo (handoff) — aplica a los 8 changes

El trabajo en equipo es **estrictamente secuencial**. No hay ramas paralelas, no hay changes simultáneos, no hay plan multi-agente.

- El change N **depende del change N-1** (código, migraciones y `seed.py` ya empujados al repositorio compartido).
- Nadie empieza el change N+1 hasta que el change N esté **archivado, commiteado y empujado**.
- Un change "terminado" significa que se cumple su **Definition of Done / handoff**, que siempre incluye:
  1. Los casos de prueba (`test/*.http`, y `test/solo_agregado.sql` cuando corresponda) que ese ejercicio hace demostrables, **con la respuesta esperada en un comentario** y corridos tras `python seed.py`.
  2. `alembic upgrade head` → `downgrade base` → `upgrade head` funcionando sobre base vacía (desde el change 02; el cambio de esquema en un change posterior lo exige de nuevo).
  3. `python seed.py` sigue dejando el estado inicial conocido.
  4. `README.md` y `env.example` actualizados con lo que el change agregó (pasos de puesta en marcha, variables nuevas).
  5. Sin credenciales en el repositorio (`.env` en `.gitignore`).
  6. `/opsx:archive` ejecutado, `commit` (Conventional Commits, p. ej. `feat(02-modelos-migraciones-seed): ...`), `bash scripts/sync-memoria.sh` (en Windows: `scripts\sync-memoria.bat`; exporta y commitea la memoria de engram) y `push`.
  7. Checkbox de este archivo marcado y, si quedaron decisiones o supuestos nuevos, anotados en `knowledge-base/09_decisiones_y_supuestos.md` / `10_preguntas_abiertas.md` para el siguiente compañero.

> El repositorio compartido ya existe desde la fundación: **https://github.com/ismaelsuarez/taller-mecanico-api** (público), con `.gitignore`, hooks de engram (`.githooks/`), `scripts/setup.sh`, `scripts/sync-memoria.sh` y skills del proyecto (`skills-lock.json` + `.agents/skills/`).

### Decisiones transversales (cómo se resuelven las dependencias entre ejercicios sin reordenarlos)

Los ejercicios se implementan en el orden de la consigna, pero algunos necesitan piezas que otro ejercicio formaliza. Se resuelve así:

| # | Realidad cruzada | Decisión |
|---|---|---|
| T-1 | **Esqueleto de capas**: la estructura de directorios de `08_arquitectura_propuesta.md` es obligatoria desde el inicio. | El Ej. 1 crea todas las carpetas/módulos (`app/core`, `app/modules/{health,usuarios,clientes,repuestos,ordenes}`) aunque estén vacíos. Nadie reorganiza carpetas después. |
| T-2 | **Repositorios y UoW (Ej. 6)** son necesarios para el CRUD (Ej. 3) y el registro (Ej. 4). | El Ej. 3 introduce una versión **mínima pero ya conforme** de `app/core/repository.py` (`BaseRepository[T]`, `SoftDeleteRepository[T]` con `get_by_id`, `get_all`, `count`, `add`, `update`, `delete`, `soft_delete`; `flush()` y nunca `commit()`) y de `app/core/unit_of_work.py` (commit al salir, rollback con excepción, no cierra la sesión), más un UoW por módulo (`clientes`, `repuestos`). El Ej. 4 agrega el UoW de `usuarios`. **Reglas RT-TX-01..03 se cumplen desde el primer día** para no reescribir firmas. El Ej. 6 **completa y audita**: precarga declarada por método, repositorio de sólo lectura del catálogo (sin heredar de `BaseRepository`), módulo `ordenes`, punto único de escritura de stock formalizado y RN-02 / RN-13 / RN-20 cada una en un solo bloque. |
| T-3 | **Punto único de escritura de stock (RN-14)**: el Ej. 3 ya necesita `stock_inicial` y `reponer`, pero la consigna lo formaliza en el Ej. 6. | El Ej. 3 implementa una única función de escritura de stock en el módulo `repuestos` (movimiento + actualización de `stock`) y la usan alta y reposición. El Ej. 6 la reutiliza para terminar órdenes y verifica que sea el único camino. |
| T-4 | **Actor de auditoría antes de la autenticación**: `movimiento_stock` e `historial_precio_repuesto` exigen `usuario_id` no nulo (SU-01), pero el login llega en el Ej. 4. | En el Ej. 3 las rutas quedan **sin protección** y el actor sale de una dependencia **temporal** (`actor_temporal`, devuelve el admin sembrado). El Ej. 5 la reemplaza por `get_usuario_actual` y agrega `requiere_rol` a esas rutas. Debe quedar comentada como temporal. |
| T-5 | **bcrypt en el seed (Ej. 2)** y `core/security.py` (Ej. 4). | El `seed.py` del Ej. 2 hashea con bcrypt directamente usando `BCRYPT_ROUNDS` de `Settings`. El Ej. 4 crea `security.py` (to_thread + semáforo) y puede hacer que el seed lo reutilice. |
| T-6 | **Disparador de sólo agregado**: lo crea la migración 2 (Ej. 2, US-005) y se evalúa en el Ej. 7. | El Ej. 2 escribe y aplica la migración 2. El Ej. 7 **demuestra y consolida** (C-14, `test/solo_agregado.sql`, captura `psql`) y revisa RN-20 e `intento_acceso`; no vuelve a crear el disparador. |
| T-7 | **`intento_acceso` en transacción propia**: el login (Ej. 4) no funciona sin anotar intentos (RN-08 los cuenta). | El Ej. 4 lo implementa con un **UoW dedicado de intentos de acceso** (sesión y transacción propias, se confirma siempre; DD-19): ningún commit fuera de un UoW (regla B-8). El Ej. 7 lo audita, documenta el costo en el comentario y lo prueba. |
| T-8 | **Lo propio (Ej. 5) sobre órdenes (Ej. 6)**: `GET /ordenes/{id}` ajena → 403 necesita el endpoint de órdenes. | El Ej. 5 entrega `/mis-vehiculos`, `/mis-ordenes` y el helper de comprobación de dueño. El 403 de `GET /ordenes/{id}` ajena y de cancelar ajena se cablea en el Ej. 6, cuando existen esos endpoints. C-06 queda completo en el Ej. 6. |
| T-9 | **Aviso en segundo plano (Ej. 8) sobre terminar orden (Ej. 6)**. | El Ej. 6 entrega `terminar` completo (RN-13) **sin** aviso. El Ej. 8 agrega `BackgroundTasks` en el router. C-12 queda completo en el Ej. 8. |
| T-10 | **Carga perezosa prohibida (RT-TX-05)** vale desde el primer repositorio (en SQLAlchemy async además falla). | Desde el Ej. 3 todo método de repositorio que devuelva relaciones las precarga (`selectinload`/`joinedload`) dentro del método. El Ej. 8 verifica el conteo fijo de consultas (C-15) y produce la evidencia. |
| T-11 | **Rutas protegidas y cambio obligatorio (RN-06)**: dos grupos de rutas en `main.py` (Ej. 5). | Los routers de los Ej. 1, 3 y 4 se montan en `main.py` de forma que el Ej. 5 sólo los mueva al grupo correspondiente (abierto: `/health`, `/auth/*`; protegido: el resto). |

---

## Árbol de dependencias

```
01-proyecto-config-lifespan
 └── 02-modelos-migraciones-seed
      └── 03-contratos-crud
           └── 04-autenticacion
                └── 05-autorizacion
                     └── 06-repositorios-uow-ordenes
                          └── 07-integridad
                               └── 08-lecturas-sin-n1-asincronia
```

Cadena lineal: cada change depende únicamente del anterior (y, transitivamente, de todos los previos).

### Paralelismo por fase

**No hay paralelismo.** Los "gates" son puntos de relevo: al completarse un change se desbloquea **exactamente uno** y lo toma **un solo integrante**.

```
GATE 0: (inicio del proyecto)
  → EJ-1 01-proyecto-config-lifespan            [Integrante 1]
GATE 1: EJ-1 ✓ (commit + push)
  → EJ-2 02-modelos-migraciones-seed            [Integrante en turno]
GATE 2: EJ-2 ✓ (commit + push)
  → EJ-3 03-contratos-crud                      [Integrante en turno]
GATE 3: EJ-3 ✓ (commit + push)
  → EJ-4 04-autenticacion                       [Integrante en turno]
GATE 4: EJ-4 ✓ (commit + push)
  → EJ-5 05-autorizacion                        [Integrante en turno]
GATE 5: EJ-5 ✓ (commit + push)
  → EJ-6 06-repositorios-uow-ordenes            [Integrante en turno]
GATE 6: EJ-6 ✓ (commit + push)
  → EJ-7 07-integridad                          [Integrante en turno]
GATE 7: EJ-7 ✓ (commit + push)
  → EJ-8 08-lecturas-sin-n1-asincronia          [Integrante en turno]
GATE 8: EJ-8 ✓ (commit + push) → entrega final (README, capturas C-14 y C-15)
```

### Camino crítico (8 changes — la cadena completa)

`EJ-1 → EJ-2 → EJ-3 → EJ-4 → EJ-5 → EJ-6 → EJ-7 → EJ-8`

Es lineal y coincide con el total: los 8 ejercicios se evalúan (100 % del puntaje) y ninguno se puede omitir ni reordenar.

### Plan de relevos del equipo (un solo integrante a la vez)

El equipo decide quién toma cada turno; la tabla fija el orden y el peso de cada uno para repartir la carga.

| Turno | Change | Puntos | Entrega que habilita al siguiente turno |
|---|---|---|---|
| 1 | EJ-1 `01-proyecto-config-lifespan` | 8 | Repo compartido, app que levanta, `/health/*`, `env.example` |
| 2 | EJ-2 `02-modelos-migraciones-seed` | 14 | Esquema por Alembic (2 migraciones), `seed.py` |
| 3 | EJ-3 `03-contratos-crud` | 10 | CRUD de clientes, vehículos y repuestos con paginación |
| 4 | EJ-4 `04-autenticacion` | 16 | Registro, login con cookie, logout, `yo`, cambio de contraseña |
| 5 | EJ-5 `05-autorizacion` | 14 | Roles vigentes, 401/403, administración de personal, dos grupos de rutas |
| 6 | EJ-6 `06-repositorios-uow-ordenes` | 20 | Jerarquía de repositorios, UoW, módulo de órdenes completo |
| 7 | EJ-7 `07-integridad` | 10 | Disparador demostrado, `intento_acceso` auditado, evidencia C-14 |
| 8 | EJ-8 `08-lecturas-sin-n1-asincronia` | 8 | Consultas fijas, aviso en segundo plano, evidencia C-15 |

---

## FASE 1 — Fundaciones del proyecto

### [EJ-1] `01-proyecto-config-lifespan`
- **Estado**: `[x]` hecho (EJ-1: 30 tests en verde, 0 skipped)
- **Ejercicio / puntos**: Ejercicio 1 — 8 pts (8 %)
- **Scope**:
  - Repositorio compartido: ya creado en la fundación (ver nota de arriba); `.gitignore` ya cubre `.env`, `.venv`, `__pycache__`. EJ-1 sólo agrega lo que haga falta para Docker (p. ej. `.dockerignore`) y completa el `README.md` existente con la puesta en marcha de la app (Docker y venv).
  - Esqueleto de directorios obligatorio completo (T-1): `main.py`, `seed.py` (vacío), `app/core/{config,database,security,dependencies,repository,paginacion,unit_of_work}.py` (los que aún no tienen contenido quedan como módulos vacíos con docstring), `app/modules/{health,usuarios,clientes,repuestos,ordenes}/`, `migrations/`, `test/`.
  - `app/core/config.py`: `Settings` (pydantic-settings) leyendo entorno o `.env`; URL asincrónica de la base con `@computed_field` desde `POSTGRES_*` (driver `asyncpg`); **sin valor por defecto** para la clave de firma ni `POSTGRES_PASSWORD` (si faltan, la app no arranca); declarar las variables fijadas en DD-30 (`JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_SECONDS`, `COOKIE_SECURE`, `BCRYPT_ROUNDS`, `BCRYPT_MAX_CONCURRENCY`, `DB_POOL_SIZE`, `SQL_ECHO`, `POSTGRES_TEST_DB`) con sus defaults; `JWT_SECRET` fijo, nunca generado al arrancar (DD-20).
  - **Docker (DD-32)**: `Dockerfile` multi-stage (Python 3.12 slim, usuario no-root), `.dockerignore`, `docker-compose.yml` con `api` (uvicorn) + `db` (`postgres:16`, volumen persistente, healthcheck) y creación de la base de test `POSTGRES_TEST_DB`; credenciales desde `.env` (`env_file` / `${POSTGRES_PASSWORD}`), nunca escritas en el compose; `POSTGRES_HOST=db` dentro del compose. El `README.md` documenta **las dos formas** de levantar: Docker (`docker compose up`, `docker compose exec api alembic upgrade head`, `... python seed.py`) y la de la consigna (venv, dependencias, `.env`, `alembic upgrade head`, `python seed.py`, uvicorn).
  - `env.example` con todas las variables y ningún secreto; `requirements.txt` con las versiones del stack; `README.md` inicial con pasos de puesta en marcha (entorno virtual, dependencias, `.env` con cómo generar la clave de firma).
  - `app/core/database.py`: funciones que crean motor asincrónico y fábrica de sesiones (las llama el lifespan, **no se ejecutan al importar**); `get_session` toma la fábrica de `app.state`, entrega una sesión por petición con `expire_on_commit=False` y la cierra al terminar.
  - `main.py`: `lifespan` que crea motor y fábrica en `app.state`, calcula **una vez** el hash ficticio del login y hace `engine.dispose()` al apagar.
  - `GET /health/live` (200, no toca la base) y `GET /health/ready` (`SELECT 1`; 200 o **503** si la base no contesta).
  - Tests: `.http` de salud (live 200; ready 200 con base arriba y 503 con base caída), arranque fallido sin variables obligatorias.
  - Runner de tests (DD-13, regla E-2 de `AGENTS.md`): pytest + httpx (+ pytest-asyncio o anyio) contra una PostgreSQL real de test, en `test/pytest/`, con los tests de salud y de configuración como primer ciclo RED/GREEN.
- **Puntos de la consigna**: US-001 (configuración), US-002 (ciclo de vida), US-003 (salud).
- **Reglas relacionadas**: RT-SE-01, RT-SE-08, EA-08 / DD-09 (recursos en el lifespan).
- **Casos C-xx demostrables**: ninguno de C-01..C-19 (se verifican las sondas de salud y el arranque; el caso C-01 de la lista requiere sesión y se demuestra en EJ-4).
- **Dependencias**: ninguna
- **Governance**: BAJO (scaffolding y configuración; ojo a la regla dura: ningún secreto por defecto ni versionado, que es criterio bloqueante de la entrega).
- **Preguntas abiertas que lo tocan**: ninguna; resueltas: variables de entorno (DD-30) y Docker app + base (DD-32).
- **Definition of Done / handoff**: `.http` de salud con respuesta esperada; la app levanta con `.env` válido y no arranca sin clave de firma; commit + push con el repositorio ya creado.
- **Leer antes**:
  - `knowledge-base/02_descripcion_general.md` (stack, configuración, endpoints de salud)
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios, §Variables de entorno
  - `knowledge-base/06_funcionalidades.md` §Épica 1
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-09, §DD-20, §DD-30, §DD-32

---

## FASE 2 — Datos: modelos, migraciones y datos iniciales

### [EJ-2] `02-modelos-migraciones-seed`
- **Estado**: `[ ]` pendiente
- **Ejercicio / puntos**: Ejercicio 2 — 14 pts (14 %)
- **Scope**:
  - Modelos SQLModel en `app/modules/*/models.py` con los **nombres obligatorios** de tablas y columnas: `usuario`, `asignacion_rol`, `intento_acceso`, `evento_seguridad`, `cliente`, `vehiculo`, `repuesto`, `estado_orden`, `orden_trabajo`, `item_orden`, `historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto` (clase `HistorialPrecio`, IN-02).
  - Tres índices únicos parciales con `postgresql_where`: `asignacion_rol (usuario_id, rol) WHERE revocada_en IS NULL`, `vehiculo (patente) WHERE borrado_en IS NULL`, `repuesto (codigo) WHERE borrado_en IS NULL`.
  - Estados de la orden y del historial como **FK a `estado_orden`** (no CHECK); CHECK `precio_nuevo <> precio_anterior`; índice en cada FK; fechas `timestamptz`; dinero `NUMERIC`/`Decimal`.
  - Relaciones navegables en los dos extremos de cada relación que se lea (`Usuario.cliente` devuelve un objeto, no una lista).
  - Alembic con **plantilla asincrónica**; `alembic.ini` sin credenciales (URL desde `Settings`); **no se usa `create_all`**.
  - Migración 1: `--autogenerate`, todas las tablas. Migración 2: **escrita a mano**, función + disparador de sólo agregado sobre `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto` (rechaza `UPDATE` y `DELETE`). Cada migración con comentario que declara que se leyó antes de aplicarla. Catálogo vacío tras migrar.
  - `seed.py`: vacía las tablas y carga **primero el catálogo** (`PENDIENTE` 1, `EN_REPARACION` 2, `TERMINADA` 3 final, `CANCELADA` 4 final); usuarios (7), clientes (Laura con 2 vehículos, Jorge con 1), repuestos con ids/códigos/precios de la tabla de ejemplos y movimiento «Stock inicial», bujía `BUJ-014` «Bujía de encendido» a 6500.00 (DD-16), órdenes 1 (`PENDIENTE`, «Cambio de aceite y filtro», 1 filtro + 4 L de aceite = 56500.00; DD-15) y 2 (`EN_REPARACION`, «Falla de encendido», 4 bujías cuando hay 2 = 26000.00, `mecanico_id` = mecanico@), historial de estados coherente (alta por recepcion@, inicio de la 2 por mecanico@), historial de precios del filtro (8000 → 8500) y evento de seguridad con actor `SISTEMA`. Actores del seed según DD-14: stock inicial y precio → admin@. Hash bcrypt directo (T-5).
  - Tests: `upgrade head` → `downgrade base` → `upgrade head`; el seed corre dos veces seguidas y deja el mismo estado; comprobaciones SQL de índices parciales y de la FK de estado.
- **Puntos de la consigna**: US-004 (modelos con restricciones), US-005 (Alembic), US-006 (datos iniciales).
- **Reglas relacionadas**: RN-01, RN-03, RN-15 (disparador), RN-19, RT-SE-08.
- **Casos C-xx demostrables**: ninguno completo. Parciales: C-14 (el disparador y la FK de estado ya rechazan; la evidencia formal es del Ej. 7) y la base de C-19 (índice único parcial de `vehiculo.patente`).
- **Dependencias**: `EJ-1`
- **Governance**: CRITICO (modelos core que todo lo demás referencia; los nombres de tablas/columnas son obligatorios y los usa la corrección; un error de esquema se arrastra a los 6 changes siguientes).
- **Preguntas abiertas que lo bloquean o tocan**: resueltas: actores del seed (DD-14), ítems de la orden 1 (DD-15), bujía (DD-16) e historial de la orden 2 (DD-14); quedan: IN-01 (diagrama vs. tabla: manda la tabla); SU-02 (`otorgada_por`).
- **Definition of Done / handoff**: ciclo `upgrade/downgrade/upgrade` verde; `python seed.py` idempotente; consultas `psql` que muestran índices y disparador; commit + push de modelos, `migrations/` y `seed.py`.
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` (completo: entidades, índices únicos parciales, migraciones, seed)
  - `knowledge-base/05_reglas_de_negocio.md` §Identidad y unicidad, §RN-15, §RN-19
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-01..DD-03, §DD-06, §SU-01, §SU-02
  - `knowledge-base/10_preguntas_abiertas.md` (todas las filas que bloquean `seed.py`)
  - `knowledge-base/03_actores_y_roles.md` §Modelo de roles, §Usuarios iniciales (seed)

---

## FASE 3 — API de recursos

### [EJ-3] `03-contratos-crud`
- **Estado**: `[ ]` pendiente
- **Ejercicio / puntos**: Ejercicio 3 — 10 pts (10 %)
- **Scope**:
  - `schemas.py` por módulo con contratos de entrada **separados** de los modelos de tabla, `extra="forbid"` (nadie edita el stock por PATCH → 422) y contratos de salida sin `password_hash`; PATCH con `exclude_unset`.
  - `app/core/paginacion.py`: envoltorio `{items, total, page, size, pages}`, `page ≥ 1`, `size` 1..100 (def. 20), página fuera de rango → 422 («La página N no existe: hay M»), cero resultados → una página vacía, `total` con los mismos filtros.
  - Mínimos de capas (T-2): `app/core/repository.py` (`BaseRepository[T]`, `SoftDeleteRepository[T]`), `app/core/unit_of_work.py`, UoW de `clientes` y `repuestos`, `service.py` y `router.py` por módulo; precarga declarada en el repositorio (T-10).
  - `clientes`: `POST /clientes` (201/409/422), `GET /clientes/{id}` con sus vehículos (200/404), `POST /clientes/{id}/vehiculos` (201/404/409/422; patente duplicada entre vigentes → 409), `DELETE /vehiculos/{id}` (borrado lógico 204; con órdenes abiertas → 409 usando `es_final` del catálogo; ya dado de baja → 404, DD-22).
  - `repuestos`: `GET /repuestos?q=&page=&size=` (búsqueda «contiene» con parámetros ligados, excluye dados de baja), `GET /repuestos/{id}`, `POST /repuestos` con `stock_inicial ≥ 0` (default 0; movimiento «Stock inicial» sólo si es > 0; negativo → 422; DD-23), `DELETE /repuestos/{id}` siempre 204 aunque esté en órdenes abiertas, ya dado de baja → 404 (DD-21, DD-22), `POST /repuestos/{id}/reponer` con `{cantidad > 0, motivo? ≤120}` (default «Reposición»; DD-29), `PATCH /repuestos/{id}` (sólo descripción y precio; cambio de precio deja línea en `historial_precio_repuesto` en la misma transacción; precio igual → sin línea), `DELETE /repuestos/{id}` (204), `POST /repuestos/{id}/reponer` (200/404/422), `GET /repuestos/{id}/movimientos`, `GET /repuestos/{id}/precios`.
  - Punto único de escritura de stock (T-3) y actor temporal (T-4).
  - Traducción de `IntegrityError` a 409/422 con mensaje propio (RN-18); validadores de contrato para que ninguna entrada inválida termine en 500.
  - Tests: `test/clientes_vehiculos.http`, `test/repuestos.http` con respuesta esperada en comentarios.
- **Puntos de la consigna**: US-007 (contratos estrictos), US-008 (listados paginados), US-009 (clientes y vehículos), US-010 (catálogo de repuestos).
- **Reglas relacionadas**: RN-01, RN-14, RN-16, RN-18, RN-20, RT-PG-01..06, RT-PG-07, RT-TX-01..03 (versión mínima), RT-TX-05.
- **Casos C-xx demostrables**: C-16 (inyección en `q`, paginación con filtro, PATCH parcial, PATCH del stock → 422), C-19 (baja de vehículo y reutilización de patente), C-18 (línea de historial al cambiar el precio; el 403 de recepción llega en EJ-5), C-01 en su parte de 422 por ruta no entera (la parte «con sesión iniciada» se completa en EJ-4).
- **Dependencias**: `EJ-2`
- **Governance**: MEDIO (lógica de negocio con transacciones —precio + historial, stock por movimientos—; sin autenticación todavía, así que las rutas quedan abiertas hasta EJ-5 y esto debe constar en el README).
- **Preguntas abiertas que lo tocan**: ninguna; resueltas: baja de repuesto (DD-21), doble baja → 404 (DD-22), `stock_inicial` (DD-23), motivos y `/reponer` (DD-29); mensajes de error en lenguaje humano (DD-25). Supuestos de contrato vigentes: SU-06, SU-07, SU-08, SU-09.
- **Definition of Done / handoff**: `.http` de clientes/vehículos/repuestos con respuestas esperadas; ningún 500 con entradas inválidas; migraciones y seed intactos; commit + push.
- **Leer antes**:
  - `knowledge-base/02_descripcion_general.md` §Endpoints de referencia y convenciones de códigos
  - `knowledge-base/05_reglas_de_negocio.md` §Contratos y paginación (RT-PG), §Stock y repuestos, §Errores
  - `knowledge-base/07_flujos_principales.md` §Flujo 10, §Flujo 11, §Flujo 12, §Flujo 13
  - `knowledge-base/06_funcionalidades.md` §Épica 3
  - `knowledge-base/08_arquitectura_propuesta.md` §Repositorios, §Responsabilidad por capa

---

## FASE 4 — Seguridad

### [EJ-4] `04-autenticacion`
- **Estado**: `[ ]` pendiente
- **Ejercicio / puntos**: Ejercicio 4 — 16 pts (16 %)
- **Scope**:
  - `app/core/security.py`: bcrypt **siempre fuera del bucle** (`asyncio.to_thread`) y bajo `asyncio.Semaphore(BCRYPT_MAX_CONCURRENCY)`, costo desde `Settings`; emisión y verificación de JWT con PyJWT (`sub`, `iat` con fracción de segundo, `exp`, roles vigentes al emitir).
  - Contratos con límite de **72 bytes** (bytes, no caracteres) en todo campo que termina en bcrypt → 422, nunca 500.
  - `POST /auth/registro`: usuario + rol `CLIENTE` + ficha de cliente en **un solo UoW** (201); correo o documento repetido → 409 con mensaje propio y sin filas sueltas; no se apropia de una ficha existente; el hash se calcula **antes** de abrir la transacción. UoW de `usuarios` (T-2). Cuerpo plano `{email, password, nombre, documento, telefono}` (`nombre` va al usuario y a la ficha); responde 201 **con `Set-Cookie access_token`** emitida **después** del commit del UoW (si el UoW revierte, no hay cookie); el cuerpo nunca trae el token (DD-17).
  - `POST /auth/login`: (1) límite de intentos (5 fallos / 60 s por correo+IP → 429 + `Retry-After`, sin calcular hash), (2) verificación contra el hash real o el **ficticio** del lifespan; mismo cuerpo y tiempo exista o no el correo (401); JWT en cookie `access_token` (`HttpOnly`, `SameSite=Lax`, `Max-Age`, `Secure` configurable); cuerpo `{ "mensaje": "Sesión iniciada", "debe_cambiar_password": false, "expira_en_segundos": 1800 }` sin token; un login correcto reinicia el conteo (SU-10).
  - Cada intento (correcto o fallido) se anota en `intento_acceso` desde un **UoW dedicado con sesión y transacción propias, confirmado siempre** (T-7, DD-19), con el comentario que lo declara y su costo.
  - Clave de firma del JWT **fija**, leída de `JWT_SECRET` en `.env`; nunca generada al arrancar (DD-20, regla S-7).
  - `POST /auth/logout` (borra la cookie, 200), `GET /auth/yo` (usuario, roles vigentes y roles del token), `POST /auth/cambiar-password` (contraseña actual + nueva ≤ 72 bytes; anota `password_cambiada_en`, limpia `debe_cambiar_password`, emite cookie nueva; las anteriores dan 401 aunque sean del mismo segundo — comparación de `iat` sin truncar).
  - Una dependencia mínima de lectura de la cookie que `/auth/yo` y `cambiar-password` necesitan (la dependencia completa con roles y control de cambio pendiente es del Ej. 5; esta se reutiliza, no se duplica).
  - Tests: `test/auth.http` con varias sesiones (REST Client: `# @name`, `# @no-cookie-jar`, `Cookie: {{login.response.headers.Set-Cookie}}`).
- **Puntos de la consigna**: US-011 (auto-registro), US-012 (login con cookie), US-013 (logout, quién soy, cambio de contraseña).
- **Reglas relacionadas**: RN-01, RN-02, RN-06 (parcial), RN-07, RN-08, RN-09, RT-SE-01..07, RT-SE-09.
- **Casos C-xx demostrables**: C-02, C-03, C-04, C-05 (parte de `intento_acceso`; auditoría formal en EJ-7), C-09 (parte: cookie nueva vale y la anterior da 401 sin esperar; el 403 de bloqueo llega en EJ-5), C-01 completo (422 de ruta con la sesión iniciada).
- **Dependencias**: `EJ-3`
- **Governance**: CRITICO (autenticación: hashing, JWT, cookie, límite de intentos, enumeración de cuentas).
- **Preguntas abiertas que lo bloquean**: cuerpo de `POST /auth/registro` resuelto (DD-17); login de usuario inactivo resuelto (DD-24: 401 genérico salvo contraseña correcta con cuenta inactiva → «Tu cuenta está desactivada…»); contraseña actual incorrecta en el cambio (SU-05 → 401); acciones de `evento_seguridad` resueltas (DD-26, incluye «Login bloqueado por demasiados intentos» en el 429).
- **Definition of Done / handoff**: `.http` con C-01..C-05 y la parte demostrable de C-09; sin token en el cuerpo ni lectura de `Authorization`; hash fuera del bucle verificado; commit + push.
- **Leer antes**:
  - `knowledge-base/07_flujos_principales.md` §Flujo 1, §Flujo 2, §Flujo 3, §Flujo 4
  - `knowledge-base/05_reglas_de_negocio.md` §Autenticación y sesión, §Seguridad técnica (RT-SE)
  - `knowledge-base/08_arquitectura_propuesta.md` §Seguridad
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-04, §DD-05, §DD-17, §DD-19, §DD-20, §DD-24, §DD-25, §DD-26, §SU-05, §SU-10
  - `knowledge-base/10_preguntas_abiertas.md` (cuerpo de registro, usuario inactivo)

### [EJ-5] `05-autorizacion`
- **Estado**: `[ ]` pendiente
- **Ejercicio / puntos**: Ejercicio 5 — 14 pts (14 %)
- **Scope**:
  - `app/core/dependencies.py`: `get_usuario_actual` (401 sin cookie, token inválido/vencido, usuario inexistente/inactivo o `iat` anterior a `password_cambiada_en`) y `requiere_rol` (403; **consulta `asignacion_rol` en cada petición**; los roles del token son informativos).
  - Reemplazar el actor temporal del Ej. 3 (T-4) por `get_usuario_actual` y proteger con `requiere_rol` las rutas de clientes, vehículos y repuestos según la matriz RBAC.
  - `main.py` con **dos grupos de rutas**: el abierto (`/health/*`, `/auth/*`) y el protegido con el control de cambio obligatorio **montado una sola vez**; con cambio pendiente: 403 en todo lo protegido (T-11).
  - `POST /usuarios` (ADMIN): alta de personal con cuerpo `{email, nombre, password_provisoria, rol}` (`rol` ∈ ADMIN/RECEPCION/MECANICO; `CLIENTE` → 422), `debe_cambiar_password = true`, usuario + asignación de rol (`otorgada_por` = admin) + evento en **un solo UoW** (DD-18); `GET /usuarios/{id}/roles`, `POST /usuarios/{id}/roles` (vencimiento opcional **con zona horaria y en el futuro**, si no 422), `DELETE /usuarios/{id}/roles/{rol}` (revoca sin borrar la fila).
  - Reasignar un rol vencido cierra la fila anterior y abre una nueva; rol abierto duplicado → 409 (índice parcial).
  - Autoprotección (RN-05): el admin no se revoca su ADMIN y nunca quedan cero administradores vigentes (409).
  - `GET /eventos` (ADMIN, paginado) sobre `evento_seguridad`; registrar altas, cambios de rol y de contraseña con el actor.
  - `GET /mis-vehiculos` y `GET /mis-ordenes` (paginados, sólo autenticado) y helper de comprobación de dueño (T-8).
  - Tests: `test/autorizacion.http` con sesiones simultáneas de ADMIN y RECEPCION.
- **Puntos de la consigna**: US-014 (usuario actual y roles vigentes), US-015 (personal y roles), US-016 (cambio obligatorio), US-017 (lo propio).
- **Reglas relacionadas**: RN-03, RN-04, RN-05, RN-06, RN-07, RN-17, RT-SE-10, RT-SE-11.
- **Casos C-xx demostrables**: C-07, C-08, C-09 (completo), C-06 (parte: 401 vs 403 y `/mis-*`; el 403 de orden ajena se completa en EJ-6), C-18 (403 a la recepción), C-17 (parte: 401 sin sesión sobre `/estados-orden` cuando exista).
- **Dependencias**: `EJ-4`
- **Governance**: CRITICO (permisos, roles y revocación de sesiones; un hueco acá expone toda la API).
- **Preguntas abiertas que lo bloquean o tocan**: cuerpo de `POST /usuarios` resuelto (DD-18); acciones de `evento_seguridad` resueltas (DD-26); `/mis-vehiculos` sólo vigentes y `/mis-ordenes` todas, incluidas las de vehículos dados de baja (DD-28); el personal (incluido MECANICO) ve cualquier orden (DD-27; se cablea en EJ-6).
- **Definition of Done / handoff**: `.http` con C-06 (parte), C-07, C-08, C-09; ninguna ruta de datos sin protección; el actor temporal eliminado; commit + push.
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` (RBAC completo, 401 vs 403, rutas públicas)
  - `knowledge-base/05_reglas_de_negocio.md` §Autorización, §Registro y usuarios, RT-SE-10, RT-SE-11
  - `knowledge-base/07_flujos_principales.md` §Flujo 3, §Flujo 5
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-01, §DD-10, §DD-18, §DD-26, §DD-27, §DD-28, §SU-03, §SU-11
  - `knowledge-base/10_preguntas_abiertas.md` (cuerpo de `POST /usuarios`, eventos)

---

## FASE 5 — Arquitectura transaccional y órdenes

### [EJ-6] `06-repositorios-uow-ordenes`
- **Estado**: `[ ]` pendiente
- **Ejercicio / puntos**: Ejercicio 6 — 20 pts (20 %, el de mayor peso)
- **Scope**:
  - **Completar y auditar** la jerarquía de repositorios (T-2): `BaseRepository[T]` y `SoftDeleteRepository[T]` con todo lo exigido (`get_by_id_including_deleted`, `soft_delete`, `flush` y nunca `commit`); un repositorio por entidad con métodos nombrados por lo que traen (p. ej. `get_detalle_con_items_e_historial`) y precarga declarada **dentro** del método; `EstadoOrdenRepository` de **sólo lectura** que **no** hereda de `BaseRepository`.
  - `UnitOfWork` base y un UoW por módulo (`usuarios`, `clientes`, `repuestos`, `ordenes`) que compone sus repositorios con la misma sesión; el router lo construye (dependencia) y lo pasa **sin abrir**; el servicio lo abre con `async with`; el UoW no cierra la sesión. Revisar y corregir los módulos de los Ej. 3-5 para que lo cumplan.
  - RN-02, RN-13 y RN-20 **cada una en un solo bloque** de UoW; punto único de escritura de stock reutilizado por reposición y terminación (T-3).
  - Módulo `ordenes` completo (modelos ya existentes del Ej. 2): `POST /ordenes` (RECEPCION, ADMIN; nace `PENDIENTE`, ≥1 ítem, sin repetidos → 422, precio copiado del repuesto, total calculado por el servidor, primera línea de historial; repuesto inexistente/dado de baja o vehículo dado de baja → 409 y no queda la orden; catálogo vacío → 409 con mensaje propio); `GET /ordenes` (filtro `estado` con enum y paginado); `GET /ordenes/{id}` con vehículo, cliente, ítems, repuesto de cada ítem e historial (403 si es ajena para CLIENTE, T-8); `POST /ordenes/{id}/iniciar` (MECANICO, `PENDIENTE → EN_REPARACION`, queda asignado); `POST /ordenes/{id}/terminar` (mecánico asignado o ADMIN; descuenta stock, un movimiento por ítem, línea de historial, todo o nada → 409 si falta stock); `POST /ordenes/{id}/cancelar` (RECEPCION, ADMIN o dueño; **403 antes que 409**; sólo desde `PENDIENTE`); `GET /estados-orden` por posición.
  - Sin aviso en segundo plano todavía (T-9).
  - Tests: `test/ordenes.http` (alta, terminar con y sin stock, cancelar con distintos actores, catálogo de estados).
- **Puntos de la consigna**: US-018 (jerarquía de repositorios), US-019 (Unit of Work), US-020 (órdenes de trabajo).
- **Reglas relacionadas**: RN-02, RN-10, RN-11, RN-12, RN-13, RN-14, RN-16, RN-19, RN-20, RT-TX-01..05, RT-PG-08.
- **Casos C-xx demostrables**: C-10, C-11, C-12 (sin el aviso, que llega en EJ-8), C-13, C-17, C-06 (completo: 200 propia / 403 ajena).
- **Dependencias**: `EJ-5`
- **Governance**: ALTO (transacciones multi-escritura y máquina de estados; es el ejercicio de mayor peso).
- **Preguntas abiertas que lo tocan**: ninguna; resueltas: órdenes existentes con un repuesto dado de baja se terminan normal con `get_by_id_including_deleted` (DD-21); el ADMIN que termina no cambia `mecanico_id` (DD-31); el personal ve cualquier orden (DD-27); motivo de salida «Salida por orden de trabajo #N» armado por el servidor (DD-29). Supuesto vigente: SU-06.
- **Definition of Done / handoff**: `.http` con C-06, C-10, C-11, C-12 (sin aviso), C-13, C-17; no existe ningún `commit()` en repositorios ni ningún servicio que construya su UoW; commit + push.
- **Leer antes**:
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados, §Responsabilidad por capa, §Repositorios
  - `knowledge-base/05_reglas_de_negocio.md` §Órdenes de trabajo, §Stock y repuestos, §Transacciones y persistencia (RT-TX)
  - `knowledge-base/07_flujos_principales.md` §Flujo 6, §Flujo 7, §Flujo 8, §Flujo 9
  - `knowledge-base/06_funcionalidades.md` §Épica 6
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-02, §DD-08, §SU-06, §SU-07, §SU-08

---

## FASE 6 — Integridad, rendimiento y asincronía

### [EJ-7] `07-integridad`
- **Estado**: `[ ]` pendiente
- **Ejercicio / puntos**: Ejercicio 7 — 10 pts (10 %)
- **Scope**:
  - **Sólo agregado**: el disparador ya existe desde la migración 2 del Ej. 2 (T-6); este change lo **demuestra y consolida**. `test/solo_agregado.sql` con `UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto` (los seis rechazados por el disparador) y el intento de insertar una orden con un estado inexistente del catálogo (rechazado por la **clave foránea**). Captura de `psql` como evidencia de entrega.
  - Revisar que el disparador rechace toda modificación “venga de donde venga” (también sobre filas creadas por la aplicación en los Ej. 3 y 6) y que `downgrade` lo quite limpiamente.
  - **Historial de precios en la misma transacción** que el cambio (RN-20): auditar el flujo del Ej. 3/6 y agregar la prueba.
  - **`intento_acceso` en su propia sesión** (T-7): auditar la implementación del Ej. 4, asegurar que se confirma siempre (también si la petición falla o devuelve 429/401), y que el comentario del código declare la excepción y su costo (deja filas aunque la petición falle). Confirmar que es la única escritura fuera de la transacción de su petición.
  - Corregir lo que la auditoría encuentre; no se agregan endpoints nuevos.
  - Tests: `test/solo_agregado.sql`, ampliación de `test/auth.http` y `test/repuestos.http` para los casos de integridad.
- **Puntos de la consigna**: US-021 (sólo agregado), US-022 (intento de acceso en su propia transacción).
- **Reglas relacionadas**: RN-15, RN-19, RN-20, RT-SE-09.
- **Casos C-xx demostrables**: C-14 (completo), C-05 (los cinco fallos quedan en `intento_acceso`), C-18 (atomicidad del cambio de precio).
- **Dependencias**: `EJ-6`
- **Governance**: CRITICO (audit trail: integridad de historiales y de intentos de acceso).
- **Preguntas abiertas que lo tocan**: ninguna bloqueante; verificar que `evento_seguridad` registre exactamente lo de DD-26.
- **Definition of Done / handoff**: `test/solo_agregado.sql` corrido con los seis rechazos + el de la FK; captura de `psql` guardada para la entrega; commit + push.
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Integridad y auditoría (RN-15), RN-20, RT-SE-09
  - `knowledge-base/04_modelo_de_datos.md` §Migraciones, §historial_estado_orden, §movimiento_stock, §historial_precio_repuesto
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-05, §DD-06
  - `knowledge-base/11_casos_de_prueba_y_entrega.md` (C-14, evidencia de entrega)

### [EJ-8] `08-lecturas-sin-n1-asincronia`
- **Estado**: `[ ]` pendiente
- **Ejercicio / puntos**: Ejercicio 8 — 8 pts (8 %)
- **Scope**:
  - **Carga anticipada**: auditar que toda respuesta con datos de relaciones use `selectinload`/`joinedload` declarado en el repositorio y que nada dependa de la carga perezosa (T-10); detalle de orden con **número fijo de consultas** (mismo número con 2 y con 4 ítems).
  - `SQL_ECHO=true` para ver las consultas en consola; evidencia C-15 (fragmento de consola con el detalle de una orden de 2 ítems y de otra de 4).
  - **Aviso en segundo plano**: al terminar una orden, `BackgroundTasks` agenda el aviso (`await asyncio.sleep(0.5)` + mensaje en el registro); corre **después de enviar la respuesta** y **sólo si la operación se confirmó** (no se agenda si terminar dio 409). Se agenda desde el router (T-9).
  - Auditar que todos los handlers sean `async def` y que no haya llamadas bloqueantes (bcrypt fuera del bucle ya desde el Ej. 4).
  - Cierre del proyecto: `README.md` final con pasos desde cero, checklist de entrega completa (`.env` fuera del repo, `env.example`, `test/*.http` con C-01..C-19, capturas C-14 y C-15).
  - Tests: ampliación de `test/ordenes.http` (C-12 completo y C-15).
- **Puntos de la consigna**: US-023 (carga anticipada), US-024 (aviso en segundo plano).
- **Reglas relacionadas**: RT-TX-05, RT-TX-06, RT-TX-07, DD-07.
- **Casos C-xx demostrables**: C-15, C-12 (completo: el aviso sale en el registro después de la respuesta).
- **Dependencias**: `EJ-7`
- **Governance**: MEDIO (rendimiento y tareas en segundo plano; sin riesgo de datos, pero cierra la entrega).
- **Preguntas abiertas que lo tocan**: ninguna bloqueante.
- **Definition of Done / handoff**: evidencia C-15 guardada; C-12 con aviso verificado en el registro; checklist de entrega de `11_casos_de_prueba_y_entrega.md` completa; commit + push final.
- **Leer antes**:
  - `knowledge-base/05_reglas_de_negocio.md` §Transacciones y persistencia (RT-TX-05..07)
  - `knowledge-base/07_flujos_principales.md` §Flujo 8
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-07
  - `knowledge-base/11_casos_de_prueba_y_entrega.md` (C-12, C-15, checklist de entrega)

---

## Resumen

| Change | Ejercicio | Puntos | Governance | Depende de | Casos C-xx que se vuelven demostrables |
|---|---|---|---|---|---|
| EJ-1 `01-proyecto-config-lifespan` | 1 | 8 | BAJO | — | (salud y arranque) |
| EJ-2 `02-modelos-migraciones-seed` | 2 | 14 | CRITICO | EJ-1 | C-14 (parcial), base de C-19 |
| EJ-3 `03-contratos-crud` | 3 | 10 | MEDIO | EJ-2 | C-16, C-19, C-18 (parcial), C-01 (parcial) |
| EJ-4 `04-autenticacion` | 4 | 16 | CRITICO | EJ-3 | C-01, C-02, C-03, C-04, C-05 (parcial), C-09 (parcial) |
| EJ-5 `05-autorizacion` | 5 | 14 | CRITICO | EJ-4 | C-06 (parcial), C-07, C-08, C-09, C-18 |
| EJ-6 `06-repositorios-uow-ordenes` | 6 | 20 | ALTO | EJ-5 | C-06, C-10, C-11, C-12 (sin aviso), C-13, C-17 |
| EJ-7 `07-integridad` | 7 | 10 | CRITICO | EJ-6 | C-14, C-05, C-18 |
| EJ-8 `08-lecturas-sin-n1-asincronia` | 8 | 8 | MEDIO | EJ-7 | C-15, C-12 |

**Camino crítico**: 8 changes (toda la cadena) · **Gates de paralelismo**: 0 (relevos secuenciales) · **Primer change recomendado**: `EJ-1` (`01-proyecto-config-lifespan`).

Para arrancar: `/opsx:propose 01-proyecto-config-lifespan`
