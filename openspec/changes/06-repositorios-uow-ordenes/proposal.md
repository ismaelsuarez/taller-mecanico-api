# Proposal

## Why

EJ-1..5 están archivados y publicados: hay autenticación, RBAC por petición y versiones mínimas de repositorios y Unit of Work (T-2), pero el módulo `ordenes` sólo expone `/mis-ordenes`. Falta el Ejercicio 6 (20 pts, el de mayor peso): sin el ciclo de vida de las órdenes no existen el alta con precios copiados, la terminación que descuenta stock en una sola transacción ni el 403 de orden ajena (C-06 queda a medias), y la jerarquía de repositorios/UoW todavía tiene huecos que la corrección mira explícitamente (catálogo de sólo lectura, una consulta SQL dentro de un servicio, rollback de un commit fallido sólo en el UoW de usuarios, punto único de stock sin guarda de insuficiencia).

## What Changes

- **Completar y auditar la jerarquía de repositorios (US-018)**: `BaseRepository[T]` y `SoftDeleteRepository[T]` quedan verificados contra la consigna (clase del modelo en el constructor, `get_by_id_including_deleted` y `soft_delete` sólo en la subclase, `flush()` y nunca `commit()`); un repositorio por entidad de `ordenes` (`OrdenRepository`, `ItemOrdenRepository`, `HistorialEstadoOrdenRepository` de sólo agregado) con métodos nombrados por lo que traen y la precarga declarada adentro (p. ej. `get_detalle_con_items_e_historial`); `EstadoOrdenRepository` de **sólo lectura** que **no** hereda de `BaseRepository`. Las consultas sobre `orden_trabajo` que hoy viven fuera de su repositorio (el dueño del vehículo en el servicio de órdenes y las órdenes abiertas en `VehiculoRepository`) se mueven a `OrdenRepository`.
- **Completar el Unit of Work (US-019)**: el `UnitOfWork` base absorbe el rollback ante un commit fallido que hoy sólo tienen los UoW de `usuarios` (sin cerrar la sesión); `UnitOfWorkOrden` compone con la misma sesión los repositorios de órdenes, catálogo, vehículos y repuestos; se audita que en los cuatro módulos el router construye el UoW con una dependencia y el servicio lo abre con `async with`, y que RN-02, RN-13 y RN-20 están cada una en un solo bloque.
- **Punto único de escritura de stock (RN-14, T-3)**: la terminación reutiliza `RepuestoRepository.registrar_movimiento`, que pasa a rechazar un stock resultante negativo con un conflicto de dominio (409 con mensaje humano) en lugar de dejar que la base responda con un 500.
- **Módulo `ordenes` completo (US-020)**: `POST /ordenes` (RECEPCION, ADMIN; nace `PENDIENTE`, ≥1 ítem sin repetidos → 422, precio copiado, total calculado por el servidor, primera línea de historial; vehículo o repuesto inexistente/dado de baja → 409 sin dejar la orden; catálogo sin `PENDIENTE` → 409 propio); `GET /ordenes` (ADMIN, RECEPCION, MECANICO; filtro `estado` con enum → 422 si no lo declara, paginado); `GET /ordenes/{id}` con vehículo, cliente, ítems, repuesto de cada ítem e historial (personal ve cualquiera — DD-27; el cliente sólo la suya, si no 403 — completa C-06); `POST /ordenes/{id}/iniciar` (MECANICO, `PENDIENTE → EN_REPARACION`, queda asignado); `POST /ordenes/{id}/terminar` (mecánico asignado o ADMIN; descuenta stock, un movimiento por ítem, línea de historial, todo o nada → 409; no cambia `mecanico_id` — DD-31); `POST /ordenes/{id}/cancelar` (sin `requiere_rol`; RECEPCION, ADMIN o dueño; **403 antes que 409**; sólo desde `PENDIENTE`); `GET /estados-orden` (autenticado, por posición).
- **Entregables de prueba**: `test/ordenes.http` con C-06 (completo), C-10, C-11, C-12 (sin aviso), C-13 y C-17; pytest + httpx sobre PostgreSQL real migrada con Alembic en `test/pytest/ordenes/`.
- **Sin aviso en segundo plano** (T-9, llega en EJ-8) y **sin migraciones** (el esquema de EJ-2 ya tiene las cuatro tablas de órdenes, el catálogo y el disparador de sólo agregado).

