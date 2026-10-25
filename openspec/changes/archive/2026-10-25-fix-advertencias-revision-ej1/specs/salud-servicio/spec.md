# Spec Delta

## ADDED Requirements

### Requirement: Registro de la causa de un 503

Cuando `GET /health/ready` responde 503, el servidor MUST registrar en su log un aviso con el tipo de falla (por ejemplo, conexión rechazada, autenticación fallida o tiempo agotado) para que quien opera el sistema pueda diagnosticarla. El registro MUST NOT incluir la contraseña de la base ni la clave de firma, y la respuesta al cliente MUST seguir sin detalles internos.

#### Scenario: Base inalcanzable
- **WHEN** `GET /health/ready` responde 503 porque la base no acepta conexiones
- **THEN** el log del servidor tiene un aviso de la sonda de preparación que nombra el tipo de falla

#### Scenario: El log no expone secretos
- **WHEN** `GET /health/ready` responde 503
- **THEN** el aviso registrado no contiene el valor de `POSTGRES_PASSWORD` ni de `JWT_SECRET`
