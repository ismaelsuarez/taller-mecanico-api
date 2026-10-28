# Spec Delta

## Purpose

Definir quién puede usar cada ruta de la API: identidad por cookie con 401, bloqueo del grupo protegido con cambio de contraseña pendiente, permisos decididos con los roles vigentes en la base en cada petición (403), la matriz RBAC de las rutas existentes, la firma de auditoría con el usuario autenticado y las rutas de lo propio (`/mis-vehiculos`, `/mis-ordenes`).

## ADDED Requirements

### Requirement: Toda ruta protegida exige una sesión válida

Las rutas del grupo protegido MUST responder 401 con mensaje humano en español ante cookie ausente, `Authorization: Bearer` sin cookie, token inválido o vencido, usuario inexistente o inactivo, y ante un `iat` anterior a `password_cambiada_en` sin truncar (RN-07). La lectura usa exclusivamente la cookie `access_token`; ningún fallo de este control expone datos ni ejecuta el handler.

#### Scenario: Sin cookie o con Bearer
- **WHEN** se llama a una ruta protegida sin cookie, o sólo con `Authorization: Bearer`
- **THEN** responde 401 en español y no ejecuta el handler ni devuelve datos del recurso

#### Scenario: Token alterado, vencido o de un usuario inexistente/inactivo
- **WHEN** la cookie trae una firma inválida, un token vencido, o el usuario ya no existe o está inactivo
- **THEN** responde 401 con el mismo formato, sin escrituras y sin datos internos

#### Scenario: Token anterior al último cambio de contraseña
- **WHEN** el `iat` del token es anterior a `password_cambiada_en`, incluso con la diferencia limitada a la fracción de un segundo
- **THEN** responde 401 sin esperar a que el token venza por su `exp`

### Requirement: El cambio de contraseña pendiente bloquea el grupo protegido

