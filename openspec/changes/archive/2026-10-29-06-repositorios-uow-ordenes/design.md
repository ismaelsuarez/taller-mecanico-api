# Design

## Context

Ver `proposal.md` para motivación y alcance; `specs/ordenes-trabajo`, `specs/estados-orden` y `specs/persistencia-transaccional` fijan los comportamientos. El diseño es necesario por ser transversal (cuatro módulos y `app/core`), por la operación de cuatro escrituras de la terminación y por los permisos mixtos rol/dueño.

| Evidencia actual (observada en el código) | Consecuencia de diseño |
|---|---|
| `app/core/repository.py` ya tiene `BaseRepository[T](sesion, modelo)` con los seis métodos y `SoftDeleteRepository[T]` con `get_by_id_including_deleted`/`soft_delete`, con `flush()` y sin `commit()`; `test/pytest/test_repositorios_uow.py` lo cubre | No se reescribe: se **audita** contra la consigna y se completan tipos/docstrings; los tests nuevos se agregan a los existentes |
| `app/core/unit_of_work.py` confirma/revierte y no cierra la sesión, pero **no** revierte si el propio `commit()` falla; `UnitOfWorkUsuario` y `UnitOfWorkIntentoAcceso` repiten ese rollback con un `__aexit__` propio | D4: subir el rollback del commit fallido al base y borrar los dos overrides (comportamiento idéntico para `usuarios`, ahora también para `clientes`, `repuestos`, `ordenes`) |
| `ordenes/service.py::_es_dueno_del_vehiculo` ejecuta `select` sobre `uow.ordenes.sesion` desde el servicio | D3: la consulta pasa a `OrdenRepository.es_dueno_del_vehiculo`; `es_personal_o_dueno` conserva su firma (T-8) |
| `clientes/repository.py::VehiculoRepository.tiene_ordenes_abiertas` consulta `orden_trabajo` y su docstring anuncia que EJ-6 lo reemplaza | D3: se mueve a `OrdenRepository.tiene_abiertas_del_vehiculo`; `UnitOfWorkCliente` compone `ordenes` con la misma sesión; RN-16 sin cambio observable |
| `repuestos/repository.py::RepuestoRepository.registrar_movimiento` es el punto único (T-3) pero suma sin guarda; la base tiene `CHECK stock >= 0`, que ante una salida grande produciría `IntegrityError` → 500 | D5: guarda de stock negativo dentro del punto único → `StockInsuficiente` (409) antes de tocar nada |
| `es_personal_o_dueno` (EJ-5) trata como «personal» también a MECANICO | Sirve para el detalle (DD-27) pero **no** para cancelar: MECANICO no cancela (RN-12, matriz). D2 define un predicado distinto para cancelar |
| `IdentidadLectura.roles_vigentes` se calcula en `get_usuario_actual` desde `asignacion_rol` en cada petición | Los permisos del servicio (detalle, terminar, cancelar) usan esos roles: siguen siendo los vigentes de la base (RN-04) sin otra consulta |
| `errores.py::_mensaje_validacion` sólo etiqueta campos de primer nivel (`loc` de largo 2) y no conoce los tipos `enum` ni `value_error` | D1: se agregan etiquetas `falla`, `items`, `estado` y mensajes para `enum`, `too_short` de listas y el validador de repetidos, sin eco de entrada (DD-42); los ítems anidados caen en el mensaje genérico seguro |
| DD-40: con `Annotated[Modelo, Query()]` y `extra="forbid"`, todo query param debe ser campo del modelo | `ParametrosOrdenes(ParametrosPagina)` con `estado: EstadoOrdenCodigo | None` |
| DD-38: el seed sincroniza la secuencia de `orden_trabajo`; las órdenes del seed son 1 (`PENDIENTE`, Laura) y 2 (`EN_REPARACION`, Jorge, 4 bujías con stock 2, `mecanico_id = 4`) | La primera orden creada por la API es la 3; C-10..C-13 se escriben sobre esos datos |
| Las skills de dominio (sqlmodel, sqlalchemy, fastapi, pydantic, tdd…) no están restauradas en `.agents/skills/` y el registro `.atl/skill-registry.md` no las indexa | El apply debe correr `bash scripts/setup.sh` (o declarar la resolución degradada) antes de cargar skills; este diseño se apoya en las reglas duras de `CLAUDE.md` |

