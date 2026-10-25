# salud-servicio Specification

## Purpose

Expone sondas que permiten distinguir un proceso vivo de uno listo para atender, de modo que una base caída no se confunda con un proceso que hay que reiniciar.

## Requirements

### Requirement: Sonda de vida

`GET /health/live` MUST responder 200 mientras el proceso esté en ejecución, sin consultar la base de datos, aunque la base no esté disponible. MUST NOT requerir sesión.

#### Scenario: Proceso vivo con base disponible
- **WHEN** se llama a `GET /health/live` con la base disponible
- **THEN** la respuesta es 200

#### Scenario: Proceso vivo con base caída
- **WHEN** se llama a `GET /health/live` con la base detenida
- **THEN** la respuesta es 200

### Requirement: Sonda de preparación

`GET /health/ready` MUST ejecutar una consulta mínima contra la base (`SELECT 1`) y responder 200 si la base contesta y 503 si no contesta. MUST NOT requerir sesión.

#### Scenario: Base disponible
- **WHEN** se llama a `GET /health/ready` con la base disponible
- **THEN** la respuesta es 200

#### Scenario: Base caída
- **WHEN** se llama a `GET /health/ready` con la base detenida o inalcanzable
- **THEN** la respuesta es 503

### Requirement: Respuestas de salud sin información interna

Las respuestas de las sondas MUST tener un cuerpo JSON breve en español claro y MUST NOT incluir texto de error de la base, direcciones de conexión, credenciales ni trazas.

#### Scenario: 503 sin detalles internos
- **WHEN** `GET /health/ready` responde 503 porque la base no contesta
- **THEN** el cuerpo informa que el servicio no está listo y no contiene el mensaje de error de la base, la dirección de conexión ni la contraseña

### Requirement: Una sesión de base por petición

Cada petición que usa la base MUST recibir su propia sesión, que se cierra al terminar la petición aunque la petición falle, de modo que las conexiones vuelvan al pool.

#### Scenario: Peticiones repetidas no agotan el pool
- **WHEN** se llama a `GET /health/ready` más veces que el tamaño del pool, una tras otra, con la base disponible
- **THEN** todas las respuestas son 200

#### Scenario: Fallos repetidos no agotan el pool
- **WHEN** la base deja de responder, se llama varias veces a `GET /health/ready` y luego la base vuelve
- **THEN** la siguiente llamada a `GET /health/ready` responde 200

### Requirement: Registro de la causa de un 503

Cuando `GET /health/ready` responde 503, el servidor MUST registrar en su log un aviso con el tipo de falla (por ejemplo, conexión rechazada, autenticación fallida o tiempo agotado) para que quien opera el sistema pueda diagnosticarla. El registro MUST NOT incluir la contraseña de la base ni la clave de firma, y la respuesta al cliente MUST seguir sin detalles internos.

#### Scenario: Base inalcanzable
- **WHEN** `GET /health/ready` responde 503 porque la base no acepta conexiones
- **THEN** el log del servidor tiene un aviso de la sonda de preparación que nombra el tipo de falla

#### Scenario: El log no expone secretos
- **WHEN** `GET /health/ready` responde 503
- **THEN** el aviso registrado no contiene el valor de `POSTGRES_PASSWORD` ni de `JWT_SECRET`
