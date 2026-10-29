# Tasks

Plan de ejecución de `/opsx:apply 06-repositorios-uow-ordenes`. Las casillas se marcan sólo con evidencia observada y registrada en `odd/tasks/06-repositorios-uow-ordenes.md` (y su espejo en engram). Referencias: [spec órdenes](specs/ordenes-trabajo/spec.md), [spec catálogo](specs/estados-orden/spec.md), [spec persistencia](specs/persistencia-transaccional/spec.md) y [diseño](design.md), decisiones D1–D8.

**Strict TDD por comportamiento**: RED (test pytest + httpx contra PostgreSQL real migrada con Alembic en `test/pytest/`, que falla por la razón correcta) → GREEN (mínimo para pasar, ejecutado) → TRIANGULAR (al menos un segundo caso con otros datos, cubriendo cada escenario de la spec) → REFACTOR (tests en verde tras cada paso). Antes de modificar archivos existentes, correr sus tests como red de seguridad y anotar el baseline; un fallo previo se reporta como preexistente, no se arregla en silencio.

**Unidades de trabajo**: cada grupo numerado es un commit Conventional Commit con sus tests y docs (`feat(06-repositorios-uow-ordenes): ...` / `refactor(...)`), sin atribución de IA. ~400 líneas autorales por grupo es sólo una heurística de planificación. El grupo 7 (terminar: stock + dinero + transacción) va en su propio commit por riesgo. `test/ordenes.http` crece en cada grupo con los bloques de sus casos (D-3: un bloque por caso `C-xx`, respuesta esperada en comentario, sesiones con `# @name` + `# @no-cookie-jar` + `Cookie:`), corrido tras `python seed.py`.

## 1. Preparación y red de seguridad

- [x] 1.1 Restaurar las skills de dominio con `bash scripts/setup.sh` (o registrar la resolución degradada) y cargar las que correspondan (`sqlmodel`, `sqlalchemy`, `fastapi`, `pydantic`, `python-error-handling`, `async-python-patterns`, `tdd`, `python-testing-patterns`, `work-unit-commits`); verificar que `.agents/skills/` las contiene o que la degradación quedó anotada en el documento ODD.
- [x] 1.2 Crear `odd/tasks/06-repositorios-uow-ordenes.md` con objetivo, tareas, ruta por tarea (inline/delegada) y pronóstico de líneas; correr la suite completa sobre la base de test y registrar el baseline (cantidad aprobada y fallos ambientales conocidos) antes de la primera escritura.

## 2. Unit of Work base y auditoría de la jerarquía de repositorios

- [x] 2.1 RED/GREEN en `test/pytest/test_repositorios_uow.py`: un commit que falla en el `UnitOfWork` base revierte y propaga, sin cerrar la sesión; triangular con un UoW de `clientes` y uno de `repuestos`; mover el rollback al base y eliminar los `__aexit__` duplicados de `UnitOfWorkUsuario` y `UnitOfWorkIntentoAcceso`, verificando que `test/pytest/auth/` sigue en verde.
- [x] 2.2 Agregar pruebas de inspección de capas (spec persistencia): ninguna llamada `commit(` fuera del `UnitOfWork` base en `app/`, `main.py` y `seed.py`; ningún `service.py` instancia un Unit of Work; ningún `service.py`/`router.py` ejecuta `execute` sobre la sesión. Verificar que la última falla hoy (RED por `ordenes/service.py::_es_dueno_del_vehiculo`) y queda marcada como esperada hasta el grupo 3.
- [x] 2.3 Auditar `BaseRepository`/`SoftDeleteRepository` contra el Ejercicio 6 (clase del modelo en el constructor, seis métodos, `get_by_id_including_deleted`/`soft_delete` sólo en la subclase, `flush` sin `commit`) y completar los tests faltantes (`add` asigna id con `flush` y desaparece al revertir; la base no tiene métodos de borrado lógico); verificar con la suite de repositorios en verde.
- [x] 2.4 Auditar con prueba de falla inyectada que RN-02 (`registrar_usuario`) y RN-20 (`actualizar_repuesto`) escriben en un solo bloque (falla en la última escritura → ninguna fila nueva); verificar en verde y anotar evidencia.

## 3. Repositorios del módulo órdenes y reubicación de consultas

