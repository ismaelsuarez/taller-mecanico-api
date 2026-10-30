# asincronia-segundo-plano Specification

## Purpose
Que la API no bloquee el bucle de eventos y que la terminación de una orden avise al cliente en segundo plano, después de enviar la respuesta y sólo cuando la operación se confirmó (RT-TX-07, DD-07, US-024).

## Requirements

### Requirement: Handlers asíncronos sin llamadas bloqueantes

Todos los handlers HTTP de `app/modules/*/router.py` MUST ser `async def` y MUST NOT ejecutar llamadas bloqueantes sobre el bucle de eventos (E-5, criterio «ninguna llamada bloqueante»). Las operaciones de CPU que tardan (bcrypt) MUST correr fuera del bucle con `asyncio.to_thread` bajo el semáforo de concurrencia, y el hash MUST calcularse antes de abrir la transacción (RT-SE-02, RT-SE-03).

#### Scenario: Todos los handlers son asíncronos
- **WHEN** se inspeccionan las funciones decoradas con `@router.get`/`@router.post`/`@router.patch`/`@router.delete` de `app/modules/*/router.py`
- **THEN** todas están declaradas como `async def` y ninguna invoca `time.sleep`, una petición HTTP síncrona ni lectura/escritura de archivos síncrona dentro del bucle

#### Scenario: bcrypt sigue fuera del bucle
- **WHEN** se revisa el cómputo de hashes de contraseñas
- **THEN** el cálculo corre en un hilo de ejecución aparte bajo el semáforo de concurrencia, nunca directo en el bucle de eventos

### Requirement: Aviso en segundo plano al terminar una orden

Cuando `POST /ordenes/{id}/terminar` responde 200, la aplicación MUST agendar una tarea en segundo plano que espera aproximadamente medio segundo y después escribe un mensaje de aviso en el registro del servidor. La tarea MUST ejecutarse **después** de enviar la respuesta y MUST agendarse **sólo si la operación se confirmó**: si terminar respondió 404, 403 o 409, MUST quedar sin agendar ningún aviso (RT-TX-07, DD-07, T-9). El aviso MUST NOT modificar el estado ni el cuerpo de la respuesta, MUST NOT agregar escrituras en la base y MUST NOT demorar la respuesta.

#### Scenario: Terminación confirmada deja el aviso en el registro (C-12)
- **WHEN** tras reponer stock el mecánico asignado termina una orden `EN_REPARACION` y la operación responde 200
- **THEN** la respuesta 200 se envía de inmediato y recién después aparece en el registro del servidor el mensaje de aviso de esa orden

#### Scenario: Terminación rechazada no agenda ningún aviso (C-11)
- **WHEN** terminar responde 409 por stock insuficiente (o 404/403 por orden inexistente o sin permiso)
- **THEN** no se escribe ningún mensaje de aviso en el registro y la respuesta no cambia

#### Scenario: El aviso no cambia la respuesta
- **WHEN** se compara la respuesta de `POST /ordenes/{id}/terminar` con y sin el aviso agendado
- **THEN** estado, cuerpo y tiempos de respuesta son los mismos y ninguna tabla de la base cambia después del commit de la terminación
