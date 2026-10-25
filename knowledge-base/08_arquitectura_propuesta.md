# Arquitectura Propuesta

> La estructura de directorios y la responsabilidad de cada archivo son **obligatorias** según la consigna.

## Patrones aplicados

| Patrón | Dónde se usa | Por qué |
|---|---|---|
| Arquitectura en capas (Router → Service → UoW → Repository → Model) | Todos los módulos | Cada capa sabe lo suyo y nada más |
| Organización por módulo funcional | `app/modules/<módulo>/` | Seis capas iguales por módulo |
| Repository genérico | `app/core/repository.py` — `BaseRepository[T]`, `SoftDeleteRepository[T]` | Reutilizar CRUD; la clase del modelo se pasa al constructor porque los genéricos se borran en runtime (6.4.3) |
| Unit of Work | `app/core/unit_of_work.py` + `app/modules/<m>/unit_of_work.py` | Agrupar las escrituras de una operación en una transacción |
| Soft delete + índice único parcial | `vehiculo`, `repuesto` | Conservar datos y permitir reutilizar patente/código |
| Catálogo (tabla de referencia) + enum en código | `estado_orden` + enum de estados | La base rechaza estados inexistentes por FK; el enum es el contrato de la API (422) |
| Append-only por disparador | `historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto` | La base impone que no se corrigen |
| Punto único de escritura | Stock de repuestos | RN-14: el stock sólo cambia por movimientos |
| DTO / contratos separados | `schemas.py` | `extra="forbid"`, sin `password_hash`, sin precio/total en el alta |
| Dependency Injection (FastAPI `Depends`) | Sesión, UoW, usuario actual, `requiere_rol` | Router construye; servicio usa |
| Dos grupos de rutas | `main.py` | FastAPI suma dependencias y no las resta (5.10) |
| Lifespan para recursos | `main.py` + `app/core/database.py` | Crear recursos con el bucle de eventos ya existente (EA-08) |
| Background task | Terminar orden | Aviso después de la respuesta y sólo si se confirmó |

## Estructura de directorios (obligatoria)

```
taller/
├── main.py                       # Aplicación, lifespan y los dos grupos de rutas
├── seed.py                       # Deja la base en el estado inicial conocido
├── requirements.txt
├── Dockerfile                    # Multi-stage, Python 3.12 slim, usuario no-root (DD-32)
├── docker-compose.yml            # api + db (postgres:16) + base de test; credenciales desde .env
├── .dockerignore
├── env.example                   # Todas las variables, ningún secreto
├── alembic.ini                   # Sin credenciales
├── README.md                     # Pasos para levantar desde cero
├── app/
│   ├── core/
│   │   ├── config.py             # Settings con pydantic-settings
│   │   ├── database.py           # Crear motor y fábrica de sesiones (los llama el lifespan) + get_session
│   │   ├── security.py           # bcrypt fuera del bucle (to_thread + semáforo); emitir/verificar JWT
│   │   ├── dependencies.py       # Usuario actual, roles vigentes, control del cambio obligatorio, requiere_rol
│   │   ├── repository.py         # BaseRepository[T] y SoftDeleteRepository[T]
│   │   ├── paginacion.py         # Envoltorio de listados y cálculo de páginas
│   │   └── unit_of_work.py       # UnitOfWork base: confirma o revierte al salir del bloque
│   └── modules/
│       ├── health/
│       │   └── router.py         # Sólo router
│       ├── usuarios/             # Usuario, AsignacionRol, IntentoAcceso, EventoSeguridad
│       │   ├── models.py
│       │   ├── schemas.py
│       │   ├── repository.py
│       │   ├── unit_of_work.py
│       │   ├── service.py
│       │   └── router.py
│       ├── clientes/             # Cliente, Vehiculo
│       │   └── (mismas 6 capas)
│       ├── repuestos/            # Repuesto, MovimientoStock, HistorialPrecio
│       │   └── (mismas 6 capas)
│       └── ordenes/              # OrdenTrabajo, EstadoOrden, ItemOrden, HistorialEstadoOrden
│           └── (mismas 6 capas)
├── migrations/                   # Alembic (plantilla async) y sus versiones
│   └── versions/
│       ├── xxxx_tablas.py        # 1ª: --autogenerate, todas las tablas
│       └── yyyy_solo_agregado.py # 2ª: a mano, función + disparador
└── test/
    ├── *.http                    # Casos C-01..C-19 con la respuesta esperada en comentarios
    └── solo_agregado.sql         # Caso C-14
```

**Suposición**: los nombres de archivo de migraciones y de los `.http` no están fijados por la consigna.

### Responsabilidad por capa

| Capa | Hace | No hace |
|---|---|---|
| `router.py` | Construye el UoW (dependencia), llama al servicio, traduce errores a HTTP, agenda `BackgroundTasks` | Reglas de negocio, abrir el UoW |
| `service.py` | Reglas de negocio; recibe el UoW y lo abre con `async with` | Construir el UoW, hablar HTTP |
| `unit_of_work.py` | Compone los repositorios del módulo con la misma sesión; commit/rollback | Cerrar la sesión |
| `repository.py` | Consultas, precarga declarada en el método, `flush()` | `commit()` |
| `models.py` | Tablas, restricciones, relaciones (navegación en ambos extremos) | Lógica |
| `schemas.py` | Contratos de entrada (`extra="forbid"`) y salida | Exponer `password_hash` |

