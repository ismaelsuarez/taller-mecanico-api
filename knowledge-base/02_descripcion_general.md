# Descripción General

## Stack tecnológico (obligatorio)

| Componente | Versión mínima | Uso |
|---|---|---|
| Python | 3.12 | Lenguaje |
| FastAPI | 0.111 | Framework web; **todos los handlers con `async def`** |
| SQLModel | 0.0.24 | Modelos de tabla |
| SQLAlchemy | 2.0, asincrónico | Motor, sesión y carga anticipada |
| asyncpg | 0.30 | Controlador asincrónico de PostgreSQL (se acepta psycopg 3 asincrónico, el del capítulo 4) |
| PostgreSQL | 16 | Base de datos |
| Alembic | 1.13, plantilla asincrónica | Migraciones |
| pydantic-settings | 2.0 | Configuración leída del entorno |
| bcrypt | 4.0 | Hash de las contraseñas |
| PyJWT | 2.8 | Token firmado |
| uvicorn | El que instala `fastapi[standard]` | Servidor ASGI |
| Docker / Docker Compose | — | Entorno del equipo: `api` + `db` (`postgres:16`) — decisión del equipo (DD-32), no exigido por la consigna |

## Arquitectura general

API monolítica, asincrónica, organizada **por módulo funcional**, con las mismas seis capas en todos los módulos:

```
HTTP ──► Router ──► Service ──► Unit of Work ──► Repository ──► Model (SQLModel) ──► PostgreSQL
          │           │             │                 │
          │           │             │                 └─ flush(), nunca commit(); precarga declarada en el método
          │           │             └─ async context manager: commit al salir, rollback si hay excepción, NO cierra la sesión
          │           └─ reglas de negocio; recibe el UoW y lo abre con `async with`; NUNCA lo construye
          └─ construye el UoW con una dependencia, llama al servicio y traduce errores a HTTP
```

- **Módulos mínimos**: `health`, `usuarios`, `clientes`, `repuestos`, `ordenes`.
- **Dos grupos de rutas** en `main.py`: uno **abierto** (`/health/*`, `/auth/*`) y uno **protegido**, que lleva montado una sola vez el control del cambio obligatorio de contraseña (FastAPI suma dependencias y no las resta — sección 5.10).
- **Recursos en el lifespan**: el motor asincrónico (con tamaño de pool en la configuración) y la fábrica de sesiones se crean en el `lifespan` y se guardan en `app.state`; nunca al importar un módulo (EA-08, sección 1.9). El lifespan también calcula **una vez** el hash ficticio del login y al apagar hace `engine.dispose()`.
- **Sesión por petición**: `get_session` toma la fábrica de `app.state`, crea la sesión con `expire_on_commit=False` y la cierra al terminar.
- **Garantías en la base**: unicidad, FKs, CHECKs, índices únicos parciales y disparador de sólo agregado.

### Configuración

- Clase `Settings` de pydantic-settings, leída del entorno o de un `.env` **no versionado**.
- URL de la base armada con un `@computed_field` a partir de `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`, con driver asincrónico (`postgresql+asyncpg` o `postgresql+psycopg`).
- La clave de firma de tokens y la contraseña de la base **no tienen valor por defecto en el código**: si faltan, la app no arranca. Tampoco sirve una clave inventada al arrancar (cambia en cada reinicio y dos procesos rechazarían los tokens del otro).
- El repo incluye `env.example` con todas las variables y ningún secreto.

