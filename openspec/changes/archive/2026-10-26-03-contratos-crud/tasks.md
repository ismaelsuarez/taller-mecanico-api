# Tasks

> Ciclo TDD (regla E-2, Strict TDD): en cada grupo con comportamiento, primero el test en rojo, después el código mínimo, después refactor con los tests en verde. Comando de tests: `pytest` (desde la raíz, con el venv activo o `docker compose exec api pytest`).
> Convenciones DD-34: sin `__init__.py` en `test/` ni `test/pytest/`; utilidades con `from conftest import ...`; fixture `configurar_entorno` de EJ-1 se reutiliza; los `.http` llevan la respuesta esperada en comentarios (D-3) y se corren tras `python seed.py`.

## 1. Contratos estrictos (spec `contratos-estrictos`)

- [x] 1.1 RED: tests de contratos en `test/pytest/test_contratos.py`: campos extra en entrada → 422 (`stock` en PATCH, `rol` en registro); PATCH con `exclude_unset` no pisa campos no enviados; ninguna respuesta incluye `password_hash`; `GET /clientes/abc` → 422 sin ejecutar el handler; cuerpo malformado → 422, nunca 500. Verificación: los tests fallan por falta de implementación.
- [x] 1.2 GREEN: implementar `schemas.py` de `clientes` (`ClienteCrear`, `ClienteLectura`, `VehiculoCrear`, `VehiculoLectura`) y `repuestos` (`RepuestoCrear`, `RepuestoActualizar`, `RepuestoReponer`, `RepuestoLectura`) con `extra="forbid"`, tipos correctos (`Decimal`, `datetime`) y sin `password_hash`. Verificación: `pytest test/pytest/test_contratos.py` pasa.

## 2. Paginación (spec `listados-paginados`)

- [x] 2.1 RED: tests en `test/pytest/test_paginacion.py`: envoltorio `{items,total,page,size,pages}`; `size=0`/`101`/`page=0` → 422; página fuera de rango → 422 «La página N no existe: hay M»; cero resultados → 200 con `items: []`, `total: 0`, `pages: 1`; `total` con los mismos filtros; `q=' OR '1'='1` → lista vacía con `total` 0. Verificación: los tests fallan.
- [x] 2.2 GREEN: implementar `app/core/paginacion.py` (`ParametrosPagina`, `Pagina[T]`, helper de 422) y usarlo en `GET /repuestos`. Verificación: `pytest test/pytest/test_paginacion.py` pasa.

## 3. Repositorios y Unit of Work mínimos (T-2, spec `contratos-estrictos`)

- [x] 3.1 RED: tests en `test/pytest/test_repositorios_uow.py`: `add`/`update` hacen `flush()` y no `commit()`; el UoW confirma al salir y revierte con excepción sin cerrar la sesión; `SoftDeleteRepository.get_by_id` no devuelve dados de baja pero `get_by_id_including_deleted` sí; `soft_delete` pone `borrado_en`. Verificación: los tests fallan.
- [x] 3.2 GREEN: implementar `app/core/repository.py` (`BaseRepository[T]`, `SoftDeleteRepository[T]`) y `app/core/unit_of_work.py` (`UnitOfWork`); UoW de `clientes` y `repuestos` en sus módulos; precarga declarada en los métodos que leen relaciones (T-10). Verificación: `pytest test/pytest/test_repositorios_uow.py` pasa.

## 4. Clientes y vehículos (spec `clientes-vehiculos`)

- [x] 4.1 RED: tests en `test/pytest/test_clientes_vehiculos.py`: `POST /clientes` 201/409 (documento)/422; `GET /clientes/{id}` 200 con vehículos vigentes / 404; `POST /clientes/{id}/vehiculos` 201/404/409 (patente vigente)/422; `DELETE /vehiculos/{id}` 204 / 404 (inexistente o ya baja) / 409 (orden abierta, usando `es_final` del catálogo) / 201 al reutilizar patente tras la baja. Verificación: los tests fallan.
- [x] 4.2 GREEN: implementar repositorio, UoW, service y router de `clientes` (incluye vehículos) con las excepciones de dominio traducidas a 404/409/422; montar el router en `main.py` (grupo abierto, T-11). Verificación: `pytest test/pytest/test_clientes_vehiculos.py` pasa.

## 5. Repuestos (spec `catalogo-repuestos`)

- [x] 5.1 RED: tests en `test/pytest/test_repuestos.py`: `GET /repuestos` sólo vigentes + paginación + `q`; `GET /repuestos/{id}` 200/404 (dado de baja); `POST /repuestos` 201 con movimiento «Stock inicial» si `stock_inicial > 0`, sin movimiento con 0, 422 con negativo, 409 con código vigente repetido; `PATCH /repuestos/{id}` con línea de historial si cambia el precio, sin línea si no cambia, 404 si no existe; `DELETE /repuestos/{id}` 204 siempre (aunque en órdenes abiertas), 404 si ya baja; `POST /repuestos/{id}/reponer` 200 con movimiento positivo / 404 / 422 (`cantidad ≤ 0`, `motivo` > 120); `GET /repuestos/{id}/movimientos` y `/precios` 200/404. Verificación: los tests fallan.
- [x] 5.2 GREEN: implementar repositorio, UoW, service y router de `repuestos` con el punto único de escritura de stock (T-3) y el actor temporal (T-4, comentado); montar el router en `main.py`. Verificación: `pytest test/pytest/test_repuestos.py` pasa.

## 6. Entrega `.http` (DoD)

- [x] 6.1 Crear `test/clientes_vehiculos.http` con la parte de 422 de C-01 (parámetro de ruta no entero; la sesión iniciada llega en EJ-4), C-19 (baja de vehículo sin órdenes y reutilización de patente para otro cliente, con la 409 de una segunda patente vigente igual) y los bloques de alta/lectura de clientes y vehículos con las respuestas esperadas en comentarios; correr tras `python seed.py`. Verificación: los bloques se ejecutan y las respuestas coinciden con los comentarios.
- [x] 6.2 Crear `test/repuestos.http` con los casos C-16 (búsqueda, paginación, PATCH parcial, PATCH del stock → 422), C-18 (línea de historial al cambiar el precio) y las respuestas esperadas en comentarios; correr tras `python seed.py`. Verificación: los bloques se ejecutan y las respuestas coinciden con los comentarios.

## 7. Documentación y cierre del relevo

- [x] 7.1 Actualizar `README.md`: endpoints nuevos, rutas **abiertas hasta EJ-5** (T-11), cómo correr los `.http`. Verificación: el README refleja el estado real de la API.
- [x] 7.2 Correr la suite completa y la revisión de secretos. Verificación: con `db` levantada, `pytest -rs` en verde con **0 skipped**; sin credenciales en el código nuevo; migraciones y `seed.py` intactos (`alembic upgrade head` → `downgrade base` → `upgrade head` + `python seed.py` siguen funcionando).
- [x] 7.3 Anotar en `knowledge-base/09_decisiones_y_supuestos.md` las decisiones nuevas (regla D-4) y marcar `[EJ-3]` como `[x]` en `CHANGES.md`. Verificación: las notas y el checkbox están en el diff del commit.

## Workflow follow-up

- `/opsx:archive 03-contratos-crud`
- Commit (Conventional Commits) → `bash scripts/sync-memoria.sh` (Windows: `scripts\sync-memoria.bat`) → `git push` (relevo al compañero del EJ-4).