## Goals / Non-Goals

**Goals:** que la corrección del 20 % encuentre cada pieza que nombra la consigna en su lugar (dos jerarquías, clase del modelo, `flush` sin `commit`, precarga en el método, quién crea/abre/confirma/cierra, operaciones de varias escrituras en un bloque); que la terminación sea todo o nada sobre PostgreSQL real; que el orden de los controles (401 → 403 → 404/409 según la ruta) sea explícito y probado.

**Non-Goals:** cambios de esquema o del seed; bloqueo optimista/pesimista del stock (DD-08); aviso en segundo plano y conteo de consultas como evidencia (EJ-8); auditoría de `intento_acceso` y C-14 (EJ-7); repositorios genéricos de sólo lectura reutilizables (el catálogo es el único caso); refactor de los servicios de EJ-3..5 más allá de lo que la auditoría de capas exige.

## Decisions

### D1 — Contratos de órdenes (propuestos; se documentan en la KB al aplicar, D-4)

| Operación | Entrada | Salida |
|---|---|---|
| `POST /ordenes` 201 | `OrdenCrear {vehiculo_id: int 1..2147483647, falla: str 1..500, items: list[ItemOrdenCrear] min 1}`; `ItemOrdenCrear {repuesto_id: int 1..2147483647, cantidad: int 1..2147483647}`; `model_validator` rechaza `repuesto_id` repetidos; todo `extra="forbid"` | `OrdenDetalle` con la forma exacta del ejemplo de la consigna: `{id, estado, patente, total, creada_en, mecanico_id, falla, cliente, items:[{repuesto_id, codigo, descripcion, cantidad, precio_unitario, subtotal}], historial:[{desde_estado, hasta_estado, usuario_id, cuando}]}` |
| `GET /ordenes` 200 | `ParametrosOrdenes {page, size, estado?: EstadoOrdenCodigo}` | `Pagina[OrdenResumenLectura]` (el resumen ya usado por `/mis-ordenes`, sin cambiar su contrato) |
| `GET /ordenes/{id}` 200 | — | `OrdenDetalle` |
| `POST /ordenes/{id}/iniciar\|terminar\|cancelar` 200 | Sin cuerpo | `OrdenDetalle` ya actualizado |
| `GET /estados-orden` 200 | — | `list[EstadoOrdenLectura {codigo, descripcion, posicion, es_final}]` sin paginar (4 filas fijas; la tabla de rutas sólo lista 200) |

`EstadoOrdenCodigo` es un `StrEnum` con los cuatro códigos del seed: es el contrato de la API (422) mientras la FK al catálogo es la garantía de la base (DD-02). Dinero como `Decimal` serializado con dos decimales (`subtotal = cantidad × precio_unitario`). El historial se devuelve ordenado por `(cuando, id)` y los ítems por id (orden del alta); ambos órdenes los aplica el serializador del servicio, no el repositorio. Un `orden_id` de la ruta fuera de `1..2147483647` no puede existir y responde 404 (nunca 422 ni un error de la base); un id no entero sigue siendo 422 (DD-52).

*Alternativas descartadas*: devolver `{vehiculo:{...}, cliente:{...}}` anidados (no coincide con el ejemplo de la consigna que la corrección compara); paginar `/estados-orden` (agrega 422 que la tabla de rutas no contempla); respuestas 204 en las transiciones (el cliente perdería el estado resultante que C-12/C-13 muestran).

### D2 — Dónde se decide cada permiso y en qué orden

