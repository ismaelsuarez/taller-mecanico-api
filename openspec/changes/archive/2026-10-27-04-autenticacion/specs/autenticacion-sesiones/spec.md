# Spec Delta

## Purpose

Permitir el registro y la autenticación de usuarios del taller mediante sesiones seguras en cookie, con intentos auditados y revocación de sesiones anteriores al cambio de contraseña, sin anticipar la autorización por roles.

## ADDED Requirements

### Requirement: Entradas de autenticación estrictas y seguras

Los contratos de autenticación MUST rechazar campos adicionales y contraseñas de más de 72 bytes UTF-8 con 422, sin eco de entradas ni secretos. El registro recibe `{email, password, nombre, documento, telefono}`; el login recibe `{email, password}`. Los campos actual y nueva del cambio también cumplen el límite.

#### Scenario: Límite medido en bytes
- **WHEN** una contraseña de registro, login o cambio contiene 36 caracteres `ñ` (72 bytes), y los demás datos son válidos
- **THEN** el límite de longitud no la rechaza y la operación continúa con sus reglas de autenticación
- **WHEN** contiene 37 caracteres `ñ` (74 bytes) o 73 caracteres ASCII
- **THEN** responde 422 antes de ejecutar bcrypt y sin escrituras derivadas de la operación

#### Scenario: Rol o campo adicional inyectado en el registro
- **WHEN** el cuerpo del registro incluye `rol` u otro campo no permitido
- **THEN** responde 422 con `detail: [{msg: mensaje_humano}]`, sin crear usuario, asignación, cliente o evento ni emitir cookie

#### Scenario: Error sin exposición de contraseña
- **WHEN** una petición de autenticación tiene JSON malformado, campos requeridos ausentes o tipos inválidos
- **THEN** responde 422 en español sin devolver contraseña, token, `input`, `ctx`, trazas ni mensajes internos

### Requirement: Registro de cliente atómico

`POST /auth/registro` MUST crear usuario, asignación CLIENTE, ficha de cliente y evento de registro como una única operación confirmada, con 201. `nombre` se usa en usuario y ficha. Correo o documento repetidos producen 409 sin apropiarse de una ficha existente ni conservar escrituras parciales.

#### Scenario: Alta válida con sesión iniciada
- **WHEN** se registra un correo y documento disponibles con datos válidos
- **THEN** devuelve 201, crea las cuatro entidades relacionadas y entrega `Set-Cookie: access_token` después de confirmar
- **AND** la cookie permite consultar `/auth/yo` y el cuerpo no contiene token ni hash

#### Scenario: Colisión de correo o documento
- **WHEN** el correo ya existe o el documento corresponde a una ficha existente, incluso sin usuario vinculado
- **THEN** devuelve 409 con mensaje humano propio, no emite cookie y no cambia las entidades existentes ni deja filas parciales

#### Scenario: Fallo al confirmar el registro
- **WHEN** falla una escritura o la confirmación final del registro
- **THEN** se revierte el conjunto completo y no se emite cookie de sesión ni respuesta de éxito

### Requirement: Login con respuesta pública sin token

`POST /auth/login` MUST responder 200 para una cuenta activa con credenciales correctas y límite disponible, iniciar sesión en cookie y devolver `mensaje`, `debe_cambiar_password` y `expira_en_segundos`. La bandera refleja al usuario y la duración refleja la configuración; el cuerpo nunca contiene el token.

#### Scenario: Inicio de sesión correcto
- **WHEN** un usuario activo sin cambio pendiente inicia sesión con duración configurada en 1800 segundos
- **THEN** recibe `{"mensaje":"Sesión iniciada","debe_cambiar_password":false,"expira_en_segundos":1800}`, cookie válida e intento exitoso confirmado

#### Scenario: Cuenta con cambio pendiente
- **WHEN** las credenciales son correctas y `debe_cambiar_password` es verdadero
- **THEN** el login responde 200 con esa bandera verdadera y permite usar `/auth/yo` y `/auth/cambiar-password`

### Requirement: Límite previo a la verificación de contraseña

