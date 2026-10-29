# Modelo de Datos

> **Los nombres de tablas y columnas son obligatorios**: los casos de prueba y la corrección los usan. Se pueden agregar columnas, pero **no quitar ni renombrar** las indicadas.

Reglas transversales:
- Todas las fechas son **`timestamptz`**.
- El dinero es **`NUMERIC`** y en Python **`Decimal`**, nunca `float` (sección 2.7).
- **Cada clave foránea lleva un índice**, porque PostgreSQL no lo crea solo (sección 4.10).
- El esquema se crea **sólo con Alembic** (nunca `create_all`).

## Dominios (módulo → entidades)

| Módulo | Entidades |
|---|---|
| `usuarios` | `Usuario`, `AsignacionRol`, `IntentoAcceso`, `EventoSeguridad` |
| `clientes` | `Cliente`, `Vehiculo` |
| `repuestos` | `Repuesto`, `MovimientoStock`, `HistorialPrecio` (tabla `historial_precio_repuesto`) |
| `ordenes` | `OrdenTrabajo`, `EstadoOrden`, `ItemOrden`, `HistorialEstadoOrden` |
| `health` | (sin modelos, sólo `router.py`) |

## ERD (según Figura 1 de la consigna)

```
                       ┌──────────────┐ 0..1      1 a 1      0..1 ┌──────────────┐ 1   roles   0..* ┌────────────────┐
                       │   Cliente    │──────────────────────────│   Usuario    │──────────────────│ AsignacionRol  │
                       └──────────────┘                          └──────────────┘                  └────────────────┘
                          1 │                                       1 │ ▲ 0..1 (mecánico)
                     0..*   │ asociación                              │ │
                       ┌──────────────┐                               │ │
                       │   Vehiculo   │                               │ │
                       └──────────────┘                               │ │
                          1 │ asociación                              │ │
                     0..*   │                                         │ │
 «catalog»  1   catálogo  ┌─┴────────────┐ 0..*                        │ │
┌────────────┐◄───────────│ OrdenTrabajo │─────────────────────────────┘─┘
│ EstadoOrden│      0..*  └──────────────┘
└────────────┘             1 ◆        1 ◆
                composición │          │ composición
                       1..* │          │ 1..*
                ┌───────────┴┐   ┌─────┴──────────────────┐
                │ ItemOrden  │   │ «appendOnly»            │
                └────────────┘   │ HistorialEstadoOrden    │
                    0..* │       └─────────────────────────┘
                         │ asociación
                       1 ▼
                   ┌────────────┐ 1      0..* ┌─────────────────┐
                   │  Repuesto  │◄────────────│ «appendOnly»    │
                   └────────────┘             │ MovimientoStock │
                       1 ▲                    └─────────────────┘
                         │ 0..*
                   ┌─────┴───────────┐
                   │ «appendOnly»    │
                   │ HistorialPrecio │
                   └─────────────────┘

IntentoAcceso y EventoSeguridad no se relacionan con ninguna otra tabla.
```

Relaciones clave:
- **Composición** `OrdenTrabajo ◆─ ItemOrden` (1..*): la orden nace con sus ítems; un ítem no existe sin su orden.
- **Composición** `OrdenTrabajo ◆─ HistorialEstadoOrden` (1..*).
- **Uno a uno opcional** `Cliente ─ Usuario`: `cliente.usuario_id` UNIQUE y nulo permitido. `Usuario.cliente` devuelve **un objeto, no una lista**.
- **Catálogo** `OrdenTrabajo ─► EstadoOrden` vía FK `orden_trabajo.estado → estado_orden.codigo`.
- **Asociación** `OrdenTrabajo ─► Usuario` (mecánico, 0..1) vía `mecanico_id`.
- Declarar la **navegación en los dos extremos** de cada relación que se lea.

## Entidades

### usuario
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `email` | str | **UNIQUE** |
| `nombre` | str | |
| `password_hash` | str | Nunca en una respuesta |
| `activo` | bool | Inactivo → 401 |
| `debe_cambiar_password` | bool | Pendiente → 403 en rutas protegidas (RN-06) |
| `password_cambiada_en` | timestamptz, **nulo permitido** | Se compara con `iat` sin truncar (RN-07) |

Relaciones: `roles` (1→0..* `asignacion_rol`), `cliente` (1→0..1 `cliente`, objeto).

### asignacion_rol
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `usuario_id` | FK → `usuario.id` | indexada |
| `rol` | str | **CHECK** `rol IN ('ADMIN','RECEPCION','MECANICO','CLIENTE')` |
| `desde` | timestamptz | |
| `vence_en` | timestamptz, nulo | Con zona y en el futuro al asignar (si no, 422) |
| `revocada_en` | timestamptz, nulo | Revocar = escribir esta columna; nunca DELETE |
| `otorgada_por` | nulo | **Suposición**: FK → `usuario.id` (no aparece en la Figura 1) |