| Ruta | Dependencia de ruta | Servicio (en orden) |
|---|---|---|
| `POST /ordenes` | `requiere_rol("RECEPCION","ADMIN")` | catálogo → vehículo → repuestos → total (409) |
| `GET /ordenes` | `requiere_rol("ADMIN","RECEPCION","MECANICO")` | — |
| `GET /ordenes/{id}` | sólo sesión (grupo protegido) | 404 → `es_personal_o_dueno` (403) |
| `POST /ordenes/{id}/iniciar` | `requiere_rol("MECANICO")` | 404 → estado `PENDIENTE` (409) |
| `POST /ordenes/{id}/terminar` | `requiere_rol("MECANICO","ADMIN")` | 404 → `puede_terminar` = ADMIN vigente **o** (MECANICO vigente **y** `mecanico_id == usuario`) (403) → estado `EN_REPARACION` (409) → stock (409) |
| `POST /ordenes/{id}/cancelar` | **ninguna** (nota de la consigna) | 404 → `puede_cancelar` = RECEPCION/ADMIN vigente **o** dueño del vehículo (403) → estado `PENDIENTE` (409) |
| `GET /estados-orden` | sólo sesión | — |

`puede_cancelar` es un predicado nuevo y separado de `es_personal_o_dueno` porque «personal» incluye a MECANICO, que no cancela. Ambos usan `OrdenRepository.es_dueno_del_vehiculo` (dueño = `cliente.usuario_id` del vehículo, también dado de baja — DD-28).

En terminar, el rol en la ruta hace que RECEPCION/CLIENTE reciban 403 aun para un id inexistente: la consigna lista 403 y 404 para la ruta y RN-12 fija «permiso antes que estado»; se acepta que el permiso por rol preceda a la existencia. Un mecánico asignado que perdió el rol MECANICO recibe 403 (RN-04: los permisos salen de los roles vigentes) — registrado como SU-15.

*Alternativa descartada*: `terminar` sin `requiere_rol` y todo en el servicio — duplica en el servicio la consulta de roles que `requiere_rol` ya resuelve y mezcla dos responsabilidades.

### D3 — Repositorios del módulo `ordenes` y reubicación de consultas

- `OrdenRepository(BaseRepository[OrdenTrabajo])`: `get_detalle_con_items_e_historial(id)` (`joinedload(vehiculo).joinedload(Vehiculo.cliente)`, `selectinload(items).joinedload(ItemOrden.repuesto)`, `selectinload(historial_estados)`; con `populate_existing` para que, dentro del mismo bloque, refleje ítems e historial recién agregados); `listar(estado, page, size) -> (items, total)` con el mismo filtro para el conteo; `es_dueno_del_vehiculo(usuario_id, vehiculo_id)`; `tiene_abiertas_del_vehiculo(vehiculo_id)` (join con `estado_orden.es_final = false`); los métodos de `/mis-ordenes` existentes sin cambio de contrato.
- `ItemOrdenRepository(BaseRepository[ItemOrden])`: los ítems se agregan sólo dentro del bloque del alta de su orden (composición de la consigna: un ítem no existe sin su orden); no hay endpoint propio.
- `HistorialEstadoOrdenRepository`: sólo `add` (sólo agregado, RN-15), con el mismo patrón que `MovimientoStockRepository`; no hereda `update`/`delete`.
- `EstadoOrdenRepository`: **no** hereda de `BaseRepository`; `get_all_por_posicion()` y `get_by_codigo(codigo)`; ningún método de escritura.
- `RepuestoRepository.get_vigentes_por_ids(ids)` (una consulta `IN` con parámetros ligados) para validar los repuestos del alta; la terminación lee los repuestos por la relación precargada del ítem, que trae también los dados de baja (DD-21, equivalente a `get_by_id_including_deleted`).

*Alternativas descartadas*: dejar los ítems sólo como cascada del agregado sin repositorio (contradice «cada entidad tiene su repositorio»); un repositorio genérico de sólo lectura para el catálogo (sobrediseño para un caso único).

### D4 — Unit of Work