El login MUST comprobar primero los fallos del par correo/IP en la ventana de 60 segundos posteriores a su último éxito. Con cinco o más fallos vigentes responde 429 con `Retry-After`, sin verificar contraseñas. El encabezado expresa los segundos hasta que salga de la ventana el fallo vigente más antiguo.

#### Scenario: Sexto intento bloqueado
- **WHEN** se envían seis intentos consecutivos del mismo par con contraseña incorrecta dentro de 60 segundos
- **THEN** los primeros cinco responden 401 y el sexto responde 429 con `Retry-After` positivo y sin bcrypt
- **AND** los cinco fallos y el resultado bloqueado quedan registrados; no hay cookie nueva

#### Scenario: Separación por correo e IP y vencimiento
- **WHEN** los fallos corresponden a otro correo, otra IP o quedaron fuera de los 60 segundos
- **THEN** no bloquean al par evaluado

#### Scenario: Login correcto reinicia el conteo sin borrar
- **WHEN** ocurre un login correcto antes de alcanzar el bloqueo y luego nuevos fallos del mismo par
- **THEN** los fallos anteriores al éxito permanecen en el historial pero dejan de contar para el límite

### Requirement: Fallos de login sin enumeración de cuentas

El login MUST responder 401 con «El correo o la contraseña no son correctos.» y tiempos semejantes ante correo inexistente o contraseña incorrecta. Una cuenta inactiva con contraseña correcta responde 401 con «Tu cuenta está desactivada. Comunicate con el taller para reactivarla.». Ninguno de esos resultados inicia sesión.

#### Scenario: Correo inexistente y contraseña incorrecta
- **WHEN** se comparan solicitudes válidas no bloqueadas para correo inexistente y para correo existente con contraseña incorrecta
- **THEN** sus cuerpos y códigos 401 son iguales y ambas realizan una verificación de contraseña de costo comparable, sin cookie

#### Scenario: Inactivo con contraseña correcta o incorrecta
- **WHEN** la cuenta está inactiva y la contraseña es correcta
- **THEN** responde el mensaje de cuenta desactivada y registra intento fallido
- **WHEN** la contraseña es incorrecta
- **THEN** responde el mensaje genérico de credenciales incorrectas y registra intento fallido

### Requirement: Intentos persistidos independientemente del resultado

Cada ejecución de login con entrada válida MUST registrar correo, IP, fecha y resultado en una transacción independiente confirmada, incluso ante 401, 429 o rollback de la petición. Un resultado bloqueado cuenta como fallido; el historial no se borra al reiniciar el conteo. Entradas rechazadas por validación no ejecutan el login.

#### Scenario: El rechazo no borra el intento
- **WHEN** el login termina en 401 o 429, o la transacción de su petición se revierte después de registrar el resultado
- **THEN** otra sesión de base observa el intento confirmado y las escrituras revertidas de la petición no quedan persistidas

#### Scenario: Falla la persistencia obligatoria del intento
- **WHEN** no puede confirmarse el intento de un login con credenciales correctas
- **THEN** no se emite cookie ni se anuncia una sesión iniciada

### Requirement: Eventos de seguridad de autenticación

El sistema MUST registrar «Alta de usuario cliente (registro)» con el correo nuevo como actor, «Cambio de contraseña» con el correo del usuario y «Login bloqueado por demasiados intentos» con el correo intentado. El login normal registra su intento sin duplicarlo como evento de seguridad.

#### Scenario: Eventos con actor correcto
- **WHEN** se confirma un registro o cambio de contraseña, o se devuelve un login bloqueado
- **THEN** existe el evento de la acción con el actor correspondiente, sin contraseñas ni token
- **AND** un registro o cambio revertido no deja su evento de éxito

### Requirement: Sesión exclusivamente en cookie segura

El JWT de sesión MUST contener `sub`, `iat` fraccional, `exp` y los roles vigentes al emitir, firmado con la clave fija configurada. Viaja sólo en la cookie `access_token`, HttpOnly, SameSite=Lax, Max-Age igual a la duración y Secure configurable. La lectura de autenticación usa sólo esa cookie.

