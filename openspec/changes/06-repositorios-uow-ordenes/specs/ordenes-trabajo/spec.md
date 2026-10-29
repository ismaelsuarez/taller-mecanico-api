# Spec Delta

## Purpose

Gestionar el ciclo de vida de las órdenes de trabajo del taller: alta con precios copiados y total calculado por el servidor, listado y detalle, e inicio, terminación y cancelación con sus permisos, su historial de estados y la terminación atómica que descuenta stock.

## ADDED Requirements

### Requirement: Contrato de alta de una orden

El cuerpo de `POST /ordenes` MUST aceptar sólo `vehiculo_id`, `falla` (texto no vacío de hasta 500 caracteres) e `items` (al menos uno, cada uno con `repuesto_id` y `cantidad` entera positiva representable en PostgreSQL). Un cuerpo con campos no declarados (precio, total, estado o fecha), sin ítems, con un `repuesto_id` repetido o con una cantidad ≤ 0 MUST responder 422 con mensaje humano, sin crear nada (RN-10, SU-07).

#### Scenario: Precio o total en el cuerpo
- **WHEN** se envía `POST /ordenes` con `total`, `estado` o `precio_unitario` en el cuerpo o en un ítem
- **THEN** responde 422 y no se crea ninguna orden

#### Scenario: Sin ítems o con un repuesto repetido
- **WHEN** se envía `items: []`, o dos ítems con el mismo `repuesto_id`
- **THEN** responde 422 con un mensaje en español, sin texto del validador ni eco de la entrada

#### Scenario: Cantidad no positiva
- **WHEN** un ítem trae `cantidad` 0 o negativa
- **THEN** responde 422 y no se crea ninguna orden

### Requirement: Alta de una orden con precios copiados y total del servidor

Con un cuerpo válido, `POST /ordenes` (RECEPCION o ADMIN) MUST crear la orden en `PENDIENTE` con `creada_en` del servidor, copiar a cada ítem el precio vigente del repuesto, calcular el total como Σ cantidad × precio unitario, agregar la línea de historial `null → PENDIENTE` firmada por el usuario autenticado y responder 201 con el detalle de la orden (C-10).

#### Scenario: Alta con dos ítems (C-10)
- **WHEN** la recepción crea una orden para el vehículo 2 con 1 × repuesto 2 y 3 × repuesto 4 del seed
- **THEN** responde 201 con estado `PENDIENTE`, patente `AC456EF`, cliente `Laura Cliente`, precios unitarios `32000.00` y `12000.00`, subtotales `32000.00` y `36000.00`, total `68000.00`, `mecanico_id` nulo y un historial con una línea `null → PENDIENTE` cuyo `usuario_id` es el de la recepción

#### Scenario: El precio del ítem no cambia con el repuesto
- **WHEN** después de crear la orden el administrador cambia el precio de uno de sus repuestos
- **THEN** el `precio_unitario` del ítem y el total de la orden conservan el valor copiado al alta

### Requirement: Referencias inválidas en el alta

`POST /ordenes` MUST responder 409 con mensaje humano, sin dejar ninguna fila de la orden, de sus ítems ni de su historial, cuando el vehículo no existe o está dado de baja, cuando algún repuesto no existe o está dado de baja (RN-16, SU-06), o cuando el total calculado no es representable en la columna de dinero.

#### Scenario: Repuesto inexistente (C-10)
- **WHEN** se crea una orden con un ítem cuyo `repuesto_id` no existe
- **THEN** responde 409 y la cantidad de órdenes, ítems y líneas de historial no cambia

#### Scenario: Vehículo o repuesto dado de baja
- **WHEN** se crea una orden para un vehículo dado de baja, o con un repuesto dado de baja
- **THEN** responde 409 con mensaje propio y la orden no queda creada

#### Scenario: Total fuera de rango
- **WHEN** las cantidades y precios válidos producen un total mayor al máximo representable
- **THEN** responde 409 con mensaje humano, nunca 500, y no se crea la orden

### Requirement: Alta sin catálogo de estados

Si el catálogo `estado_orden` no tiene el estado `PENDIENTE` (por ejemplo, está vacío), `POST /ordenes` MUST responder 409 con un mensaje propio en español que no mencione tablas, columnas ni restricciones, y no MUST crear ninguna fila (RN-19).

#### Scenario: Catálogo vacío
- **WHEN** el catálogo está vacío y la recepción envía un alta válida
- **THEN** responde 409 con mensaje propio y no queda ninguna orden, ítem ni línea de historial

### Requirement: Listado de órdenes filtrable por estado

