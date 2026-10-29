# estados-orden Specification

## Purpose
Exponer el catálogo `estado_orden` como referencia de sólo lectura de la API: los estados posibles de una orden por posición, con su marca de estado final, sin que la API pueda crearlos, modificarlos ni borrarlos.

## Requirements

### Requirement: Consulta del catálogo por posición

`GET /estados-orden` MUST responder 200 a cualquier usuario autenticado, sin exigir rol, con la lista de estados del catálogo ordenada por `posicion`, cada uno con `codigo`, `descripcion`, `posicion` y `es_final`. Sin sesión MUST responder 401 y con el cambio de contraseña pendiente 403 (RN-19, C-17).

#### Scenario: Los cuatro estados por posición (C-17)
- **WHEN** un usuario autenticado consulta `GET /estados-orden` tras el seed
- **THEN** responde 200 con `PENDIENTE` (1), `EN_REPARACION` (2), `TERMINADA` (3) y `CANCELADA` (4), en ese orden, y sólo `TERMINADA` y `CANCELADA` con `es_final = true`

#### Scenario: Un cliente consulta el catálogo
- **WHEN** `cliente@example.com` consulta `GET /estados-orden`
- **THEN** responde 200 con los mismos cuatro estados

#### Scenario: Sin sesión (C-17)
- **WHEN** se consulta `GET /estados-orden` sin cookie
- **THEN** responde 401 sin devolver el catálogo

### Requirement: El catálogo no se edita desde la API

La API MUST NOT ofrecer ninguna operación que cree, modifique o borre filas de `estado_orden`: `/estados-orden` sólo declara `GET`, un método de escritura sobre esa ruta MUST ser rechazado sin ejecutar nada, y ninguna operación de órdenes MUST insertar, actualizar ni borrar estados del catálogo (RN-19, A-5).

#### Scenario: Intento de escritura
- **WHEN** se envía `POST`, `PATCH` o `DELETE` a `/estados-orden` con sesión ADMIN
- **THEN** la petición es rechazada (método no permitido), la especificación OpenAPI sólo publica `GET` para esa ruta y el catálogo sigue con las mismas filas

#### Scenario: Las transiciones no tocan el catálogo
- **WHEN** se crean, inician, terminan y cancelan órdenes
- **THEN** las filas de `estado_orden` son exactamente las mismas antes y después

### Requirement: El contrato de estados coincide con el catálogo

Los valores de estado que acepta el contrato de la API (filtro de `GET /ordenes`) MUST coincidir con los códigos que carga el seed en el catálogo; un estado que no está en el contrato MUST responder 422 y un estado que no está en el catálogo MUST ser rechazado por la base (RN-19).

#### Scenario: Contrato y catálogo alineados
- **WHEN** se comparan los valores del filtro `estado` con las filas del catálogo tras el seed
- **THEN** son los mismos cuatro códigos

#### Scenario: Filtro con un estado inventado
- **WHEN** se lista `GET /ordenes?estado=PERDIDA`
- **THEN** responde 422