- Base: `__aexit__` confirma sin excepción; con excepción revierte y la propaga; si `commit()` lanza, revierte y propaga; nunca cierra la sesión. Se eliminan los overrides equivalentes de `usuarios`.
- `UnitOfWorkOrden(sesion)`: `ordenes`, `items`, `historial`, `estados`, `vehiculos` (`VehiculoRepository`), `repuestos` (`RepuestoRepository`) — misma sesión.
- `UnitOfWorkCliente` agrega `ordenes` para la consulta de órdenes abiertas.
- Construcción: `construir_uow(sesion: SesionDep)` en cada `router.py` (ya existe en los cuatro); `app/core/dependencies.py` también construye `UnitOfWorkUsuario` dentro de dependencias, lo cual es conforme (una dependencia construye, el servicio abre).
- RN-02 (`registrar_usuario`), RN-20 (`actualizar_repuesto`) ya están en un solo bloque: se agregan pruebas de falla inyectada que lo demuestran; RN-13 nace en un bloque.

### D5 — Punto único de stock con guarda

`registrar_movimiento(repuesto, cantidad, motivo, usuario_id, orden_id=None)` valida `repuesto.stock + cantidad >= 0` **antes** de agregar el movimiento o tocar el stock; si no, lanza `StockInsuficiente(EnConflicto)` con un mensaje humano que nombra el repuesto por descripción y código y las cantidades («No hay stock suficiente de Bujía de encendido (BUJ-014): hay 2 y se necesitan 4.»). `StockInsuficiente` vive en `app/core/errores.py`, junto a `EnConflicto`, para no agregar archivos fuera de la estructura obligatoria (A-2) y para que el traductor de dominio lo resuelva a 409 sin cambios. La guarda vive en el punto único (y no sólo en el servicio de órdenes) para que ningún llamador futuro pueda dejar stock negativo; el `CHECK` de la base queda como última defensa. El tope superior de reposición (`MAXIMO_STOCK`, DD-41) se mantiene en el servicio de repuestos sin cambios.

Terminar recorre los ítems en orden de id llamando al punto único con `-cantidad`, motivo `f"Salida por orden de trabajo #{orden.id}"` y `orden_id`; la primera insuficiencia aborta el bloque y el UoW revierte todas las escrituras previas (C-11).

### D6 — Alta en un bloque

Dentro de `async with uow`: (1) `estados.get_by_codigo("PENDIENTE")` nulo → 409 «Todavía no se pueden crear órdenes: falta cargar los estados del taller.»; (2) `vehiculos.get_by_id` vigente nulo → 409; (3) `repuestos.get_vigentes_por_ids` con faltantes → 409 que nombra los ids pedidos que no están disponibles; (4) total `Decimal` y tope `NUMERIC(12,2)` (≤ 9 999 999 999.99) → 409 si se excede; (5) `ordenes.add` (flush → id), `items.add` por ítem con `precio_unitario` copiado, `historial.add(null → PENDIENTE)`; (6) relectura con `get_detalle_con_items_e_historial`. La respuesta se arma con los datos ya leídos; con `expire_on_commit=False` siguen disponibles tras el commit.

### D7 — Transiciones

Tabla única en el servicio: `iniciar: PENDIENTE → EN_REPARACION`, `terminar: EN_REPARACION → TERMINADA`, `cancelar: PENDIENTE → CANCELADA`. Cada transición, en un bloque: valida el estado de origen (`_exigir_estado`) antes de la primera escritura y luego cambia `estado`, agrega la línea de historial (`desde`, `hasta`, `usuario_id` de quien actúa, `cuando` UTC) y, sólo en iniciar, asigna `mecanico_id` (`_registrar_transicion`, que además relee el detalle con la precarga declarada). En terminar, las salidas de stock van entre la validación del estado y `_registrar_transicion`, de modo que un 409 por estado nunca toca el stock. Terminar no toca `mecanico_id` (DD-31). Mensajes 409 humanos por estado («La orden ya está terminada: no se puede cancelar.»).

### D8 — Pruebas y entregables