- [x] 3.1 RED/GREEN: `OrdenRepository.es_dueno_del_vehiculo` y `tiene_abiertas_del_vehiculo` (dueño también con vehículo dado de baja; abierta según `es_final`), con triangulación de dueño/ajeno/sin ficha y de estados finales/no finales.
- [x] 3.2 Hacer que `es_personal_o_dueno` use el repositorio (misma firma, T-8) y que `UnitOfWorkCliente` componga `ordenes` para la baja de vehículos; eliminar `VehiculoRepository.tiene_ordenes_abiertas`; verificar que la prueba de capas del 2.2 pasa a verde y que `test_clientes_vehiculos.py` (RN-16, C-19) sigue en verde sin cambiar contratos.
- [x] 3.3 RED/GREEN: `ItemOrdenRepository` (hereda de `BaseRepository`), `HistorialEstadoOrdenRepository` (sólo `add`, sin `update`/`delete`) y `OrdenRepository.get_detalle_con_items_e_historial` con precarga declarada (vehículo→cliente, ítems→repuesto incluido dado de baja, historial); probar que el detalle se lee sin carga perezosa y refleja ítems recién agregados en el mismo bloque.
- [x] 3.4 `UnitOfWorkOrden` compone `ordenes`, `items`, `historial`, `estados`, `vehiculos` y `repuestos` con la misma sesión; verificar con un test que todos comparten la sesión del UoW.

## 4. Catálogo de estados (sólo lectura) y `GET /estados-orden`

- [ ] 4.1 RED/GREEN: `EstadoOrdenRepository` que no hereda de `BaseRepository` ni ofrece `add`/`update`/`delete`, con `get_all_por_posicion` y `get_by_codigo`; triangular con catálogo vacío y con el seed.
- [ ] 4.2 RED/GREEN: `EstadoOrdenCodigo` (`StrEnum`) y `EstadoOrdenLectura`; test de alineación contrato ↔ catálogo sembrado (mismos cuatro códigos).
- [ ] 4.3 RED/GREEN: `GET /estados-orden` en el grupo protegido sin `requiere_rol` (200 por posición para ADMIN y CLIENTE, 401 sin sesión, 403 con cambio pendiente; `POST`/`PATCH`/`DELETE` rechazados y OpenAPI sólo con `GET`; el catálogo no cambia). Agregar a `test/ordenes.http` el bloque C-17 (catálogo con sesión y sin sesión) y documentar la ruta en el README.

## 5. Punto único de escritura de stock con guarda

- [ ] 5.1 Red de seguridad: correr `test/pytest/test_repuestos.py` y `test_repuestos_limites.py` y anotar el baseline.
- [ ] 5.2 RED/GREEN: `registrar_movimiento` con una salida mayor al stock lanza `StockInsuficiente` (subclase de `EnConflicto`, 409, mensaje humano con descripción, código y cantidades) sin agregar movimiento ni cambiar el stock; triangular con salida exacta al stock (queda 0) y con entrada positiva (sin cambios de comportamiento). Verificar que alta con stock inicial y reposición siguen en verde y que una prueba de inspección confirma que sólo el punto único asigna `stock` de un repuesto existente.

## 6. Contratos, alta, listado y detalle de órdenes

- [ ] 6.1 RED/GREEN de contratos (D1): `OrdenCrear`/`ItemOrdenCrear` con `extra="forbid"`, ≥1 ítem, sin `repuesto_id` repetido, `cantidad` 1..2147483647, `falla` 1..500; `ParametrosOrdenes` con `estado` enum (DD-40); `OrdenDetalle` con la forma del ejemplo de la consigna. Extender `errores.py` con etiquetas/mensajes para `falla`, `items`, `estado`, `enum` y el validador de repetidos sin eco de entrada; correr la regresión `test_errores_validacion.py`, `test_contratos.py`, `test_paginacion.py`.
- [ ] 6.2 RED/GREEN `POST /ordenes` (RECEPCION/ADMIN) en un solo bloque (D6): 201 de C-10 con precios copiados, subtotales, total `68000.00` e historial `null → PENDIENTE` firmado por la recepción; triangular el precio congelado tras un PATCH de precio. Probar 409 sin filas para repuesto inexistente/dado de baja, vehículo inexistente/dado de baja, catálogo vacío y total fuera de rango; 422 para precio/total/estado en el cuerpo, ítems vacíos o repetidos; 403 para MECANICO/CLIENTE.
- [ ] 6.3 RED/GREEN `GET /ordenes` (ADMIN/RECEPCION/MECANICO): paginado por id, filtro `estado` con `total` del mismo filtro, `estado` no declarado → 422 (C-17), 403 para CLIENTE; `/mis-ordenes` sin cambio de contrato.
- [ ] 6.4 RED/GREEN `GET /ordenes/{id}`: detalle completo de la orden 2 (ítems, repuesto, historial cronológico), 404 inexistente, 422 id no entero; personal ve cualquiera (DD-27), cliente dueño 200 (también con vehículo dado de baja, DD-28), cliente ajeno 403, sin sesión 401 (C-06 completo).
- [ ] 6.5 Agregar a `test/ordenes.http` los bloques C-17 (filtro válido e inválido), C-10 (201 y 409 con la orden no creada) y C-06 (200 propia, 403 ajena, 200 de `mecanico2` en una orden no asignada); documentar las rutas en el README y registrar en la KB (D-4) los contratos de D1 como DD nueva.

## 7. Transiciones: iniciar y cancelar

