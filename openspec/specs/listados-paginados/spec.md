# listados-paginados Specification

## Purpose
Define el envoltorio de listados paginados que usan todos los endpoints de colección: estructura, validación de página y tamaño, total con los mismos filtros y búsqueda por descripción con parámetros ligados.

## Requirements

### Requirement: Envoltorio de paginación

Todo listado MUST devolver `{items, total, page, size, pages}` con `page` empezando en 1, `size` entre 1 y 100 (por defecto 20) y `pages = max(1, ceil(total / size))` (RT-PG-05).

#### Scenario: Listado con página y tamaño
- **WHEN** se pide `GET /repuestos?page=1&size=2` con 4 repuestos vigentes
- **THEN** la respuesta tiene 2 items, `total` 4, `page` 1, `size` 2 y `pages` 2

#### Scenario: Tamaño fuera de rango
- **WHEN** se pide un listado con `size=0`, `size=101` o `page=0`
- **THEN** la respuesta es 422

### Requirement: Página fuera de rango da 422

Pedir una página más allá de la última MUST responder 422 con el mensaje «La página N no existe: hay M» (RT-PG-05).

#### Scenario: Página que no existe
- **WHEN** se pide `GET /repuestos?page=3&size=2` con 4 resultados (2 páginas)
- **THEN** la respuesta es 422 con el mensaje «La página 3 no existe: hay 2»

### Requirement: Cero resultados, una página vacía

Con cero resultados el listado MUST devolver 200 con `items` vacío, `total` 0 y `pages` 1 (no 422) (RT-PG-05).

#### Scenario: Búsqueda sin coincidencias
- **WHEN** se pide `GET /repuestos?q=inexistente`
- **THEN** la respuesta es 200 con `items: []`, `total: 0`, `pages: 1`

### Requirement: total con los mismos filtros

`total` MUST contar los resultados con los mismos filtros que la página (la búsqueda `q` incluida) (RT-PG-05).

#### Scenario: Total filtrado
- **WHEN** hay 4 repuestos vigentes y se pide `GET /repuestos?q=freno&page=1&size=10`
- **THEN** `total` es 1 (sólo «Pastillas de freno delanteras») y `pages` es 1

### Requirement: Búsqueda con parámetros ligados

La búsqueda por descripción MUST usar parámetros ligados (nunca SQL armado por concatenación con datos del usuario) y ser «contiene» (RT-PG-06, SU-09). Un `q` con sintaxis de inyección MUST devolver lista vacía con `total` 0, nunca un error (C-16).

#### Scenario: Inyección en q
- **WHEN** se pide `GET /repuestos?q=' OR '1'='1`
- **THEN** la respuesta es 200 con una lista vacía y `total` 0
