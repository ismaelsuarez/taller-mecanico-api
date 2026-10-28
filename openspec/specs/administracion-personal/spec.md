# administracion-personal Specification

## Purpose
Definir la administración de personal y roles reservada al ADMIN: alta atómica de personal con contraseña provisoria, consulta, asignación y revocación de roles con vigencia y autoprotección, y el listado paginado de eventos de seguridad que deja el rastro de esas acciones.

## Requirements

### Requirement: Alta de personal atómica con contraseña provisoria

`POST /usuarios` (ADMIN) MUST recibir `{email, nombre, password_provisoria, rol}` con `extra="forbid"`, aceptando `rol` ∈ ADMIN/RECEPCION/MECANICO y rechazando `CLIENTE` con 422 (los clientes entran por el registro, DD-18). Una operación válida MUST responder 201 creando el usuario activo con `debe_cambiar_password = true`, su asignación de rol vigente con `otorgada_por` = administrador actual y el evento de seguridad, como una única operación confirmada en un solo Unit of Work. Correo repetido → 409 sin filas parciales. La respuesta no incluye `password_hash` ni la contraseña.

#### Scenario: Alta válida
- **WHEN** un ADMIN crea personal con un correo disponible y los datos válidos
- **THEN** responde 201, el usuario queda activo con cambio de contraseña pendiente, su rol vigente y el evento «Alta de personal con rol X» con el administrador como actor

#### Scenario: Rol CLIENTE o campo adicional
- **WHEN** el cuerpo trae `rol = "CLIENTE"` o un campo no permitido
- **THEN** responde 422 con mensaje humano, sin crear usuario, asignación ni evento

#### Scenario: Correo repetido
- **WHEN** el correo ya pertenece a un usuario existente
- **THEN** responde 409 con mensaje propio y no queda ninguna fila nueva

#### Scenario: Fallo al confirmar
- **WHEN** falla la confirmación de un alta válida
- **THEN** se revierten usuario, asignación y evento por igual y no se responde 201

### Requirement: Consulta de roles de un usuario

`GET /usuarios/{id}/roles` (ADMIN) MUST responder 200 con las asignaciones vigentes del usuario (rol, `desde`, `vence_en`, `otorgada_por`), sin revocadas ni vencidas y sin datos de contraseña. Un usuario inexistente MUST responder 404; sin el rol ADMIN, 403.

#### Scenario: Listado para el administrador
- **WHEN** un ADMIN consulta los roles de un usuario con una asignación vigente y otra revocada
- **THEN** sólo aparece la vigente, con su vencimiento si lo tiene

#### Scenario: Usuario inexistente o sin permiso
- **WHEN** se pide un id inexistente, o la petición viene de una sesión que no es ADMIN
- **THEN** responde 404 o 403 respectivamente

### Requirement: Asignación de rol con vencimiento opcional

`POST /usuarios/{id}/roles` (ADMIN) MUST recibir un `rol` válido y un `vence_en` opcional; el vencimiento MUST llegar con zona horaria y en el futuro, o responder 422 (RT-SE-11, no 409). Usuario inexistente → 404. Si existe una fila abierta **vencida** del mismo rol, MUST cerrarla (`revocada_en`) y abrir una nueva; si existe una fila abierta **vigente**, MUST responder 409 (RN-03, índice único parcial). Una operación válida responde 201 y registra «Rol X asignado a Y» con el administrador como actor.

#### Scenario: Asignación con vencimiento futuro válido
- **WHEN** se asigna un rol con `vence_en` con zona horaria posterior al instante actual
- **THEN** responde 201 y la fila queda abierta con ese vencimiento

#### Scenario: Vencimiento en el pasado o sin zona horaria
- **WHEN** `vence_en` es anterior al instante actual o carece de zona horaria
- **THEN** responde 422 con mensaje humano y no se modifica ninguna asignación

#### Scenario: Rol abierto duplicado
- **WHEN** el usuario ya tiene ese rol con una asignación abierta vigente
- **THEN** responde 409 con mensaje propio y no se crean ni se cierran filas

#### Scenario: Reasignar un rol vencido
- **WHEN** el usuario tiene ese rol con una asignación abierta cuyo `vence_en` ya pasó
- **THEN** la fila anterior queda cerrada (`revocada_en` no nulo) y se abre una nueva, conservando el historial

### Requirement: Revocación sin borrar la fila y autoprotección

`DELETE /usuarios/{id}/roles/{rol}` (ADMIN) MUST escribir `revocada_en` sin eliminar la fila y responder 200, registrando «Rol X revocado a Y». Usuario o asignación abierta inexistente → 404. MUST responder 409 cuando un administrador se revoca su propio rol ADMIN (RN-05) o cuando la revocación dejaría el sistema sin administradores vigentes. La revocación MUST surtir efecto en la siguiente petición de una sesión ya abierta (C-07).

#### Scenario: Revocación efectiva de inmediato
- **WHEN** un ADMIN revoca un rol de otro usuario que tiene la sesión abierta
- **THEN** responde 200, la fila queda con `revocada_en` y la siguiente petición de esa sesión a una ruta del rol revocado responde 403 (C-07)

#### Scenario: El administrador no se revoca su ADMIN (C-08)
- **WHEN** un ADMIN intenta revocarse su propio rol ADMIN
- **THEN** responde 409 con mensaje humano y su asignación sigue vigente

#### Scenario: No quedan administradores vigentes
- **WHEN** la revocación dejaría cero administradores vigentes
- **THEN** responde 409, no se escribe `revocada_en` y el sistema conserva al menos un ADMIN activo

#### Scenario: Sin asignación abierta
- **WHEN** el usuario no tiene ese rol en una asignación abierta
- **THEN** responde 404 y no modifica filas anteriores

### Requirement: Eventos de seguridad paginados

`GET /eventos` (ADMIN) MUST responder 200 con el envoltorio `{items, total, page, size, pages}` sobre `evento_seguridad`, cada item con `id`, `cuando`, `accion` y `actor`, en el orden de los mismos filtros que la página; `page` o `size` fuera de contrato → 422. Debe incluir las acciones registradas por DD-26 (altas de personal, asignaciones y revocaciones de rol, cambios de contraseña, logins bloqueados y carga de datos iniciales) y nunca contraseñas, tokens ni texto interno. Sin el rol ADMIN → 403.

#### Scenario: Listado autenticado como ADMIN
- **WHEN** un ADMIN pagina `/eventos` tras realizar altas y cambios de rol
- **THEN** los eventos aparecen con su actor y acción en español, con el envoltorio de paginación

#### Scenario: Página fuera de rango o sin permiso
- **WHEN** se pide una página más allá de la última, o la petición no es de un ADMIN
- **THEN** responde 422 con el mensaje propio de paginación o 403 respectivamente