- [ ] 7.1 RED/GREEN `POST /ordenes/{id}/iniciar` (`requiere_rol("MECANICO")`): `PENDIENTE → EN_REPARACION`, `mecanico_id` = usuario, línea de historial, 200 con detalle; triangular 409 desde `EN_REPARACION`/`TERMINADA`/`CANCELADA` sin escrituras, 404 inexistente, 403 para ADMIN sin MECANICO y para el MECANICO con cambio pendiente.
- [ ] 7.2 RED/GREEN `POST /ordenes/{id}/cancelar` sin `requiere_rol`, con el predicado `puede_cancelar` (RECEPCION/ADMIN vigente o dueño) evaluado **antes** del estado: dueño cancela su `PENDIENTE` (200, historial con su id, stock y `mecanico_id` intactos); cliente sobre orden ajena no pendiente → 403 (no 409); MECANICO → 403; recepción sobre `TERMINADA` → 409; 404 inexistente; 401 sin sesión.
- [ ] 7.3 Agregar a `test/ordenes.http` los bloques de iniciar (200, 409 repetido, 403 de ADMIN) y la parte de C-13 que no depende de terminar (403 ajena, 200 del dueño); registrar en la KB (D-4) el orden de controles de D2 y el predicado `puede_cancelar` como DD.

## 8. Terminar orden (RN-13): stock, movimientos, estado e historial en un bloque

- [ ] 8.1 RED/GREEN permiso (`requiere_rol("MECANICO","ADMIN")` + asignación en el servicio): mecánico no asignado, recepción y cliente → 403 sin escrituras; mecánico asignado que perdió el rol MECANICO → 403; 404 inexistente; 409 desde `PENDIENTE`/`TERMINADA`/`CANCELADA` sin escrituras.
- [ ] 8.2 RED/GREEN C-11: terminar la orden 2 del seed (4 bujías, stock 2) → 409 con mensaje humano; estado, stock, cantidad de movimientos e historial idénticos antes y después. Triangular con una orden de varios ítems donde sólo el último no alcanza (ningún stock cambia).
- [ ] 8.3 RED/GREEN C-12 sin aviso: reponer 2 bujías y terminar con el mecánico asignado → 200 `TERMINADA`, stock 0, movimiento −4 «Salida por orden de trabajo #2» con `orden_id` y su `usuario_id`, línea `EN_REPARACION → TERMINADA`; triangular con un ADMIN que termina (no cambia `mecanico_id`, DD-31) y con un repuesto dado de baja tras el alta (DD-21). Probar con falla inyectada a mitad de la terminación que no queda ninguna escritura (RN-13, RT-TX-04).
- [ ] 8.4 Agregar a `test/ordenes.http` C-11 (409 + lecturas que muestran nada cambió), C-12 sin aviso (reponer, terminar, movimientos, historial) y el resto de C-13 (recepción cancela la orden terminada → 409); registrar en la KB (D-4) la guarda de stock y el tope del total (DD) y el supuesto del rol MECANICO vigente para el asignado (SU).

## 9. Verificación integrada y Definition of Done

- [ ] 9.1 Correr la suite pytest completa sobre PostgreSQL aislada con esquema de Alembic (incluye el ciclo `upgrade head → downgrade base → upgrade head` de `test_migraciones.py`); registrar aprobados/fallidos/omitidos reales y comparar con el baseline del 1.2 sin regresiones nuevas.
- [ ] 9.2 Levantar la API, correr `python seed.py` y ejecutar `test/ordenes.http` de punta a punta (C-06, C-10, C-11, C-12 sin aviso, C-13, C-17) y los `.http` previos (cada uno tras `python seed.py`); verificar que `python seed.py` vuelve a dejar el estado inicial después de las pruebas.
- [ ] 9.3 Verificación independiente (riesgo ALTO: transacciones de varias escrituras, stock, permisos y helpers compartidos): ningún `commit()` en repositorios, ningún servicio construye su UoW, catálogo de sólo lectura sin herencia, precarga declarada en el método, punto único de stock, 403 antes que 409 en cancelar, matriz de permisos de órdenes, sin secretos ni texto interno en errores; registrar el dictamen sin inventar evidencia.
- [ ] 9.4 Conciliar specs/diseño/tasks con lo observado, README (rutas y uso de `test/ordenes.http`), `env.example` (sin variables nuevas: verificar), KB `09_decisiones_y_supuestos.md` con todas las DD/SU candidatas del diseño y `10_preguntas_abiertas.md` si surgió alguna duda; validar con `openspec validate 06-repositorios-uow-ordenes --strict`.

## Workflow follow-up

- Con la implementación verificada, ejecutar `/opsx:archive 06-repositorios-uow-ordenes` (no forma parte de esta propuesta).
- En el commit de cierre: marcar `[x]` EJ-6 en `CHANGES.md`, correr `bash scripts/sync-memoria.sh` (Windows: `scripts\sync-memoria.bat`) y hacer push sólo con autorización explícita de entrega.
- El relevo a EJ-7 (`07-integridad`) requiere EJ-6 archivado, commiteado y empujado.