#### Scenario: Atributos y configuración de cookie
- **WHEN** registro, login o cambio confirman una nueva sesión
- **THEN** la cookie tiene los atributos exigidos y la duración configurada, con Secure presente cuando está habilitado y ausente cuando está deshabilitado
- **AND** ningún cuerpo de respuesta contiene el JWT

#### Scenario: Bearer no sustituye a la cookie
- **WHEN** se llama a `/auth/yo` o cambio de contraseña con `Authorization: Bearer` pero sin cookie
- **THEN** responde 401 sin autenticar desde la cabecera

### Requirement: Validación de la identidad y vigencia de sesión

Las operaciones autenticadas MUST rechazar con 401 cookies ausentes, JWT inválidos, vencidos o con claims requeridos inválidos, usuarios inexistentes/inactivos y tokens emitidos antes de `password_cambiada_en`. La comparación temporal conserva fracciones de segundo; no basta confiar en los roles del JWT.

#### Scenario: Token o usuario no válido
- **WHEN** falta la cookie, se altera la firma, vence el token, faltan claims válidos, no existe el usuario o está inactivo
- **THEN** `/auth/yo` y cambio de contraseña responden 401 humano, sin datos internos ni escritura de cambio de contraseña

### Requirement: Identidad con roles actuales y roles emitidos

`GET /auth/yo` MUST devolver 200 con el usuario y dos conjuntos distinguibles: roles vigentes en la base y roles contenidos en su token, sin hash de contraseña. Un rol vigente no está revocado y no venció. Esta consulta no exige un rol específico.

#### Scenario: Roles cambiaron desde el login
- **WHEN** una asignación del usuario se revoca o vence después de emitir una cookie todavía válida
- **THEN** `/auth/yo` muestra la diferencia entre los roles actuales y los emitidos sin reescribir el token ni responder 403 por esa diferencia

### Requirement: Cambio de contraseña atómico con revocación inmediata

`POST /auth/cambiar-password` MUST verificar la contraseña actual; si es incorrecta, responde 401 sin cambios. Si es correcta, confirma el nuevo hash, `password_cambiada_en`, bandera falsa y evento como una unidad, responde 200 y emite cookie nueva. Las sesiones emitidas antes del cambio dejan de valer inmediatamente.

#### Scenario: Cambio dentro del mismo segundo
- **WHEN** un usuario inicia sesión y cambia correctamente su contraseña dentro del mismo segundo
- **THEN** la cookie nueva permite `/auth/yo`, la anterior obtiene 401 sin esperar y la contraseña anterior ya no permite login
- **AND** se limpia la bandera de cambio pendiente y persiste el evento

#### Scenario: Contraseña actual incorrecta o fallo de confirmación
- **WHEN** la contraseña actual es incorrecta
- **THEN** responde 401 sin alterar hash, timestamp, bandera, evento ni cookie
- **WHEN** falla la confirmación de un cambio válido
- **THEN** se revierten todos sus cambios y no se entrega cookie nueva

### Requirement: Logout público que elimina la cookie

`POST /auth/logout` MUST responder 200 y eliminar `access_token`, exista o no una sesión válida. No requiere una lista central de revocación de JWT ni cambia contraseñas.

#### Scenario: Cierre con y sin cookie
- **WHEN** se solicita logout con cookie o sin ella
- **THEN** responde 200 y envía la eliminación de la cookie con alcance compatible con su emisión
- **AND** el cliente que acepta la eliminación obtiene 401 al consultar `/auth/yo` sin enviar otra cookie

### Requirement: Cálculo de contraseñas sin bloquear ni retener conexión

El procesamiento de contraseñas MUST ejecutarse fuera del bucle de eventos y con concurrencia limitada por configuración. El cálculo del hash no debe retener una conexión de base en una transacción abierta; las sondas de salud siguen disponibles durante ese trabajo.

#### Scenario: Hashing y salud concurrentes
- **WHEN** se realizan operaciones de contraseña junto con peticiones a `/health/live`
- **THEN** el procesamiento respeta el límite configurado y no bloquea el bucle de eventos ni retiene una transacción para esperar bcrypt
