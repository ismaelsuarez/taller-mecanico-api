# Spec Delta

## Purpose

Define el CRUD de clientes y vehículos: alta y lectura de clientes con sus vehículos, alta de vehículos con patente única entre vigentes y borrado lógico de vehículos con control de órdenes abiertas.

## ADDED Requirements

### Requirement: Alta de cliente

`POST /clientes` MUST crear una ficha de cliente y responder 201 con el cliente creado; un `documento` ya existente MUST responder 409 con mensaje propio (RN-01); un cuerpo que no cumple el contrato MUST responder 422. La unicidad se garantiza con la base, no con una consulta previa (S-2).

#### Scenario: Cliente creado
- **WHEN** se envía `POST /clientes` con un documento nuevo
- **THEN** la respuesta es 201 con el cliente (incluido su `id`)

#### Scenario: Documento duplicado
- **WHEN** se envía `POST /clientes` con un documento ya registrado
- **THEN** la respuesta es 409 con un mensaje propio en español

### Requirement: Detalle de cliente con sus vehículos

`GET /clientes/{id}` MUST responder 200 con el cliente y su lista de vehículos **vigentes** (precargados, sin consulta N+1 — T-10); un id inexistente MUST responder 404.

#### Scenario: Cliente con vehículos
- **WHEN** se pide `GET /clientes/{id}` de un cliente con dos vehículos vigentes y uno dado de baja
- **THEN** la respuesta incluye los dos vehículos vigentes y no el dado de baja

#### Scenario: Cliente inexistente
- **WHEN** se pide `GET /clientes/{id}` con un id que no existe
- **THEN** la respuesta es 404 con un mensaje propio

### Requirement: Alta de vehículo bajo un cliente

`POST /clientes/{id}/vehiculos` MUST crear un vehículo del cliente y responder 201; el cliente de la ruta debe existir (404); una patente **vigente** repetida MUST responder 409 (índice único parcial — RN-01); un cuerpo inválido (por ejemplo `anio` fuera de rango) MUST responder 422.

#### Scenario: Vehículo creado
- **WHEN** se envía `POST /clientes/{id}/vehiculos` con una patente nueva
- **THEN** la respuesta es 201 con el vehículo

#### Scenario: Patente vigente repetida
- **WHEN** se envía `POST /clientes/{id}/vehiculos` con una patente que ya tiene un vehículo vigente
- **THEN** la respuesta es 409 con un mensaje propio

#### Scenario: Cliente de la ruta inexistente
- **WHEN** se envía `POST /clientes/{id}/vehiculos` con un `id` de cliente inexistente
- **THEN** la respuesta es 404

### Requirement: Borrado lógico de vehículo

`DELETE /vehiculos/{id}` MUST hacer borrado lógico (`borrado_en`) y responder 204; un vehículo ya dado de baja MUST responder 404 (DD-22, RT-EQ-03); un vehículo con **órdenes abiertas** (estado cuya fila del catálogo tiene `es_final = false`) MUST responder 409 (RN-16); un vehículo inexistente MUST responder 404.

#### Scenario: Vehículo dado de baja
- **WHEN** se envía `DELETE /vehiculos/{id}` de un vehículo sin órdenes abiertas
- **THEN** la respuesta es 204 y el vehículo queda con `borrado_en` con valor; sus datos se conservan

#### Scenario: Vehículo con orden abierta
- **WHEN** se envía `DELETE /vehiculos/{id}` de un vehículo con una orden `PENDIENTE` o `EN_REPARACION`
- **THEN** la respuesta es 409 y el vehículo sigue vigente

#### Scenario: Doble baja
- **WHEN** se envía `DELETE /vehiculos/{id}` de un vehículo ya dado de baja
- **THEN** la respuesta es 404

#### Scenario: Patente reutilizable tras la baja
- **WHEN** un vehículo con patente `AC456EF` fue dado de baja y otro cliente registra la misma patente
- **THEN** la respuesta es 201 (el índice único parcial sólo cubre los vigentes)