`GET /ordenes` (ADMIN, RECEPCION, MECANICO) MUST devolver el envoltorio `{items, total, page, size, pages}` ordenado por id, con filtro opcional `estado` cuyos valores son los del contrato (`PENDIENTE`, `EN_REPARACION`, `TERMINADA`, `CANCELADA`). Un `estado` que el contrato no declara MUST responder 422 (RT-PG-08, C-17); `total` cuenta con el mismo filtro.

#### Scenario: Filtro válido
- **WHEN** el personal lista `GET /ordenes?estado=PENDIENTE` tras el seed
- **THEN** responde 200 con la orden 1 y `total = 1`

#### Scenario: Estado no declarado (C-17)
- **WHEN** se lista `GET /ordenes?estado=ARCHIVADA`
- **THEN** responde 422 con mensaje humano, sin ejecutar la consulta

#### Scenario: Cliente sin rol de personal
- **WHEN** una sesión CLIENTE llama a `GET /ordenes`
- **THEN** responde 403

### Requirement: Detalle de una orden

`GET /ordenes/{id}` MUST responder 200 con la orden, la patente del vehículo, el nombre del cliente, sus ítems con código y descripción de cada repuesto (también si el repuesto fue dado de baja, DD-21), subtotales y su historial de estados en orden cronológico. Un id inexistente MUST responder 404; un id no entero, 422.

#### Scenario: Detalle completo
- **WHEN** el personal consulta la orden 2 del seed
- **THEN** responde 200 con 1 ítem de 4 bujías, total `26000.00`, `mecanico_id` del mecánico asignado y dos líneas de historial en orden (`null → PENDIENTE`, `PENDIENTE → EN_REPARACION`)

#### Scenario: Orden inexistente
- **WHEN** se consulta `GET /ordenes/999`
- **THEN** responde 404 con mensaje humano

### Requirement: Quién ve el detalle de una orden

El personal (ADMIN, RECEPCION, MECANICO vigentes) MUST ver el detalle de cualquier orden (DD-27). Un usuario sin rol de personal MUST verla sólo si es el dueño del vehículo —incluso si el vehículo fue dado de baja (DD-28)— y MUST recibir 403 con mensaje humano para cualquier otra (RN-17, C-06). Sin sesión, 401.

#### Scenario: El cliente ve su orden y no la ajena (C-06)
- **WHEN** `cliente@example.com` consulta la orden 1 (de su vehículo) y la orden 2 (de Jorge)
- **THEN** la primera responde 200 y la segunda 403 sin datos de la orden

#### Scenario: Un mecánico ve una orden que no tiene asignada
- **WHEN** `mecanico2@example.com` consulta la orden 1
- **THEN** responde 200

#### Scenario: Sin sesión
- **WHEN** se consulta una orden sin cookie
- **THEN** responde 401

### Requirement: Iniciar una orden

`POST /ordenes/{id}/iniciar` MUST estar permitido sólo a MECANICO (403 para cualquier otro rol, incluido ADMIN). Sobre una orden `PENDIENTE` MUST pasarla a `EN_REPARACION`, asignar `mecanico_id` al usuario autenticado, agregar la línea de historial y responder 200 con el detalle. Orden inexistente → 404; en otro estado → 409 sin escrituras (RN-11).

#### Scenario: Un mecánico toma una orden pendiente
- **WHEN** `mecanico2@example.com` inicia una orden `PENDIENTE`
- **THEN** responde 200 con estado `EN_REPARACION`, `mecanico_id` del mecánico y una línea `PENDIENTE → EN_REPARACION` firmada por él

#### Scenario: Orden que no está pendiente
- **WHEN** un mecánico inicia una orden `EN_REPARACION`, `TERMINADA` o `CANCELADA`
- **THEN** responde 409 y no cambian el estado, el mecánico ni el historial

#### Scenario: Administrador intenta iniciar
- **WHEN** una sesión ADMIN sin rol MECANICO inicia una orden
- **THEN** responde 403

### Requirement: Permiso para terminar una orden

`POST /ordenes/{id}/terminar` MUST estar permitido sólo al mecánico asignado a la orden (con el rol MECANICO vigente) o a un ADMIN vigente. Cualquier otro usuario, incluido otro mecánico, MUST recibir 403 antes de evaluar el estado. Orden inexistente → 404.

#### Scenario: Mecánico no asignado
- **WHEN** `mecanico2@example.com` termina la orden 2, asignada a `mecanico@example.com`
- **THEN** responde 403 y no se escribe nada

#### Scenario: Recepción o cliente
- **WHEN** la recepción o un cliente intentan terminar una orden
- **THEN** responde 403

### Requirement: Terminación atómica que descuenta stock