- `test/pytest/ordenes/` con su `conftest.py`, reutilizando la fixture `base_migrada` (Alembic real, DD-43) y las sesiones reales de `test/pytest/autorizacion/conftest.py`, que `ordenes/conftest.py` importa sin duplicarlas (no se promovieron a un módulo compartido). Los datos de las órdenes 1/2 salen de `seed.py` real (fixtures `base_sembrada` y `api_sembrada`); los helpers de snapshot y alta (`instantanea`, `poner_estado`, `crear_orden`) viven en `test/pytest/ordenes/_apoyo.py`.
- Pruebas de capas por inspección (sin `commit(` fuera del UoW base, servicios sin `execute`, catálogo sin escrituras) y pruebas de comportamiento con fallos inyectados (rollback de commit fallido, falla a mitad de terminación/registro/precio).
- `test/ordenes.http` siguiendo D-3 y el formato de `test/autorizacion.http` (variables de contraseña por entorno, `# @name` + `# @no-cookie-jar` + `Cookie:`), orden de bloques: C-17 → C-10 → C-06 → iniciar → C-11 → C-12 → C-13.

### Supuestos/decisiones nuevos registrados en `knowledge-base/09_decisiones_y_supuestos.md` (D-4)

1. **DD-52** — contratos de D1 (forma del detalle = ejemplo de la consigna; transiciones devuelven 200 con el detalle; `/estados-orden` sin paginar).
2. **DD-54** — orden de controles de D2, predicado `puede_cancelar` separado de `es_personal_o_dueno`, y `requiere_rol("MECANICO","ADMIN")` en terminar.
3. **SU-15** — el mecánico asignado necesita el rol MECANICO vigente para terminar.
4. **DD-53** — guarda de stock en el punto único (`StockInsuficiente` → 409) y tope del total de la orden → 409 (extiende DD-41).
5. **DD-51** — `ItemOrdenRepository` e `HistorialEstadoOrdenRepository` (sólo agregado), reubicación de las consultas de órdenes a `OrdenRepository` y rollback del commit fallido en el UoW base.

## Risks / Trade-offs

- [Cambiar el `UnitOfWork` base afecta a los cuatro módulos y al seed] → la suite completa corre antes y después; los overrides de `usuarios` se borran sólo tras ver verde el base con sus mismas pruebas.
- [Mover `tiene_ordenes_abiertas` toca la baja de vehículos (C-19, RN-16) de EJ-3] → pruebas existentes de `clientes-vehiculos` como red de seguridad antes de mover; sin cambio de contrato.
- [`populate_existing` y la identidad de sesión pueden devolver colecciones viejas tras agregar ítems/historial en el mismo bloque] → prueba explícita de que la respuesta 201 trae los ítems y la línea de historial; alternativa: `sesion.expire(orden)` antes de releer.
- [Extender el traductor 422 compartido] → sólo agregar etiquetas/casos; regresión de `test_errores_validacion.py`, `test_contratos.py` y `test_paginacion.py`.
- [Dos terminaciones simultáneas pueden perder una actualización de stock] → fuera de alcance por DD-08 (cap. 7); el `CHECK stock >= 0` evita al menos el stock negativo.
- [El 403 por rol en terminar precede al 404] → documentado en D2 y en la DD candidata; coherente con la tabla de códigos de la consigna.
- [El historial depende del orden de `cuando`; dos líneas en el mismo microsegundo] → desempate por `id`.
- [Skills de dominio no restauradas en la máquina] → el apply corre `scripts/setup.sh` o reporta `skill_resolution` degradada; las reglas duras de `CLAUDE.md` mandan igual.

## Migration Plan

Sin migraciones ni cambios de `seed.py`. Despliegue: `git pull`, `alembic upgrade head` (no-op), `python seed.py`, levantar la API. Rollback: revertir los commits del change; no hay datos nuevos que limpiar más allá de las órdenes de prueba, que el seed vuelve a dejar en el estado inicial. Como regresión del DoD, el ciclo `upgrade head → downgrade base → upgrade head` se vuelve a correr (cubierto por `test_migraciones.py`) aunque el esquema no cambie.
