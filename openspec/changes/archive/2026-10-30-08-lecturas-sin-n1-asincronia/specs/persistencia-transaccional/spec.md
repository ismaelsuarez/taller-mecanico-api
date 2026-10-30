# Spec Delta

## ADDED Requirements

### Requirement: Detalle de una orden con número fijo de consultas

El detalle de una orden (`GET /ordenes/{id}` y el método de repositorio que lo trae) MUST resolverse con un **número fijo de consultas** que no crece con la cantidad de ítems ni con la cantidad de líneas de historial (RT-TX-06, C-15): la orden, su vehículo, su cliente, sus ítems con su repuesto y su historial se piden en consultas contadas, declaradas en el repositorio, sin ninguna consulta adicional por fila.

#### Scenario: Mismo número de consultas con 2 y con 4 ítems (C-15)
- **WHEN** con `SQL_ECHO=true` se pide el detalle de una orden de 2 ítems y el de otra de 4 ítems
- **THEN** ambas respuestas se resuelven con exactamente la misma cantidad de consultas

#### Scenario: Una consulta por relación, no por fila
- **WHEN** una orden tiene ítems de muchos repuestos distintos y varias líneas de historial
- **THEN** el número de consultas no aumenta por cada ítem ni por cada línea: se repiten las mismas consultas iniciales de cualquier orden

#### Scenario: La evidencia queda guardada
- **WHEN** se revisa la entrega del proyecto
- **THEN** el repositorio contiene el fragmento de consola con las consultas del detalle de una orden de 2 ítems y de otra de 4 ítems, producido con `SQL_ECHO=true`

## MODIFIED Requirements

### Requirement: Un repositorio por entidad con precarga declarada

Cada entidad leída o escrita por un módulo MUST tener su repositorio, con métodos nombrados por lo que traen; toda relación que una respuesta lee MUST precargarse dentro del método del repositorio que la trae, sin depender de la carga perezosa. Ningún servicio ni router MUST ejecutar consultas SQL directamente sobre la sesión (RT-TX-05).

#### Scenario: Detalle de orden sin carga perezosa
- **WHEN** el servicio obtiene el detalle de una orden y la sesión ya no admite cargas implícitas
- **THEN** vehículo, cliente, ítems, repuesto de cada ítem e historial están disponibles sin consultas adicionales

#### Scenario: Servicios sin SQL
- **WHEN** se inspeccionan los `service.py` y `router.py` de los módulos con datos
- **THEN** ninguno ejecuta `execute` ni construye consultas sobre la sesión: todas viven en repositorios

#### Scenario: Ninguna respuesta consulta por fila
- **WHEN** se piden los listados y los detalles que traen relaciones (por ejemplo `GET /ordenes`, `GET /clientes` y `GET /ordenes/{id}`) con la base registrando las consultas
- **THEN** la cantidad de consultas no crece con la cantidad de filas ni con la de ítems devueltos
