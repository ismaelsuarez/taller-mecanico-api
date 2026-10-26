# Spec Delta

## Purpose

Define el script `seed.py` como parte de la puesta en marcha: vacía las tablas y carga el estado inicial conocido del taller (catálogo de estados, usuarios con roles, clientes y vehículos, repuestos con sus movimientos de stock inicial, dos órdenes de trabajo con sus historiales, historial de precios y evento de seguridad), de forma idempotente y sin exponer credenciales reales.

## ADDED Requirements

### Requirement: Seed idempotente que vacía y recarga

`seed.py` MUST vaciar las tablas en orden seguro de dependencias y recargar el estado inicial conocido. Correrlo dos veces seguidas MUST dejar la base en el mismo estado lógico (mismos datos de negocio, sin duplicados).

#### Scenario: Dos corridas consecutivas
- **WHEN** se ejecuta `python seed.py` dos veces seguidas sobre la misma base migrada
- **THEN** ambas terminan sin error y los datos de negocio finales son idénticos a los de una sola corrida

#### Scenario: Seed sobre base sin migrar
- **WHEN** se ejecuta `python seed.py` sobre una base sin las tablas
- **THEN** el script informa claramente que falta migrar (no un traceback crudo)

### Requirement: Catálogo de estados cargado primero

El seed MUST cargar primero la tabla `estado_orden` con `PENDIENTE` (posición 1), `EN_REPARACION` (2), `TERMINADA` (3, final) y `CANCELADA` (4, final), cada uno con su descripción, antes que cualquier orden de trabajo.

#### Scenario: Catálogo presente antes de las órdenes
- **WHEN** el seed termina
- **THEN** `estado_orden` tiene las cuatro filas con sus posiciones y banderas `es_final`

### Requirement: Usuarios y roles iniciales

El seed MUST crear los usuarios de la consigna con sus roles vigentes en `asignacion_rol`: `admin@example.com` y `admin2@example.com` (ADMIN), `recepcion@example.com` (RECEPCION), `mecanico@example.com` y `mecanico2@example.com` (MECANICO), `cliente@example.com` (CLIENTE) y `nuevo@example.com` (MECANICO con `debe_cambiar_password = true`). Las contraseñas son de mentira, viven sólo en `seed.py` y se guardan hasheadas con bcrypt (costo desde la configuración).

#### Scenario: Siete usuarios con roles
- **WHEN** el seed termina
- **THEN** existen los siete usuarios con sus roles vigentes y `nuevo@example.com` tiene `debe_cambiar_password = true`

#### Scenario: Contraseñas sólo en el seed
- **WHEN** se revisa el repositorio
- **THEN** la contraseña en texto plano de los usuarios del seed aparece únicamente dentro de `seed.py` y no en configuración, migraciones ni documentación

### Requirement: Clientes y vehículos iniciales

El seed MUST crear a Laura con usuario (`cliente@example.com`) y dos vehículos, y a Jorge sin usuario y con un vehículo. El vehículo `id = 2`, patente `AC456EF`, MUST ser de Laura.

#### Scenario: Fichas y vehículos
- **WHEN** el seed termina
- **THEN** Laura tiene su usuario vinculado y dos vehículos, y Jorge tiene un vehículo sin usuario vinculado

### Requirement: Repuestos con movimiento de stock inicial

El seed MUST crear los repuestos de la tabla de la consigna (Filtro de aceite `FIL-001` 8500.00 stock 10, Pastillas de freno `FRE-010` 32000.00 stock 4, Bujía `BUJ-014` 6500.00 stock 2, Aceite 5W30 `ACE-530` 12000.00 stock 20) y, por cada uno, un movimiento «Stock inicial» con `usuario_id` de `admin@example.com` que explique exactamente su stock.

#### Scenario: Stock coherente con movimientos
- **WHEN** se suma el `cantidad` de los movimientos de stock inicial de cada repuesto
- **THEN** el total coincide con la columna `stock` del repuesto

### Requirement: Órdenes de trabajo del seed

El seed MUST crear la orden 1 (`PENDIENTE`, «Cambio de aceite y filtro», primer vehículo de Laura; 1 × Filtro de aceite + 4 × Aceite 5W30; total 56500.00) y la orden 2 (`EN_REPARACION`, «Falla de encendido», vehículo de Jorge, `mecanico_id` = `mecanico@example.com`; 4 × Bujía; total 26000.00), con sus ítems y el precio unitario copiado del repuesto.

#### Scenario: Orden 1 pendiente con dos ítems
- **WHEN** el seed termina
- **THEN** la orden 1 está `PENDIENTE` con dos ítems cuyos precios unitarios coinciden con los repuestos y cuyo total es 56500.00

#### Scenario: Orden 2 en reparación con faltante de stock
- **WHEN** el seed termina
- **THEN** la orden 2 está `EN_REPARACION`, asignada a `mecanico@example.com`, con 4 bujías pedidas cuando el stock del repuesto es 2

### Requirement: Historiales coherentes con las órdenes

El seed MUST cargar el historial de estados: orden 1 y orden 2 con línea `null → PENDIENTE` por `recepcion@example.com`, y orden 2 además con `PENDIENTE → EN_REPARACION` por `mecanico@example.com`. También una línea de historial de precios del filtro de aceite de 8000.00 a 8500.00.

#### Scenario: Historial de estados del seed
- **WHEN** se consulta el historial de estados de la orden 2
- **THEN** tiene dos líneas en orden: alta por recepción e inicio por el mecánico

#### Scenario: Historial de precios del filtro
- **WHEN** se consulta el historial de precios del filtro de aceite
- **THEN** tiene una línea de 8000.00 a 8500.00 con `usuario_id` del admin

### Requirement: Evento de seguridad del sistema

El seed MUST insertar una fila en `evento_seguridad` con actor `SISTEMA` y acción «Carga de los datos iniciales».

#### Scenario: Evento del sistema
- **WHEN** el seed termina
- **THEN** existe un evento de seguridad cuyo actor es el texto `SISTEMA` y cuya acción describe la carga inicial

### Requirement: Seed sin secretos ni credenciales

`seed.py` MUST NOT contener claves de firma, contraseñas de la base ni ningún otro secreto del entorno. Las contraseñas de los usuarios del seed son datos de prueba que sólo viven en ese archivo.

#### Scenario: Revisión de secretos
- **WHEN** se busca en `seed.py` el valor de `JWT_SECRET` o de `POSTGRES_PASSWORD`
- **THEN** no hay resultados