Mientras `debe_cambiar_password` sea verdadero, cada ruta del grupo protegido MUST responder 403 con mensaje humano (RN-06). `GET /health/live`, `GET /health/ready`, `POST /auth/registro`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/yo` y `POST /auth/cambiar-password` siguen disponibles. El control MUST estar montado una sola vez sobre el grupo protegido (DD-10).

#### Scenario: Usuario con cambio pendiente
- **WHEN** un usuario con `debe_cambiar_password = true` llama con sesión válida a cualquier ruta protegida
- **THEN** responde 403 en español sin ejecutar el handler
- **AND** `/auth/yo` y `/auth/cambiar-password` responden con normalidad

#### Scenario: Después de cambiar la contraseña
- **WHEN** el usuario cambia su contraseña y repite la misma petición con la cookie nueva
- **THEN** la ruta protegida responde según su contrato y la cookie anterior obtiene 401

### Requirement: Los permisos se deciden con los roles vigentes en la base en cada petición

`requiere_rol` MUST consultar las filas vigentes de `asignacion_rol` (no revocadas y sin vencer) en cada petición y responder 403 cuando el rol requerido no está vigente, sin importar los roles que traiga el token (RN-04). Los roles del JWT son informativos. Un 403 por permiso MUST llevar mensaje humano en español y nunca texto interno de la base.

#### Scenario: Revocación con la sesión abierta
- **WHEN** a un usuario se le revoca un rol y su cookie sigue siendo válida, y en la petición siguiente usa una ruta que exigía ese rol
- **THEN** responde 403 en la petición siguiente sin reescribir el token ni esperar a su vencimiento (C-07)

#### Scenario: Rol vencido con token todavía vigente
- **WHEN** la asignación del rol venció pero el JWT emitido antes todavía es válido
- **THEN** la ruta protegida que exige ese rol responde 403

#### Scenario: Token con roles que ya no corresponden
- **WHEN** el token contiene un rol que el usuario ya no tiene vigente, o el usuario tiene un rol vigente que el token no menciona
- **THEN** la decisión se toma con la base: se permite si el rol está vigente y se deniega si no lo está, sin modificar el token

### Requirement: Matriz de permisos de las rutas de datos existentes

Las rutas de clientes y vehículos (`POST /clientes`, `GET /clientes/{id}`, `POST /clientes/{id}/vehiculos`, `DELETE /vehiculos/{id}`) MUST exigir ADMIN o RECEPCION. Las de lectura de repuestos (`GET /repuestos`, `GET /repuestos/{id}`) MUST exigir ADMIN, RECEPCION o MECANICO, y las de escritura (`POST /repuestos`, `PATCH /repuestos/{id}`, `DELETE /repuestos/{id}`, `POST /repuestos/{id}/reponer`, `GET /repuestos/{id}/movimientos`, `GET /repuestos/{id}/precios`) MUST exigir ADMIN. Quien no tenga el rol vigente recibe 403; sin sesión, 401.

#### Scenario: Recepción y taller en clientes
- **WHEN** una sesión RECEPCION crea un cliente y una sesión ADMIN consulta su detalle
- **THEN** ambas responden según el contrato de la ruta (201 y 200)

#### Scenario: Personal sin permiso sobre clientes
- **WHEN** una sesión MECANICO o CLIENTE llama a `POST /clientes` o a `GET /clientes/{id}`
- **THEN** responde 403 y no se ejecuta el handler

#### Scenario: Escritura de repuestos sólo para ADMIN (C-18)
- **WHEN** una sesión RECEPCION cambia el precio o la descripción de un repuesto
- **THEN** responde 403 sin modificar precio, descripción ni historial

#### Scenario: Lectura de repuestos para el personal
- **WHEN** sesiones ADMIN, RECEPCION o MECANICO listan o consultan repuestos
- **THEN** responden con normalidad; una sesión CLIENTE recibe 403

### Requirement: La auditoría se firma con el usuario autenticado

El reemplazo del actor temporal (T-4) MUST sustituir `actor_temporal` por el usuario de la sesión en toda escritura de auditoría que hoy firma el admin del seed (`movimiento_stock`, `historial_precio_repuesto`). Con sesión válida el `usuario_id` corresponde al usuario autenticado; sin sesión la operación responde 401 y no se escribe nada. No debe quedar ninguna dependencia `actor_temporal` en los routers.

#### Scenario: Reposición con sesión del administrador
- **WHEN** un ADMIN autenticado repone stock o cambia un precio
- **THEN** el movimiento o la línea de historial llevan su `usuario_id`, no el del admin sembrado

#### Scenario: Sin sesión no hay escritura de auditoría
- **WHEN** se llama a cualquiera de esas escrituras sin cookie o sin el rol requerido
- **THEN** responde 401 o 403 y no se inserta movimiento, historial ni evento

### Requirement: Lo propio con sólo estar autenticado

`GET /mis-vehiculos` y `GET /mis-ordenes` MUST responder 200 con el envoltorio de paginación a cualquier usuario autenticado, sin exigir un rol (RN-17), devolviendo únicamente lo propio. `/mis-vehiculos` MUST mostrar sólo los vehículos vigentes y `/mis-ordenes` todas las órdenes de los vehículos del usuario, incluidas las de vehículos dados de baja (DD-28). Un usuario sin ficha de cliente MUST recibir 200 con una página vacía (SU-11).

#### Scenario: Cliente ve lo suyo y nada de lo ajeno
- **WHEN** un CLIENTE lista sus vehículos y sus órdenes
- **THEN** sólo aparecen los vehículos y órdenes de sus propios vehículos, con el envoltorio `{items, total, page, size, pages}`

#### Scenario: Usuario sin ficha de cliente
- **WHEN** un usuario sin relación con una ficha de cliente lista `/mis-vehiculos` o `/mis-ordenes`
- **THEN** responde 200 con `total = 0` y una página vacía

#### Scenario: Vehículo dado de baja
- **WHEN** un cliente consultado tiene vehículos dados de baja
- **THEN** `/mis-vehiculos` no los muestra y `/mis-ordenes` conserva sus órdenes

#### Scenario: Sin sesión
- **WHEN** se llaman sin cookie
- **THEN** responde 401 y no devuelve ningún dato