Variables completas: [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md#variables-de-entorno).

## Integraciones externas

| Servicio | Propósito | Tipo |
|---|---|---|
| PostgreSQL 16 | Persistencia, unicidad, FKs, CHECKs, disparador | Driver asincrónico (asyncpg / psycopg 3) |
| Aviso al cliente (simulado) | Notificar que la orden terminó | `BackgroundTasks` en proceso: `await asyncio.sleep(0.5)` + mensaje en el log |

No hay pasarelas, colas, caché ni servicios externos.

## API REST — Endpoints de referencia

Toda ruta del grupo **protegido** responde además **401 sin sesión** y **403 con el cambio de contraseña pendiente**.

### Grupo abierto

| Método | Ruta | Quién | Códigos |
|---|---|---|---|
| GET | `/health/live` | Cualquiera | 200 |
| GET | `/health/ready` | Cualquiera | 200, 503 |
| POST | `/auth/registro` | Cualquiera | 201, 409, 422 |
| POST | `/auth/login` | Cualquiera | 200, 401, 422, 429 |
| POST | `/auth/logout` | Cualquiera | 200 |
| GET | `/auth/yo` | Autenticado | 200, 401 |
| POST | `/auth/cambiar-password` | Autenticado | 200, 401, 422 |

### Grupo protegido — usuarios (ADMIN)

| Método | Ruta | Quién | Códigos |
|---|---|---|---|
| POST | `/usuarios` (alta de personal, con contraseña provisoria) | ADMIN | 201, 409, 422 |
| GET | `/usuarios/{id}/roles` | ADMIN | 200, 404 |
| POST | `/usuarios/{id}/roles` | ADMIN | 201, 404, 409, 422 |
| DELETE | `/usuarios/{id}/roles/{rol}` | ADMIN | 200, 404, 409 |
| GET | `/eventos` (`page`, `size`) | ADMIN | 200, 422 |

### Grupo protegido — clientes y vehículos

| Método | Ruta | Quién | Códigos |
|---|---|---|---|
| POST | `/clientes` | RECEPCION, ADMIN | 201, 409, 422 |
| GET | `/clientes/{id}` (con sus vehículos) | RECEPCION, ADMIN | 200, 404 |
| POST | `/clientes/{id}/vehiculos` | RECEPCION, ADMIN | 201, 404, 409, 422 |
| DELETE | `/vehiculos/{id}` | RECEPCION, ADMIN | 204, 404, 409 |
| GET | `/mis-vehiculos` | Autenticado | 200 |

### Grupo protegido — repuestos

| Método | Ruta | Quién | Códigos |
|---|---|---|---|
| GET | `/repuestos` (`q`, `page`, `size`) | ADMIN, RECEPCION, MECANICO | 200, 422 |
| GET | `/repuestos/{id}` | ADMIN, RECEPCION, MECANICO | 200, 404 |
| POST | `/repuestos` (con `stock_inicial`) | ADMIN | 201, 409, 422 |
| PATCH | `/repuestos/{id}` (descripción y precio) | ADMIN | 200, 404, 422 |
| DELETE | `/repuestos/{id}` | ADMIN | 204, 404 |
| POST | `/repuestos/{id}/reponer` | ADMIN | 200, 404, 422 |
| GET | `/repuestos/{id}/movimientos` | ADMIN | 200, 404 |
| GET | `/repuestos/{id}/precios` (historial de precios) | ADMIN | 200, 404 |

### Grupo protegido — órdenes

| Método | Ruta | Quién | Códigos |
|---|---|---|---|
| POST | `/ordenes` | RECEPCION, ADMIN | 201, 409, 422 |
| GET | `/ordenes` (`estado`, `page`, `size`) | ADMIN, RECEPCION, MECANICO | 200, 422 |
| GET | `/ordenes/{id}` | El personal, o el dueño del vehículo | 200, 403, 404 |
| POST | `/ordenes/{id}/iniciar` | MECANICO | 200, 404, 409 |
| POST | `/ordenes/{id}/terminar` | El mecánico asignado, o ADMIN | 200, 403, 404, 409 |
| POST | `/ordenes/{id}/cancelar` | RECEPCION, ADMIN o el dueño | 200, 403, 404, 409 |
| GET | `/estados-orden` (el catálogo, por posición) | Autenticado | 200 |
| GET | `/mis-ordenes` (`page`, `size`) | Autenticado | 200, 422 |

> **La ruta de cancelar NO lleva `requiere_rol`**: el dueño de un vehículo puede cancelar su orden y no tiene rol de personal. La decisión la toma el servicio: primero quién es y qué relación tiene con la orden (403), y recién después si el estado permite cancelarla (409).

### Convenciones de respuesta

- **201** al crear, **204** al dar de baja, **404** si el recurso de la ruta no existe, **409** si choca con lo guardado, **422** si el cuerpo o los parámetros no cumplen el contrato.
- Listados con el envoltorio de la sección 2.9: `{items, total, page, size, pages}` — ver [05](05_reglas_de_negocio.md#dominio-contratos-y-paginación-rn-pg) y ejemplos en [07](07_flujos_principales.md).
- Ninguna respuesta incluye `password_hash`. Ningún error devuelve texto interno de la base ni una traza.