**Fuera de alcance:** `BackgroundTasks` y la evidencia de consultas fijas C-15 (EJ-8; el detalle sí se precarga ya, T-10), la evidencia `psql` de C-14 y la auditoría de `intento_acceso` (EJ-7), control de concurrencia del stock (DD-08), edición o borrado de órdenes, ítems o catálogo desde la API (A-5, RN-19). Esta propuesta se redactó como planificación; la ejecución y su evidencia quedaron registradas en `odd/tasks/06-repositorios-uow-ordenes.md`.

## Capabilities

### New Capabilities

- `ordenes-trabajo`: alta, listado, detalle y transiciones (iniciar, terminar, cancelar) de las órdenes de trabajo, con sus permisos por rol y por dueño, la atomicidad de la terminación y el historial de estados.
- `estados-orden`: consulta del catálogo de estados por posición y su uso como contrato del filtro de órdenes; el catálogo no se edita desde la API.
- `persistencia-transaccional`: contrato de la jerarquía de repositorios, del Unit of Work (quién crea, abre, confirma, revierte y cierra), de las operaciones de varias escrituras en un solo bloque y del punto único de escritura de stock.

### Modified Capabilities

Ninguna. `catalogo-repuestos` ya exige que el stock cambie sólo por el punto único y que la reposición pase por él; la terminación y la guarda de insuficiencia se especifican en `ordenes-trabajo`/`persistencia-transaccional` sin alterar ningún requisito ni escenario vigente de reposición, alta o movimientos. `clientes-vehiculos` conserva la baja con 409 por órdenes abiertas: sólo cambia el repositorio que hace la consulta. `autorizacion-roles` conserva `/mis-ordenes`; las rutas de órdenes se especifican en `ordenes-trabajo`. Si al aplicar apareciera un cambio observable de una spec vigente, se agregará el delta MODIFIED con decisión explícita.

## Impact

- **Código**: `app/core/{unit_of_work,errores}.py` (`app/core/repository.py` se auditó y quedó sin cambios); `app/modules/ordenes/{schemas,repository,unit_of_work,service,router}.py` (los modelos de EJ-2 no cambian); `app/modules/repuestos/repository.py` (guarda en el punto único); `app/modules/clientes/{repository,service,unit_of_work}.py` (órdenes abiertas vía `OrdenRepository`); `app/modules/usuarios/unit_of_work.py` (se elimina el rollback duplicado al subirlo a la base).
- **Persistencia**: sin migraciones ni cambios en `seed.py`; usa `orden_trabajo`, `item_orden`, `historial_estado_orden`, `movimiento_stock`, `repuesto` y `estado_orden` tal como los creó EJ-2. Las órdenes del seed (1 `PENDIENTE` de Laura, 2 `EN_REPARACION` de Jorge con 4 bujías y stock 2) son la base de C-11/C-12/C-13.
- **Riesgo**: dominio ALTO — transacciones de varias escrituras sobre stock y dinero y una máquina de estados con permisos; los helpers compartidos (`UnitOfWork` base, traductor 422) afectan a los cuatro módulos y exigen regresión completa.
- **Pruebas/documentación**: nuevo `test/ordenes.http`, `test/pytest/ordenes/`, README (rutas de órdenes) y decisiones/supuestos nuevos en `knowledge-base/09_decisiones_y_supuestos.md` (D-4). Sin dependencias ni variables de entorno nuevas.
- **Aceptación**: C-06 completo, C-10, C-11, C-12 (sin aviso), C-13, C-17; ningún `commit()` en repositorios ni servicio que construya su UoW.
- **Fuentes**: `docs/TP_Cap1a6_Consigna.pdf` (Ejercicio 6, tabla de rutas, nota «La ruta de cancelar no lleva requiere_rol», ejemplo de alta), `CHANGES.md` (EJ-6, T-2/T-3/T-8/T-9/T-10), KB 03/05/06/07/08/09/11; DD-02, DD-08, DD-21, DD-27, DD-28, DD-29, DD-31, DD-38, DD-40, DD-41, SU-03, SU-06..SU-08.
