# persistencia-transaccional Specification

## Purpose
Fijar el contrato de persistencia que exige la consigna (Ejercicio 6): la jerarquía de repositorios, el repositorio de sólo lectura del catálogo, el Unit of Work con sus responsables (quién crea, abre, confirma, revierte y cierra), las operaciones de varias escrituras en un solo bloque y el punto único de escritura de stock.

## Requirements

### Requirement: Repositorio base genérico con la clase del modelo

`BaseRepository[T]` MUST recibir en su constructor la sesión y la clase del modelo (los genéricos se borran en tiempo de ejecución) y ofrecer al menos `get_by_id`, `get_all`, `count`, `add`, `update` y `delete`. `add` y `update` MUST hacer `flush()` y ningún repositorio MUST llamar a `commit()`: lo escrito sólo queda confirmado cuando confirma el Unit of Work.

#### Scenario: add hace flush sin confirmar
- **WHEN** un repositorio agrega una entidad y la transacción se revierte sin pasar por el commit del Unit of Work
- **THEN** la entidad tuvo id asignado tras el `flush()` pero no existe en la base al revertir

#### Scenario: Ningún commit en repositorios
- **WHEN** se inspecciona el código de `app/core/repository.py` y de cada `app/modules/*/repository.py`
- **THEN** no existe ninguna llamada a `commit()`

### Requirement: Repositorio con borrado lógico

`SoftDeleteRepository[T]` MUST heredar de `BaseRepository[T]`, filtrar los dados de baja en `get_by_id`, `get_all` y `count`, y agregar `get_by_id_including_deleted` y `soft_delete`, que no existen en la clase base. `soft_delete` MUST marcar `borrado_en` sin borrar la fila.

#### Scenario: Un dado de baja deja de aparecer pero se conserva
- **WHEN** se da de baja un repuesto con `soft_delete`
- **THEN** `get_by_id` devuelve nulo, `get_by_id_including_deleted` lo devuelve con `borrado_en` y la fila sigue en la base

#### Scenario: La clase base no ofrece borrado lógico
- **WHEN** se inspecciona `BaseRepository`
- **THEN** no tiene `get_by_id_including_deleted` ni `soft_delete`

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

### Requirement: Catálogo con repositorio de sólo lectura

El catálogo `estado_orden` MUST tener un repositorio propio que NO hereda de `BaseRepository` (su clave primaria es `codigo`, no `id`) y que sólo ofrece lecturas: listar por posición y obtener por código. MUST NOT ofrecer `add`, `update` ni `delete`.

#### Scenario: Sin herencia ni escrituras
- **WHEN** se inspecciona el repositorio del catálogo
- **THEN** no es subclase de `BaseRepository` y no tiene métodos `add`, `update` ni `delete`

#### Scenario: Lectura por posición
- **WHEN** se listan los estados tras el seed
- **THEN** vuelven los cuatro estados ordenados por `posicion`

### Requirement: Unit of Work que confirma, revierte y no cierra la sesión

El `UnitOfWork` base MUST ser un gestor de contexto asincrónico que confirma al salir del bloque sin excepción, revierte si sale con una excepción y la propaga, revierte también si la confirmación falla, y MUST NOT cerrar la sesión, que la crea y la cierra la dependencia de sesión de la petición (RT-TX-03).

#### Scenario: Salida normal
- **WHEN** un servicio sale del bloque `async with uow` sin excepción
- **THEN** las escrituras del bloque quedan confirmadas y la sesión sigue abierta hasta el fin de la petición

#### Scenario: Excepción dentro del bloque
- **WHEN** una excepción de dominio sale del bloque después de varios `flush()`
- **THEN** ninguna escritura del bloque queda en la base y la excepción llega al traductor HTTP

#### Scenario: Falla al confirmar
- **WHEN** la confirmación lanza un error de la base
- **THEN** el Unit of Work revierte la transacción antes de propagar el error, en cualquier módulo