Constraints: **índice único parcial `(usuario_id, rol) WHERE revocada_en IS NULL`** (`postgresql_where`).

### intento_acceso
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `cuando` | timestamptz | |
| `email` | str | |
| `ip` | str | |
| `exito` | bool | |

Índice: **`(email, ip, cuando)`**. Se escribe desde una **sesión y transacción propias** (ver RN-08 y Ej. 7).

### evento_seguridad
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `cuando` | timestamptz | |
| `actor` | **texto** | Correo/identificador del usuario o `SISTEMA` |
| `accion` | str | |

Sin restricciones extra. Registra altas, cambios de rol, cambios de contraseña, el bloqueo por demasiados intentos de login (429; actor: el correo intentado, DD-26) y los datos iniciales (actor `SISTEMA`).

### cliente
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `usuario_id` | FK → `usuario.id`, **nulo permitido** | **UNIQUE** |
| `nombre` | str | |
| `documento` | str | **UNIQUE** |
| `telefono` | str | |

Relaciones: `usuario` (0..1), `vehiculos` (0..*).

### vehiculo
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `cliente_id` | FK → `cliente.id` | indexada |
| `patente` | str | |
| `marca` | str | |
| `modelo` | str | |
| `anio` | int | **CHECK `anio BETWEEN 1950 AND 2100`** |
| `borrado_en` | timestamptz, nulo | Borrado lógico |

Constraints: **índice único parcial `(patente) WHERE borrado_en IS NULL`**.

### repuesto
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `codigo` | str | |
| `descripcion` | str | |
| `precio` | **NUMERIC(10,2)** | **CHECK `precio > 0`** |
| `stock` | int | **CHECK `stock >= 0`**; sólo cambia por movimientos (RN-14) |
| `borrado_en` | timestamptz, nulo | Borrado lógico |

Constraints: **índice único parcial `(codigo) WHERE borrado_en IS NULL`**.

### estado_orden «catalog»
| Columna | Tipo | Notas |
|---|---|---|
| `codigo` | str **PK** | No hay `id`: así `orden_trabajo.estado` se lee igual en psql que en la API |
| `descripcion` | str | |
| `posicion` | int | **UNIQUE** |
| `es_final` | bool | Decide qué es una orden abierta |

La migración crea la tabla **vacía**; las filas las carga `seed.py`. Repositorio propio **de sólo lectura** que **no hereda** de `BaseRepository`.

### orden_trabajo
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `vehiculo_id` | FK → `vehiculo.id` | indexada |
| `mecanico_id` | FK → `usuario.id`, nulo | Se asigna al iniciar |
| `estado` | str FK → `estado_orden.codigo` | **No es un CHECK con la lista** (RN-19) |
| `falla` | str | |
| `creada_en` | timestamptz | |
| `total` | **NUMERIC(12,2)** | **CHECK `total >= 0`**; lo calcula el servidor |

### item_orden
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `orden_id` | FK → `orden_trabajo.id` | indexada |
| `repuesto_id` | FK → `repuesto.id` | indexada |
| `cantidad` | int | **CHECK `cantidad > 0`** |
| `precio_unitario` | **NUMERIC(10,2)** | **CHECK `precio_unitario > 0`**; copiado del repuesto |

Constraints: **UNIQUE `(orden_id, repuesto_id)`**.

### historial_estado_orden «appendOnly»
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `orden_id` | FK → `orden_trabajo.id` | |
| `desde_estado` | str FK → `estado_orden.codigo`, **nulo** | Nulo en la primera línea (alta) |
| `hasta_estado` | str FK → `estado_orden.codigo` | |
| `usuario_id` | FK → `usuario.id` (**Suposición**) | |
| `cuando` | timestamptz | |

Sólo agregado (disparador).

### movimiento_stock «appendOnly»
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `repuesto_id` | FK → `repuesto.id` | |
| `orden_id` | FK → `orden_trabajo.id`, **nulo** | Con valor en las salidas por orden |
| `usuario_id` | FK → `usuario.id` (**Suposición**) | |
| `cantidad` | int | **CHECK `cantidad <> 0`** |
| `motivo` | str | p. ej. «Stock inicial» |
| `cuando` | timestamptz | |

Sólo agregado (disparador).

### historial_precio_repuesto «appendOnly» (clase `HistorialPrecio`)
| Columna | Tipo | Notas |
|---|---|---|
| `id` | int PK | |
| `repuesto_id` | FK → `repuesto.id` | |
| `usuario_id` | FK → `usuario.id` (**Suposición**) | |
| `precio_anterior` | **NUMERIC(10,2)** | |
| `precio_nuevo` | **NUMERIC(10,2)** | **CHECK `precio_nuevo > 0`**; **CHECK `precio_nuevo <> precio_anterior`** |
| `cuando` | timestamptz | |

