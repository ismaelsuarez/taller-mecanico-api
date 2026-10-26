# contratos-estrictos Specification

## Purpose
Define los contratos de la API: entrada separada de los modelos con `extra="forbid"`, salidas sin `password_hash`, PATCH que aplica sólo los campos enviados, códigos de estado según la convención y garantía de que ninguna entrada inválida termina en 500.

## Requirements

### Requirement: Contratos de entrada estrictos y separados de los modelos

Cada contrato de entrada MUST estar declarado en `schemas.py`, separado del modelo de tabla, con `extra="forbid"`: un cuerpo con campos no declarados (por ejemplo `stock` en un PATCH de repuesto, o `rol` en un registro) MUST responder 422. Ninguna respuesta MUST incluir `password_hash`.

#### Scenario: Campo extra en un PATCH rechazado
- **WHEN** se envía un `PATCH /repuestos/{id}` con el campo `stock` en el cuerpo
- **THEN** la respuesta es 422 y el repuesto no se modifica

#### Scenario: Respuesta sin password_hash
- **WHEN** se crea un recurso o se lo lee con cualquier endpoint de este change
- **THEN** el cuerpo de la respuesta no contiene `password_hash`

### Requirement: PATCH parcial con exclude_unset

Un `PATCH` MUST aplicar sólo los campos enviados (`exclude_unset`): un cuerpo con un único campo válido no MUST modificar los demás campos del recurso.

#### Scenario: PATCH de sólo precio conserva la descripción
- **WHEN** se envía `PATCH /repuestos/{id}` con sólo `precio`
- **THEN** el precio cambia, la descripción queda intacta y —si el precio era distinto— aparece una línea en `historial_precio_repuesto`

### Requirement: Códigos de estado según la convención

Los endpoints MUST responder: 201 al crear, 204 al dar de baja, 404 si el recurso de la ruta no existe o ya fue dado de baja (DD-22), 409 si choca con lo guardado (RN-01, RN-16) y 422 si el cuerpo o los parámetros no cumplen el contrato (RT-PG-04).

#### Scenario: Repetido da 409
- **WHEN** se crea un cliente con un documento ya existente, o un vehículo con una patente vigente repetida, o un repuesto con un código vigente repetido
- **THEN** la respuesta es 409 con un mensaje propio en español

#### Scenario: Recurso inexistente da 404
- **WHEN** se pide, modifica o da de baja un id que no existe en la base
- **THEN** la respuesta es 404 con un mensaje propio en español

### Requirement: Ninguna entrada inválida termina en 500

Ninguna entrada inválida MUST terminar en 500 (RN-18): la validación vive en el contrato y los `IntegrityError` de la base se traducen a 409/422 con un mensaje propio en español, nunca texto interno de la base ni trazas (RT-EQ-01, S-9).

#### Scenario: Parámetro de ruta no entero
- **WHEN** se pide `GET /clientes/abc` (o cualquier parámetro de ruta no entero)
- **THEN** la respuesta es 422 sin ejecutar el handler (RT-PG-07)

#### Scenario: Cuerpo malformado
- **WHEN** se envía un JSON inválido o con tipos incorrectos a cualquiera de estos endpoints
- **THEN** la respuesta es 422 con un mensaje propio, nunca un 500
