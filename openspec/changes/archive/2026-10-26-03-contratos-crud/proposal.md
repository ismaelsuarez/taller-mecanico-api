# Proposal

## Why

Es el tercer relevo del equipo ([EJ-3] en `CHANGES.md`, Ejercicio 3 de la consigna, 10 pts). EJ-2 dejó el esquema completo con sus restricciones y el seed, pero la API sigue exponiendo sólo `/health/*`: no hay contratos, no hay paginación, no hay CRUD de clientes, vehículos ni repuestos. Los ejercicios siguientes (autenticación, autorización, órdenes, integridad, rendimiento) se construyen sobre estos contratos y sobre la versión mínima pero conforme de repositorios y Unit of Work que este change introduce (T-2). Governance MEDIO: lógica de negocio con transacciones (precio + historial, stock por movimientos); sin autenticación todavía, así que las rutas quedan abiertas hasta EJ-5 y esto debe constar en el README.

## What Changes

- **Contratos** (`schemas.py` por módulo): entrada separada de los modelos de tabla, `extra="forbid"` (nadie edita el stock por PATCH → 422), salida sin `password_hash`, PATCH con `exclude_unset` (RT-PG-01..03). Ninguna entrada inválida termina en 500 (RN-18); `IntegrityError` traducido a 409/422 con mensaje propio en español (S-9, RT-EQ-01).
- **Paginación** (`app/core/paginacion.py`): envoltorio `{items, total, page, size, pages}`; `page ≥ 1`, `size` 1..100 (def. 20); página fuera de rango → 422 «La página N no existe: hay M»; cero resultados → una página vacía; `total` con los mismos filtros (RT-PG-05).
- **Repositorios y UoW mínimos** (T-2): `app/core/repository.py` con `BaseRepository[T]` (`get_by_id`, `get_all`, `count`, `add`, `update`, `delete`; `flush()` y nunca `commit()`) y `SoftDeleteRepository[T]` (filtra `borrado_en IS NULL`, agrega `get_by_id_including_deleted` y `soft_delete`); `app/core/unit_of_work.py` (commit al salir, rollback con excepción, no cierra la sesión); UoW de `clientes` y `repuestos`; precarga declarada dentro del método desde el primer día (T-10).
- **Clientes y vehículos**: `POST /clientes` (201/409/422), `GET /clientes/{id}` con sus vehículos (200/404), `POST /clientes/{id}/vehiculos` (201/404/409/422; patente duplicada entre vigentes → 409), `DELETE /vehiculos/{id}` (borrado lógico 204; con órdenes abiertas → 409 usando `es_final` del catálogo; ya dado de baja → 404, DD-22).
- **Repuestos**: `GET /repuestos?q=&page=&size=` (búsqueda «contiene» con parámetros ligados, excluye dados de baja), `GET /repuestos/{id}`, `POST /repuestos` con `stock_inicial ≥ 0` (default 0; movimiento «Stock inicial» sólo si es > 0; DD-23), `PATCH /repuestos/{id}` (sólo descripción y precio; cambio de precio deja línea en `historial_precio_repuesto` en la misma transacción — RN-20; precio igual → sin línea), `DELETE /repuestos/{id}` siempre 204 (204 aunque esté en órdenes abiertas — DD-21; ya dado de baja → 404 — DD-22), `POST /repuestos/{id}/reponer` con `{cantidad > 0, motivo? ≤120}` (default «Reposición» — DD-29), `GET /repuestos/{id}/movimientos`, `GET /repuestos/{id}/precios`.
- **Punto único de escritura de stock** (T-3): una única función en el módulo `repuestos` (movimiento + actualización de `stock`) que usan alta y reposición; el EJ-6 la reutiliza para terminar órdenes.
- **Actor temporal** (T-4): hasta EJ-5 no existe login; `movimiento_stock` e `historial_precio_repuesto` exigen `usuario_id` no nulo, así que las rutas usan una dependencia temporal `actor_temporal` que devuelve el admin sembrado, comentada como tal. El EJ-5 la reemplaza por `get_usuario_actual` y agrega `requiere_rol`.
- **Rutas sin protección hasta EJ-5**: los endpoints de este change quedan abiertos (EJ-5 agrega autorización); debe constar en el README (T-11: los routers se montan en `main.py` de forma que el EJ-5 sólo los mueva al grupo protegido).
- **Tests**: `test/clientes_vehiculos.http` y `test/repuestos.http` con la respuesta esperada en comentarios (D-3), más la suite pytest de contratos, paginación y comportamiento contra la base real.

## Capabilities

### New Capabilities

- `contratos-estrictos`: contratos de entrada con `extra="forbid"` separados de los modelos, salidas sin `password_hash`, PATCH con `exclude_unset`, códigos 201/204/404/409/422 según la convención y ninguna entrada inválida termina en 500.
- `listados-paginados`: envoltorio `{items, total, page, size, pages}` con validación de página y tamaño, total con los mismos filtros y búsqueda con parámetros ligados.
- `clientes-vehiculos`: alta y lectura de clientes con sus vehículos, alta de vehículos con patente única entre vigentes y borrado lógico de vehículos con control de órdenes abiertas.
- `catalogo-repuestos`: listado y detalle de repuestos, alta con stock inicial, cambio de precio con historial en la misma transacción, borrado lógico, reposición de stock y consultas de movimientos y precios.

### Modified Capabilities

<!-- Ninguno: los specs existentes (configuracion-aplicacion, salud-servicio, modelo-datos, migraciones-esquema, datos-iniciales) no cambian de requisito. -->

## Impact

- **Código nuevo**: `app/core/paginacion.py`, `app/core/repository.py`, `app/core/unit_of_work.py`; contenido de `app/modules/clientes/{schemas,repository,unit_of_work,service,router}.py` y `app/modules/repuestos/{schemas,repository,unit_of_work,service,router}.py`.
- **`main.py`**: monta los routers de clientes y repuestos en el grupo abierto (T-11; el EJ-5 los mueve al protegido).
- **Dependencias**: ninguna nueva (FastAPI, SQLModel, SQLAlchemy async, httpx ya están).
- **Documentación**: `README.md` (endpoints nuevos, rutas abiertas hasta EJ-5, pasos de puesta en marcha con `.http`), `env.example` sin cambios.
- **Tests**: `test/pytest/` (contratos, paginación, CRUD contra la base real) y `test/clientes_vehiculos.http`, `test/repuestos.http` con respuestas esperadas.
- **Sin cambios de esquema**: migraciones y `seed.py` intactos (DoD lo exige).