Sólo agregado (disparador).

## Índices únicos parciales (exactamente tres, con `postgresql_where`)

| Tabla | Columnas | Condición |
|---|---|---|
| `asignacion_rol` | `(usuario_id, rol)` | `WHERE revocada_en IS NULL` |
| `vehiculo` | `(patente)` | `WHERE borrado_en IS NULL` |
| `repuesto` | `(codigo)` | `WHERE borrado_en IS NULL` |

> Con un UNIQUE común, el comprador de un auto vendido no podría registrarlo y la base respondería «ya existe» de un vehículo que la aplicación no muestra en ningún listado.

## Migraciones

1. **Migración 1** — generada con `--autogenerate`, con **todas las tablas**.
2. **Migración 2** — **escrita a mano**: función + disparador de sólo agregado sobre `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto` (rechaza todo `UPDATE` y `DELETE`, venga de donde venga). La comparación automática no ve funciones ni disparadores.

- Cada migración se lee antes de aplicarla y **lleva un comentario que lo diga**.
- `alembic upgrade head` sobre base vacía → `alembic downgrade base` → `upgrade head` deben funcionar.
- Plantilla **asincrónica** de Alembic.
- Las migraciones crean el catálogo **vacío**.

## Seed data inicial (`seed.py`)

`seed.py` **vacía las tablas** y carga como mínimo lo siguiente (las contraseñas son de mentira y viven sólo en ese archivo). Es parte de la puesta en marcha, no un extra. **El catálogo se carga primero.**

| Qué | Datos |
|---|---|
| Catálogo de estados | `PENDIENTE` (posición 1), `EN_REPARACION` (2), `TERMINADA` (3, final), `CANCELADA` (4, final), cada uno con su descripción |
| Usuarios | `admin@example.com`, `admin2@example.com` (ADMIN); `recepcion@example.com` (RECEPCION); `mecanico@example.com`, `mecanico2@example.com` (MECANICO); `cliente@example.com` (CLIENTE); `nuevo@example.com` (MECANICO, con cambio de contraseña obligatorio) |
| Clientes | Laura, con usuario (`cliente@example.com`) y dos vehículos; Jorge, sin usuario, con un vehículo |
| Repuestos | Filtro de aceite (stock 10), pastillas de freno (4), bujía (2), aceite por litro (20); cada stock cargado como un movimiento «Stock inicial» |
| Órdenes | La 1, `PENDIENTE`, del primer vehículo de Laura; la 2, `EN_REPARACION`, del vehículo de Jorge, asignada a `mecanico@example.com`, con **4 bujías cuando hay 2** |
| Historial de precios | Una línea del filtro de aceite: de 8000 a 8500 |
| Historial de seguridad | Una línea con el actor `SISTEMA`: «Carga de los datos iniciales» |

Datos que surgen de los ejemplos de respuesta de la consigna (útiles para que coincidan los casos de prueba):

| Repuesto | `id` | `codigo` | `precio` | `stock` |
|---|---|---|---|---|
| Filtro de aceite | 1 | `FIL-001` | 8500.00 | 10 |
| Pastillas de freno delanteras | 2 | `FRE-010` | 32000.00 | 4 |
| Bujía de encendido | 3 | `BUJ-014` *(DD-16)* | 6500.00 *(DD-16)* | 2 |
| Aceite 5W30 por litro | 4 | `ACE-530` | 12000.00 | 20 |

- El vehículo `id = 2`, patente `AC456EF`, es de «Laura Cliente».
- En el ejemplo, `usuario_id: 3` crea una orden → coherente con `recepcion@example.com` como tercer usuario.

Decisiones del equipo para completar el seed (ver [09](09_decisiones_y_supuestos.md)):

| Dato | Valor | Decisión |
|---|---|---|
| Orden 1 | `PENDIENTE`, primer vehículo de Laura, «Cambio de aceite y filtro»; 1 × Filtro de aceite (8500.00) + 4 × Aceite 5W30 (12000.00); total **56500.00** | DD-15 |
| Orden 2 | `EN_REPARACION`, vehículo de Jorge, «Falla de encendido», `mecanico_id` = mecanico@; 4 × Bujía (6500.00); total **26000.00** | DD-16 |
| `usuario_id` de movimientos «Stock inicial» y del historial de precio del filtro | `admin@example.com` | DD-14 |
| Historial de estados | Órdenes 1 y 2: `null → PENDIENTE` por `recepcion@example.com`; orden 2: `PENDIENTE → EN_REPARACION` por `mecanico@example.com` | DD-14 |
