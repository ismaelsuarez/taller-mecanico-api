# Design

## Context

EJ-2 dejó los 13 modelos con sus restricciones, las dos migraciones y el seed. La API expone sólo `/health/*`: no hay contratos, ni paginación, ni CRUD. `app/core/` tiene `config`, `database`, `security` (sólo `hashear_password` de EJ-1), `dependencies` (placeholder) y `paginacion`/`repository`/`unit_of_work` (placeholders con docstring que apuntan a este change). Los `schemas.py`, `service.py`, `router.py` y `repository.py` de `clientes` y `repuestos` están vacíos. No hay login (EJ-4), ni roles en las rutas (EJ-5), ni el módulo `ordenes` (EJ-6) — pero `DELETE /vehiculos/{id}` necesita saber si el vehículo tiene órdenes abiertas.

## Goals / Non-Goals

**Goals:**
- Contratos estrictos (`extra="forbid"`), separados de los modelos, sin `password_hash` en ninguna respuesta.
- Envoltorio de paginación reutilizable con la validación de RT-PG-05.
- Versión mínima pero conforme de `BaseRepository`/`SoftDeleteRepository` y `UnitOfWork` (T-2), con `flush()` y nunca `commit()` desde el primer día.
- CRUD completo de clientes, vehículos y repuestos con las reglas de negocio RN-01, RN-14, RN-16, RN-20 y los DD-21..DD-23, DD-25, DD-29.
- Punto único de escritura de stock (T-3) y actor temporal comentado (T-4).
- Tests pytest contra la base real + `.http` de entrega con respuestas esperadas.

**Non-Goals:**
- Autenticación y autorización (EJ-4/EJ-5): las rutas quedan abiertas; `requiere_rol` no existe todavía.
- Módulo `ordenes` completo (EJ-6): sólo la consulta mínima de órdenes abiertas para el 409 de `DELETE /vehiculos/{id}`.
- `GET /mis-vehiculos` (EJ-5), terminar órdenes (EJ-6), conteo fijo de consultas (EJ-8).

## Decisions

- **D1 — Contratos en `schemas.py`, modelos en `models.py`.** Entrada (`*Crear`, `*Actualizar`, `*Reponer`) con `extra="forbid"`; salida (`*Lectura`, `*Detalle`) sin `password_hash`. Los `Decimal` se declaran como `Decimal` (nunca `float`) y las fechas como `datetime` con zona. Los `id` de salida son `int`; el `precio` del repuesto en salida es `Decimal`.
- **D2 — `paginacion.py` como helper puro.** `ParametrosPagina` (query params `page`/`size` con validación) + `Pagina[T]` (envoltorio) + `pagina_o_422(items, total, page, size)` que lanza el error 422 con el mensaje «La página N no existe: hay M» cuando `page > pages`. El router arma la consulta con offset/limit y llama al helper; el `total` sale del mismo filtro.
- **D3 — Repositorio genérico con la clase del modelo en el constructor** (los genéricos se borran en runtime, 6.4.3). `BaseRepository[T]`: `get_by_id`, `get_all`, `count`, `add`, `update`, `delete`, todos con `flush()` y jamás `commit()` (RT-TX-01). `SoftDeleteRepository[T]`: filtra `borrado_en IS NULL` en `get_by_id`/`get_all`/`count` y agrega `get_by_id_including_deleted` y `soft_delete`. Métodos con precarga declarada adentro (T-10): `get_by_id_con_vehiculos` usa `selectinload(Cliente.vehiculos)`.
- **D4 — UoW base + uno por módulo.** `UnitOfWork` en `core/unit_of_work.py`: gestor de contexto asincrónico que recibe la sesión, hace `commit` al salir y `rollback` si sale con excepción, y **no cierra la sesión** (RT-TX-03). El router lo construye con una dependencia (`Depends` sobre la sesión) y lo pasa sin abrir; el servicio lo abre con `async with` (RT-TX-02, B-2). `UnitOfWorkCliente` compone `clientes` + `vehiculos`; `UnitOfWorkRepuesto` compone `repuestos` + `movimientos` + `precios`.
- **D5 — Punto único de escritura de stock (T-3).** Un método `registrar_movimiento(repuesto, cantidad, motivo, orden_id, usuario_id)` en el repositorio de repuestos (o en el servicio `repuestos`) que hace `stock += cantidad`, inserta el movimiento y hace `flush()`; lo usan alta con `stock_inicial` y `/reponer`. El EJ-6 lo reutiliza para terminar órdenes. RN-14: nada más toca `repuesto.stock`.
- **D6 — Actor temporal (T-4).** Dependencia `actor_temporal` en `core/dependencies.py` que devuelve el usuario admin sembrado (`admin@example.com`) con un comentario que declara que es temporal hasta EJ-5. `movimiento_stock.usuario_id` y `historial_precio_repuesto.usuario_id` son NOT NULL, así que sin login no hay otra opción. El EJ-5 la reemplaza por `get_usuario_actual`.
- **D7 — Órdenes abiertas para el 409 del vehículo.** Como el módulo `ordenes` llega en EJ-6, el 409 de `DELETE /vehiculos/{id}` consulta `orden_trabajo` con un `exists()` sobre los estados no finales (JOIN a `estado_orden.es_final = false`) desde el repositorio de vehículos, en una sola consulta. Cuando exista el repositorio de órdenes (EJ-6), se reemplaza por él sin cambiar el contrato.
- **D8 — Errores: excepciones de dominio traducidas en el router.** Los servicios lanzan excepciones propias (`NoEncontrado`, `EnConflicto`, `Validacion`) con mensaje en español; el router las traduce a 404/409/422. `IntegrityError` se captura en el servicio (o UoW) al confirmar y se traduce a 409/422 con mensaje propio, nunca texto de la base (RN-18, S-9).
- **D9 — Rutas abiertas hasta EJ-5 (T-11).** Los routers de `clientes` y `repuestos` se montan en `main.py` dentro del grupo **abierto** (junto a `/health`), con un comentario que dice que el EJ-5 los mueve al grupo protegido y agrega `requiere_rol`. El README lo documenta.

## Risks / Trade-offs

- **Consulta de órdenes abiertas fuera del módulo ordenes (D7)**: duplicará lógica cuando EJ-6 traiga el repositorio; se compensa dejando el `exists()` en un solo método con comentario apuntando al EJ-6.
- **Actor temporal (D6)**: hasta EJ-5, cualquier movimiento o cambio de precio queda firmado por el admin sembrado; es explícito en el código y en el README para que nadie lo confunda con un bug.
- **Rutas abiertas (D9)**: sin `requiere_rol` cualquiera puede crear clientes o repuestos; es el alcance acordado (T-11) y debe constar en el README.
- **Sin `ordenes` completo**: el 409 del vehículo depende de `es_final` del catálogo; si el catálogo estuviera vacío (no pasa con el seed) el comportamiento sería conservador (sin órdenes abiertas → permitir la baja).