### Repositorios

- `BaseRepository[T](session, model)`: `get_by_id`, `get_all`, `count`, `add`, `update`, `delete` (mínimo).
- `SoftDeleteRepository[T](BaseRepository[T])`: filtra `borrado_en IS NULL`; agrega `get_by_id_including_deleted`, `soft_delete`.
- `EstadoOrdenRepository`: **sólo lectura**, **no** hereda de `BaseRepository` (PK `codigo`, no `id`; no debe ofrecer `add`/`update`/`delete`).
- Métodos nombrados por lo que traen (p. ej. `get_detalle_con_items_e_historial`), con `selectinload`/`joinedload` adentro.

## Seguridad

- **Autenticación**: JWT (PyJWT) firmado con clave del entorno; claims `sub`, `iat` (con fracción de segundo), `exp`, roles vigentes al emitir. Transporte **sólo** en cookie `access_token` (`HttpOnly`, `SameSite=Lax`, `Max-Age`, `Secure` configurable). Nunca en el cuerpo ni leído de `Authorization`.
- **Contraseñas**: bcrypt con costo configurable; `asyncio.to_thread` + `asyncio.Semaphore`; máximo 72 bytes en el contrato; hash ficticio calculado una vez en el lifespan.
- **Autorización**: roles vigentes leídos de `asignacion_rol` en cada petición (`requiere_rol`); el token es informativo.
- **Revocación de sesiones**: `iat < password_cambiada_en` (sin truncar) → 401.
- **Fuerza bruta**: 5 fallos / 60 s por (correo, IP) → 429 + `Retry-After`; intentos anotados en transacción propia.
- **Enumeración de cuentas**: misma respuesta y mismo tiempo exista o no el correo.
- **Validación de input**: Pydantic v2 en el contrato; ninguna entrada inválida → 500.
- **SQL**: siempre parámetros ligados; nunca concatenación.
- **Errores**: mensajes propios, sin texto de la base ni trazas (`IntegrityError` traducido).
- **Secrets management**: `.env` no versionado; `env.example` sin secretos; sin defaults para la clave de firma ni la contraseña de la base; `alembic.ini` sin credenciales (la URL sale de `Settings`).

## Variables de entorno

Obligatorias por nombre en la consigna: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`. El resto las fijó el equipo (DD-30).

| Variable | Descripción | Default en código | Ejemplo en `env.example` | Sensible |
|---|---|---|---|---|
| `POSTGRES_USER` | Usuario de la base | `taller` | `taller` | N |
| `POSTGRES_PASSWORD` | Contraseña de la base | **ninguno** | *(vacío)* | **Y** |
| `POSTGRES_DB` | Nombre de la base | `taller` | `taller` | N |
| `POSTGRES_HOST` | Host (`db` dentro de Docker Compose) | `localhost` | `localhost` | N |
| `POSTGRES_PORT` | Puerto | `5432` | `5432` | N |
| `POSTGRES_TEST_DB` | Base real que usa pytest (DD-13) | **ninguno** | `taller_test` | N |
| `JWT_SECRET` | Clave de firma: **fija**, nunca generada al arrancar (DD-20) | **ninguno** | *(vacío; generarla una vez con `python -c "import secrets; print(secrets.token_urlsafe(64))"`)* | **Y** |
| `JWT_ALGORITHM` | Algoritmo de firma | `HS256` | `HS256` | N |
| `ACCESS_TOKEN_EXPIRE_SECONDS` | Duración del token = `Max-Age` | `1800` | `1800` | N |
| `COOKIE_SECURE` | Flag `Secure` de la cookie | `false` | `false` (en producción `true`) | N |
| `BCRYPT_ROUNDS` | Costo de bcrypt | `12` | `12` | N |
| `BCRYPT_MAX_CONCURRENCY` | Tamaño del semáforo de bcrypt | `4` | `4` | N |
| `DB_POOL_SIZE` | Tamaño del pool del motor | `5` | `5` | N |
| `SQL_ECHO` | Mostrar consultas en consola (C-15) | `false` | `false` | N |

## Puesta en marcha (lo que el README debe documentar)

**Con Docker (DD-32, entorno del equipo)**:

1. `cp env.example .env` y completar `POSTGRES_PASSWORD` y `JWT_SECRET`.
2. `docker compose up -d --build` (servicios `api` y `db` con `postgres:16`; crea también la base de test).
3. `docker compose exec api alembic upgrade head`.
4. `docker compose exec api python seed.py`.

**Sin Docker (pasos que exige la consigna)**:

1. Entorno virtual.
2. Dependencias (`requirements.txt`).
3. `.env` a partir de `env.example` (con cómo generar la clave de firma).
4. `alembic upgrade head`.
5. `python seed.py`.
6. Arranque del servidor (uvicorn / `fastapi dev`).
