# Spec Delta

## Purpose

Define el catálogo de repuestos: listado y detalle, alta con stock inicial, cambio de precio con historial en la misma transacción, borrado lógico, reposición de stock a través del punto único de escritura y las consultas de movimientos y precios.

## ADDED Requirements

### Requirement: Listado y detalle de repuestos

`GET /repuestos` MUST listar los repuestos **vigentes** paginados con búsqueda opcional `q` por descripción; `GET /repuestos/{id}` MUST devolver 200 con el repuesto y 404 si no existe o está dado de baja.

#### Scenario: Listado sólo vigentes
- **WHEN** hay repuestos vigentes y otros dados de baja
- **THEN** el listado sólo incluye los vigentes

#### Scenario: Detalle de repuesto dado de baja
- **WHEN** se pide `GET /repuestos/{id}` de un repuesto dado de baja
- **THEN** la respuesta es 404

### Requirement: Alta con stock inicial

`POST /repuestos` MUST crear un repuesto con `stock_inicial ≥ 0` (default 0) y responder 201; `stock_inicial` negativo MUST responder 422 (DD-23, RT-EQ-04); un `codigo` vigente repetido MUST responder 409 (RN-01); un `precio ≤ 0` MUST responder 422. Cuando `stock_inicial > 0` MUST quedar un movimiento «Stock inicial»; con 0 no MUST haber movimiento. El stock cambia únicamente a través del **punto único de escritura de stock** (RN-14, T-3).

#### Scenario: Alta con stock positivo
- **WHEN** se envía `POST /repuestos` con `stock_inicial: 5`
- **THEN** la respuesta es 201, el repuesto tiene `stock` 5 y existe un movimiento «Stock inicial» con cantidad 5

#### Scenario: Alta sin stock
- **WHEN** se envía `POST /repuestos` sin `stock_inicial` (default 0)
- **THEN** la respuesta es 201, el repuesto tiene `stock` 0 y no hay movimiento de stock

#### Scenario: Stock inicial negativo
- **WHEN** se envía `POST /repuestos` con `stock_inicial: -1`
- **THEN** la respuesta es 422 y no se crea el repuesto

### Requirement: Cambio de precio con historial en la misma transacción

`PATCH /repuestos/{id}` MUST aceptar sólo `descripcion` y/o `precio` (`extra="forbid"`); si `precio` llega y es distinto del actual MUST actualizarlo y agregar una línea en `historial_precio_repuesto` (anterior, nuevo, actor) **en la misma transacción** (RN-20, RT-TX-04); si el precio no cambia no MUST quedar línea (RN-20). El repuesto inexistente o dado de baja MUST responder 404.

#### Scenario: Precio actualizado con línea de historial
- **WHEN** se envía `PATCH /repuestos/{id}` con un precio distinto del actual
- **THEN** el precio cambia, `historial_precio_repuesto` tiene una línea con `precio_anterior` y `precio_nuevo` correctos, y la respuesta es 200

#### Scenario: Precio igual no deja línea
- **WHEN** se envía `PATCH /repuestos/{id}` con el mismo precio actual (con o sin descripción)
- **THEN** la respuesta es 200 y `historial_precio_repuesto` no tiene líneas nuevas

#### Scenario: Sólo descripción
- **WHEN** se envía `PATCH /repuestos/{id}` con sólo `descripcion`
- **THEN** cambia la descripción, el precio queda intacto y no hay línea de historial

### Requirement: Borrado lógico de repuesto

`DELETE /repuestos/{id}` MUST responder 204 **siempre** que el repuesto exista y esté vigente, aunque esté en órdenes abiertas (DD-21, RT-EQ-02); ya dado de baja MUST responder 404 (DD-22); inexistente MUST responder 404. Los datos se conservan (RN-16).

#### Scenario: Baja con órdenes abiertas
- **WHEN** se envía `DELETE /repuestos/{id}` de un repuesto que se usa en una orden `PENDIENTE`
- **THEN** la respuesta es 204 y el repuesto queda dado de baja

#### Scenario: Doble baja
- **WHEN** se envía `DELETE /repuestos/{id}` de un repuesto ya dado de baja
- **THEN** la respuesta es 404

### Requirement: Reposición de stock

`POST /repuestos/{id}/reponer` MUST aceptar `{cantidad > 0, motivo? ≤ 120}` (default «Reposición» — DD-29); `cantidad ≤ 0` o un `motivo` demasiado largo MUST responder 422; repuesto inexistente o dado de baja MUST responder 404. La reposición MUST pasar por el punto único de escritura: `stock += cantidad` y un `movimiento_stock` positivo con el motivo en la misma transacción (RN-14). La respuesta es 200 con el repuesto y su stock.

#### Scenario: Reposición exitosa
- **WHEN** se envía `POST /repuestos/{id}/reponer` con `{"cantidad": 10}`
- **THEN** la respuesta es 200, el stock sube 10 y hay un movimiento positivo con motivo «Reposición»

#### Scenario: Motivo propio
- **WHEN** se envía `POST /repuestos/{id}/reponer` con `{"cantidad": 5, "motivo": "Compra al proveedor"}`
- **THEN** el movimiento queda con ese motivo

#### Scenario: Cantidad no positiva
- **WHEN** se envía `POST /repuestos/{id}/reponer` con `{"cantidad": 0}` o negativa
- **THEN** la respuesta es 422 y el stock no cambia

### Requirement: Movimientos y precios de un repuesto

`GET /repuestos/{id}/movimientos` MUST devolver 200 con los movimientos de stock del repuesto (404 si no existe o está dado de baja) y `GET /repuestos/{id}/precios` MUST devolver 200 con el historial de precios en orden cronológico (404 si no existe o está dado de baja). Las tablas de auditoría son de sólo agregado (RN-15): sólo se insertan filas, nunca se modifican ni borran.

#### Scenario: Movimientos del repuesto
- **WHEN** se pide `GET /repuestos/{id}/movimientos` de un repuesto con «Stock inicial» y una reposición
- **THEN** la respuesta es 200 con los dos movimientos ordenados cronológicamente

#### Scenario: Precios del repuesto
- **WHEN** se pide `GET /repuestos/{id}/precios` de un repuesto cuyo precio se cambió una vez
- **THEN** la respuesta es 200 con la línea de historial (anterior y nuevo)
