# modelo-datos Specification

## Purpose
Define el esquema relacional completo del taller con los nombres de tablas y columnas obligatorios de la consigna, los tipos correctos (dinero NUMERIC, fechas timestamptz), las restricciones CHECK/UNIQUE, los tres índices únicos parciales para borrado lógico, el catálogo de estados de orden y las relaciones navegables en ambos extremos.

## Requirements

### Requirement: Nombres obligatorios de tablas y columnas

El esquema MUST contener exactamente las tablas `usuario`, `asignacion_rol`, `intento_acceso`, `evento_seguridad`, `cliente`, `vehiculo`, `repuesto`, `estado_orden`, `orden_trabajo`, `item_orden`, `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto`, con los nombres de columna fijados en la consigna (se pueden agregar columnas, no quitar ni renombrar). La clase del historial de precios MUST llamarse `HistorialPrecio` con tabla `historial_precio_repuesto` (IN-02).

#### Scenario: Las trece tablas existen
- **WHEN** se consulta el catálogo de tablas del esquema de la aplicación
- **THEN** aparecen las 13 tablas con los nombres exactos de la consigna

#### Scenario: Clase y tabla del historial de precios
- **WHEN** se inspecciona la clase del historial de precios de repuestos
- **THEN** la clase es `HistorialPrecio` y su tabla es `historial_precio_repuesto`

### Requirement: Tipos de dinero y fecha

Todo campo de dinero MUST ser `NUMERIC` en la base y `Decimal` en Python (nunca `float`). Todas las fechas y marcas de tiempo MUST ser `timestamptz`.

#### Scenario: Dinero como NUMERIC
- **WHEN** se consulta el tipo de las columnas `precio`, `total`, `precio_unitario`, `precio_anterior` y `precio_nuevo`
- **THEN** su tipo es NUMERIC con precisión (10,2) o (12,2) según la columna

#### Scenario: Fechas con zona horaria
- **WHEN** se consulta el tipo de las columnas de fecha (`cuando`, `desde`, `vence_en`, `revocada_en`, `borrado_en`, `creada_en`, `password_cambiada_en`)
- **THEN** su tipo es timestamptz

### Requirement: Restricciones CHECK del modelo

El esquema MUST imponer: `asignacion_rol.rol` sólo con valores `ADMIN`, `RECEPCION`, `MECANICO` o `CLIENTE`; `vehiculo.anio` entre 1950 y 2100; `repuesto.precio > 0`; `repuesto.stock >= 0`; `orden_trabajo.total >= 0`; `item_orden.cantidad > 0`; `item_orden.precio_unitario > 0`; `movimiento_stock.cantidad <> 0`; `historial_precio_repuesto.precio_nuevo > 0` y `precio_nuevo <> precio_anterior`.

#### Scenario: Rol inválido rechazado
- **WHEN** se intenta insertar una asignación de rol con valor fuera del conjunto permitido
- **THEN** la base rechaza la escritura por la restricción CHECK

#### Scenario: Precio negativo rechazado
- **WHEN** se intenta insertar un repuesto con precio menor o igual a cero
- **THEN** la base rechaza la escritura por la restricción CHECK

#### Scenario: Historial de precio sin cambio rechazado
- **WHEN** se intenta insertar una línea de historial de precios con `precio_nuevo` igual a `precio_anterior`
- **THEN** la base rechaza la escritura por la restricción CHECK

### Requirement: Tres índices únicos parciales

El esquema MUST tener exactamente tres índices únicos parciales: `asignacion_rol (usuario_id, rol) WHERE revocada_en IS NULL`, `vehiculo (patente) WHERE borrado_en IS NULL` y `repuesto (codigo) WHERE borrado_en IS NULL`. Deben permitir que un registro borrado lógicamente no choque con uno vigente al reutilizar patente o código.

#### Scenario: Un solo rol abierto por usuario y rol
- **WHEN** un usuario ya tiene una asignación de `ADMIN` sin revocar y se intenta crear otra igual sin revocar
- **THEN** la base rechaza la escritura por el índice único parcial

#### Scenario: Patente reutilizada tras borrado lógico
- **WHEN** un vehículo con patente `AC456EF` está dado de baja (`borrado_en` con valor) y se intenta crear otro vehículo vigente con la misma patente
- **THEN** la escritura es admitida por el índice único parcial

#### Scenario: Código de repuesto en dos vigentes
- **WHEN** dos repuestos no dados de baja tienen el mismo `codigo`
- **THEN** la base rechaza el segundo por el índice único parcial

### Requirement: Índice en cada clave foránea

Cada columna que es clave foránea MUST tener un índice, porque PostgreSQL no lo crea automáticamente.

#### Scenario: FKs indexadas
- **WHEN** se lista el catálogo de índices del esquema
- **THEN** cada columna usada como clave foránea tiene al menos un índice que la encabeza

### Requirement: Catálogo estado_orden

La tabla `estado_orden` MUST usar `codigo` como clave primaria (no `id`), con columnas `descripcion`, `posicion` (única) y `es_final`. `orden_trabajo.estado` MUST ser clave foránea a `estado_orden.codigo` (no un CHECK con la lista de estados — RN-19). La tabla debe poder quedar vacía sin romper el esquema.

#### Scenario: Estado inexistente rechazado por FK
- **WHEN** se intenta insertar una orden de trabajo con un `estado` que no es fila del catálogo
- **THEN** la base rechaza la escritura por la clave foránea

#### Scenario: Catálogo con posición única
- **WHEN** se intentan insertar dos estados con la misma `posicion`
- **THEN** la base rechaza la segunda escritura

### Requirement: Relaciones navegables en ambos extremos

Cada relación que la aplicación lea MUST ser navegable desde ambos lados. En particular `Usuario.cliente` MUST devolver un objeto opcional (no una lista) y `Cliente.usuario` MUST ser el usuario dueño de la ficha.

#### Scenario: Cliente con usuario opcional
- **WHEN** se carga un `Cliente` que tiene `usuario_id` con valor
- **THEN** el atributo de navegación `usuario` devuelve el `Usuario` correspondiente

#### Scenario: Usuario con una sola ficha de cliente
- **WHEN** se carga un `Usuario` que tiene una ficha de cliente asociada
- **THEN** el atributo de navegación `cliente` devuelve un objeto `Cliente` (o nulo), nunca una lista

### Requirement: Unicidad garantizada por la base

La unicidad de correo de usuario, documento de cliente y de los tres índices parciales MUST estar garantizada por restricciones de la base (UNIQUE o índice único parcial), no por consultas previas de la aplicación (RN-01, regla S-2).

#### Scenario: Correo duplicado rechazado por la base
- **WHEN** se intentan insertar dos usuarios con el mismo `email`
- **THEN** la base rechaza el segundo por la restricción UNIQUE
