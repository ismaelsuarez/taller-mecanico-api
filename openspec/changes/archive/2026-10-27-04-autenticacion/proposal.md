# Proposal

## Why

EJ-1..3 ya están archivados y publicados, incluidas las correcciones de auditoría. Falta implementar la autenticación de EJ-4 para iniciar sesiones seguras y habilitar después la autorización de EJ-5, sin anticipar sus permisos ni modificar el CRUD existente.

## What Changes

- Incorporar `POST /auth/registro`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/yo` y `POST /auth/cambiar-password` en el módulo `usuarios`.
- Registrar usuario, rol CLIENTE, ficha de cliente y evento de seguridad atómicamente; no apropiarse de fichas existentes. Entregar la cookie únicamente después de confirmar el UoW.
- Ampliar los helpers existentes de bcrypt, semáforo y `to_thread` con verificación de contraseñas y JWT firmado; limitar todos los campos destinados a bcrypt a 72 bytes UTF-8.
- Transportar el JWT exclusivamente mediante `access_token`, con sus atributos de seguridad y duración configurada; conservar `iat` fraccional para invalidar sesiones anteriores al cambio de contraseña.
- Aplicar primero el límite de cinco fallos por correo/IP en 60 segundos; responder 429 con `Retry-After` sin bcrypt. Persistir los intentos mediante un UoW dedicado y mantener el historial tras un login correcto.
- Reutilizar el hash ficticio del lifespan para impedir la enumeración por el camino de verificación; mantener los mensajes humanos acordados y la distinción de cuenta inactiva de DD-24.
- Agregar una dependencia mínima de autenticación para `/auth/yo` y cambio de contraseña, con roles actuales y roles del token diferenciados, sin autorización RBAC.
- Preparar pruebas PostgreSQL/Alembic con usuarios autenticables y secuencias coherentes, ampliar el contrato seguro de errores 401/429 y documentar los casos `.http` de EJ-4.

**Fuera de alcance:** protección del CRUD, reemplazo de `actor_temporal`, `requiere_rol`, administración de personal/roles, bloqueo global por cambio obligatorio, endpoints de órdenes y nuevas migraciones sin necesidad demostrada. Esos comportamientos siguen el roadmap de EJ-5..8. Este pedido produce planificación solamente: no ejecuta `apply`, archive, commit ni push.

## Capabilities

### New Capabilities

- `autenticacion-sesiones`: registro de clientes, login limitado y auditado, sesión por cookie, consulta de identidad, logout y renovación/invalidez por cambio de contraseña.

### Modified Capabilities

Ninguna. Se conservan los requisitos de `configuracion-aplicacion`, `salud-servicio`, `contratos-estrictos`, `modelo-datos`, `datos-iniciales` y `migraciones-esquema`. Reutilizar o ampliar su implementación no cambia por sí mismo sus requisitos normativos.

## Impact

- Código previsto: `app/modules/usuarios/{schemas,repository,unit_of_work,service,router}.py`, `app/core/{security,dependencies,errores}.py` y montaje del router en `main.py`. El hashing, el semáforo y el hash ficticio ya existen; no se crean servicios paralelos.
- Persistencia: modelos de usuarios, roles, intentos, eventos y clientes existentes; repositorios con `flush`, UoW como único dueño del commit y sesiones cerradas por su dependencia.
- Integración sensible: evitar conexiones retenidas durante bcrypt por transacciones implícitas; preservar el comportamiento del seed, la salud, los errores 404/409 y la validación 422 sin eco de datos sensibles.
- Pruebas/documentación: `test/pytest/`, `test/auth.http`, README y documentación de decisiones propuestas. Sin dependencias nuevas previstas: bcrypt, PyJWT y el stack asíncrono ya forman parte del proyecto.
- Aceptación: C-01..C-04 completos; C-05 en el alcance de EJ-4; C-09 respecto de cookie nueva y revocación inmediata, sin el bloqueo 403 global de EJ-5.
- Fuentes: `docs/TP_Cap1a6_Consigna.pdf` (EJ-4, RN-07..09 y tabla de rutas), `CHANGES.md` (EJ-4 y T-2/4/7/10/11), KB 02/03/05/07/08/09/11; DD-17/19/20/24/25/26/42 y SU-05/10. Los detalles no fijados por esas fuentes se identifican como decisiones propuestas en `design.md`.