Terminar una orden `EN_REPARACION` MUST, en una sola transacción, descontar el stock de cada ítem por el punto único de escritura, dejar un movimiento de salida por ítem (cantidad negativa, `orden_id`, motivo «Salida por orden de trabajo #N», firmado por quien termina), pasar a `TERMINADA` con una línea de historial y responder 200. `mecanico_id` no cambia (DD-31). Otro estado → 409 (RN-11, RN-13).

#### Scenario: Reponer y terminar la orden 2 (C-12, sin aviso)
- **WHEN** el administrador repone 2 bujías y `mecanico@example.com` termina la orden 2
- **THEN** responde 200 con estado `TERMINADA`, el stock de la bujía queda en 0, aparece un movimiento de −4 con motivo «Salida por orden de trabajo #2» y una línea `EN_REPARACION → TERMINADA` firmada por el mecánico

#### Scenario: El ADMIN termina sin cambiar el mecánico
- **WHEN** un ADMIN termina una orden `EN_REPARACION` con stock suficiente
- **THEN** responde 200, `mecanico_id` conserva al mecánico que la inició y el historial y los movimientos llevan el `usuario_id` del ADMIN

#### Scenario: Orden que no está en reparación
- **WHEN** el mecánico asignado o un ADMIN terminan una orden `PENDIENTE`, `TERMINADA` o `CANCELADA`
- **THEN** responde 409 sin modificar stock, movimientos, estado ni historial

#### Scenario: Repuesto dado de baja después del alta
- **WHEN** se termina una orden cuyo repuesto fue dado de baja después de crearla, con stock suficiente
- **THEN** responde 200 y descuenta el stock de ese repuesto como de cualquier otro (DD-21)

### Requirement: Stock insuficiente al terminar

Si algún ítem pide más unidades que el stock de su repuesto, terminar MUST responder 409 con mensaje humano y no MUST quedar ninguna de las escrituras de la terminación: estado, stock de todos los ítems, movimientos e historial quedan exactamente como estaban (RN-13, C-11).

#### Scenario: Terminar la orden 2 sin bujías suficientes (C-11)
- **WHEN** `mecanico@example.com` termina la orden 2 del seed (4 bujías pedidas, stock 2)
- **THEN** responde 409; la orden sigue `EN_REPARACION`, la bujía sigue con stock 2 y no aparecen movimientos ni líneas de historial nuevas

#### Scenario: Falta stock en el último ítem
- **WHEN** una orden con varios ítems tiene stock suficiente en todos salvo el último
- **THEN** responde 409 y el stock de los ítems anteriores tampoco cambia

### Requirement: Permiso para cancelar una orden

`POST /ordenes/{id}/cancelar` MUST NOT exigir un rol en la ruta: el permiso lo decide el servicio y sólo lo tienen RECEPCION o ADMIN vigentes y el dueño del vehículo. Cualquier otro usuario (incluido un MECANICO) MUST recibir 403 **antes** de evaluar el estado de la orden (RN-12). Orden inexistente → 404.

#### Scenario: Orden ajena en un estado no cancelable (C-13)
- **WHEN** `cliente@example.com` cancela la orden 2, que no es suya y no está `PENDIENTE`
- **THEN** responde 403, no 409

#### Scenario: Un mecánico intenta cancelar
- **WHEN** un MECANICO sin otro rol cancela una orden `PENDIENTE`
- **THEN** responde 403 y la orden sigue `PENDIENTE`

### Requirement: Cancelación sólo desde PENDIENTE

Con permiso, cancelar una orden `PENDIENTE` MUST pasarla a `CANCELADA`, agregar la línea de historial firmada por quien cancela y responder 200 con el detalle, sin tocar stock ni `mecanico_id`. En cualquier otro estado MUST responder 409 sin escrituras (RN-11, C-13).

#### Scenario: El dueño cancela su orden pendiente (C-13)
- **WHEN** `cliente@example.com` cancela la orden 1
- **THEN** responde 200 con estado `CANCELADA` y una línea `PENDIENTE → CANCELADA` con su `usuario_id`

#### Scenario: Orden terminada (C-13)
- **WHEN** la recepción cancela una orden `TERMINADA`
- **THEN** responde 409 y el estado y el historial no cambian

### Requirement: Rutas de órdenes protegidas

Toda ruta de órdenes MUST pertenecer al grupo protegido: sin sesión MUST responder 401 y con el cambio de contraseña pendiente 403, antes de cualquier 404/409. Los mensajes de 401, 403, 404 y 409 MUST estar en español claro, sin nombres de tablas, columnas, restricciones ni trazas (DD-25).

#### Scenario: Sin sesión sobre una transición
- **WHEN** se llama a `POST /ordenes/1/cancelar` sin cookie
- **THEN** responde 401 y la orden no cambia

#### Scenario: Cambio de contraseña pendiente
- **WHEN** `nuevo@example.com` (MECANICO con cambio pendiente) inicia una orden
- **THEN** responde 403 y la orden no cambia