### Requirement: Un Unit of Work por módulo con la misma sesión

Cada módulo con datos (`usuarios`, `clientes`, `repuestos`, `ordenes`) MUST tener su Unit of Work, que compone los repositorios que sus operaciones necesitan, todos con la misma sesión. El de `ordenes` MUST incluir los repositorios de órdenes, ítems, historial, catálogo, vehículos y repuestos.

#### Scenario: Repositorios de una misma transacción
- **WHEN** se construye el Unit of Work de órdenes con una sesión
- **THEN** todos sus repositorios usan exactamente esa sesión

### Requirement: Quién construye y quién abre el Unit of Work

El router MUST construir el Unit of Work con una dependencia y pasarlo al servicio sin abrir; el servicio MUST abrirlo con `async with` y MUST NOT construirlo. Ningún código MUST confirmar fuera de un Unit of Work (B-8, RT-TX-02).

#### Scenario: Servicios que no construyen su UoW
- **WHEN** se inspeccionan los `service.py` de los cuatro módulos
- **THEN** ninguno instancia un Unit of Work: lo reciben por parámetro y lo abren con `async with`

#### Scenario: Commits sólo en el Unit of Work
- **WHEN** se busca `commit(` en `app/`, `main.py` y `seed.py`
- **THEN** la única llamada está en el `UnitOfWork` base

### Requirement: Operaciones de varias escrituras en un solo bloque

El registro (RN-02: usuario + rol `CLIENTE` + ficha), la terminación de una orden (RN-13: stock + movimientos + estado + historial) y el cambio de precio (RN-20: precio + línea de historial) MUST escribirse cada una dentro de un único bloque de Unit of Work: si cualquier escritura falla, no queda ninguna (RT-TX-04).

#### Scenario: Falla a mitad de la terminación
- **WHEN** la terminación falla después de descontar el stock del primer ítem
- **THEN** no queda ningún descuento, movimiento, cambio de estado ni línea de historial

#### Scenario: Falla a mitad del registro o del cambio de precio
- **WHEN** el registro falla al crear la ficha, o el cambio de precio falla al escribir el historial
- **THEN** no queda el usuario ni su rol, ni el precio nuevo sin su línea

### Requirement: Punto único de escritura de stock

El stock de un repuesto MUST cambiar sólo a través de una única operación de escritura que suma o resta la cantidad y agrega el movimiento correspondiente en la misma transacción; la usan el alta con stock inicial, la reposición y la terminación de órdenes (RN-14). Si el stock resultante fuera negativo, MUST rechazar la escritura con un conflicto de dominio (409), sin escribir nada.

#### Scenario: Un solo camino para el stock
- **WHEN** se inspecciona el código de `app/`
- **THEN** sólo la operación del punto único asigna `stock` de un repuesto ya creado

#### Scenario: Salida que dejaría stock negativo
- **WHEN** se pide una salida mayor que el stock disponible
- **THEN** la operación lanza un conflicto con mensaje humano, el stock no cambia y no se agrega el movimiento

### Requirement: Repositorios de las tablas de sólo agregado sólo agregan

El acceso desde la aplicación a `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` MUST ofrecer sólo operaciones de alta y de lectura: ningún repositorio de esas tablas MUST exponer modificación ni borrado (RN-15 en la capa de aplicación, además del disparador de la base).

#### Scenario: Sin operaciones de modificación ni borrado
- **WHEN** se inspeccionan los repositorios de las tres tablas de sólo agregado
- **THEN** ninguno ofrece operaciones de actualización, borrado ni borrado lógico, y ninguno hereda del repositorio genérico que las trae

#### Scenario: El alta sigue funcionando dentro de su bloque
- **WHEN** una operación de varias escrituras (cambio de precio, reposición o transición de una orden) agrega su línea de auditoría
- **THEN** la línea queda escrita en la misma transacción que el cambio que registra y se revierte con él si el bloque falla

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
