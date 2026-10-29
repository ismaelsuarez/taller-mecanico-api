# Spec Delta

## ADDED Requirements

### Requirement: Intento de acceso como única escritura fuera de la transacción de su petición

La escritura de `intento_acceso` MUST ser la única del sistema que usa una sesión y una transacción distintas de las de su petición; toda otra escritura MUST compartir la sesión de su petición y confirmarse con su Unit of Work. El código MUST declarar en un comentario esa excepción, por qué existe y su costo: deja filas aunque la petición falle.

#### Scenario: Una sola fuente de sesiones adicionales
- **WHEN** se inspecciona el código de la aplicación en busca de lugares que abren sesiones nuevas a partir de la fábrica de sesiones
- **THEN** sólo existen la sesión por petición y la sesión propia de los intentos de acceso, y esta última sólo alimenta al Unit of Work de intentos de acceso

#### Scenario: Excepción y costo declarados en el código
- **WHEN** se lee el código que crea la sesión propia de los intentos y el Unit of Work que los confirma
- **THEN** un comentario dice que es la única escritura que no comparte la transacción de su petición, que existe porque el fallo que se cuenta es el mismo que revierte la petición, y que su costo es dejar filas aunque la petición falle

### Requirement: Los fallos de C-05 quedan registrados en intento_acceso

Tras cinco logins fallidos seguidos del mismo correo e IP y un sexto bloqueado, `intento_acceso` MUST contener, confirmadas y visibles desde otra sesión, una fila con `exito=false` por cada uno de los cinco fallos y otra por el sexto (429), con su correo, IP y fecha; ninguno de esos intentos MUST registrarse como exitoso.

#### Scenario: Cinco fallos y el bloqueo observables desde otra sesión
- **WHEN** después de C-05 (cinco 401 y un 429 con `Retry-After`) se consulta `intento_acceso` desde una sesión distinta de la de la API
- **THEN** hay exactamente seis filas nuevas de ese correo e IP con `exito=false`, en el orden en que llegaron, y ninguna fila de la petición rechazada se perdió por el rollback de su transacción normal

#### Scenario: El evento del bloqueo no reemplaza al intento
- **WHEN** el sexto intento responde 429
- **THEN** además de su fila en `intento_acceso` queda un único evento «Login bloqueado por demasiados intentos» con el correo intentado como actor, y los cinco 401 no generan eventos de seguridad
