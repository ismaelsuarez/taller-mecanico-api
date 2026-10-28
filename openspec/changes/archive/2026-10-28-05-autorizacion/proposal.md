# Proposal

## Why

EJ-1..4 están archivados y publicados, con la autenticación de EJ-4 funcionando sobre cookie. Falta aplicar la autorización de EJ-5: hoy las rutas de datos siguen abiertas y las escrituras de auditoría se firman con el actor temporal (T-4), por lo que cualquier visitante puede crear clientes, editar repuestos o leer el catálogo. Sin `requiere_rol`, la matriz RBAC de la consigna (14 % de la nota) no existe y un hueco acá expone toda la API.

## What Changes

- Completar `get_usuario_actual` para que toda ruta protegida responda 401 ante cookie ausente, token inválido/vencido, usuario inexistente/inactivo o `iat` anterior a `password_cambiada_en` (RN-07), y agregar `requiere_rol`, que consulta los roles vigentes de `asignacion_rol` **en cada petición** y responde 403 (RN-04); los roles del token quedan como información, nunca como autorización.
- Reemplazar `actor_temporal` (T-4) por `get_usuario_actual` en las escrituras de auditoría existentes y proteger con `requiere_rol` las rutas de clientes, vehículos y repuestos según la matriz RBAC de `knowledge-base/03_actores_y_roles.md`.
- Reorganizar `main.py` en los dos grupos de rutas (T-11): abierto (`/health/*`, `/auth/*`) y protegido con el control del cambio obligatorio de contraseña montado **una sola vez**; con cambio pendiente, 403 en todo lo protegido (RN-06, DD-10) sin bloquear `/auth/*` ni `/health/*`.
- Agregar la administración de personal y roles (ADMIN): `POST /usuarios` de alta atómica con `debe_cambiar_password = true` (usuario + asignación + evento en un solo UoW, DD-18), `GET /usuarios/{id}/roles`, `POST /usuarios/{id}/roles` (vencimiento opcional con zona horaria y en el futuro, si no 422 — RT-SE-11) y `DELETE /usuarios/{id}/roles/{rol}` que revoca sin borrar la fila; reasignar un rol vencido cierra la fila anterior y abre una nueva; rol abierto duplicado → 409 (RN-03); autoprotección del ADMIN y mínimo de administradores vigentes → 409 (RN-05).
- Agregar `GET /eventos` (ADMIN, paginado) sobre `evento_seguridad`, con las acciones y actores de DD-26, y `GET /mis-vehiculos` y `GET /mis-ordenes` (paginados, sólo autenticado) con el helper de comprobación de dueño (RN-17, T-8, DD-28, SU-11).
- Agregar el error de autorización 403 con mensaje humano en español (DD-25), registrar los eventos de seguridad de altas y cambios de rol (RT-SE-10) y documentar las formas de respuesta no fijadas por la consigna como decisiones del proyecto.
- Escribir `test/autorizacion.http` con sesiones simultáneas de ADMIN y RECEPCION para C-06 (parte), C-07, C-08 y C-09, actualizar los `.http` existentes a sesiones autenticadas (C-18 exige el 403 de la recepción) y adaptar las fixtures/pytest a rutas protegidas.

**Fuera de alcance:** endpoints y permisos de órdenes de trabajo (`POST /ordenes`, iniciar/terminar/cancelar, `GET /estados-orden`, el 403 de orden ajena — cablean en EJ-6 según T-8), jerarquía de repositorios y UoW (EJ-6), aviso en segundo plano (EJ-8), migraciones nuevas (el esquema de EJ-2 ya cubre `asignacion_rol` y `evento_seguridad`), Redis/refresh tokens/listas de revocación. Este pedido produce planificación solamente: no ejecuta `apply`, archive, commit ni push.

## Capabilities

### New Capabilities

- `autorizacion-roles`: identidad exigida por toda ruta protegida (401), bloqueo por cambio de contraseña pendiente (403), permisos decididos con los roles vigentes en la base en cada petición (403), la matriz RBAC de las rutas existentes, el reemplazo del actor temporal y lo propio (`/mis-vehiculos`, `/mis-ordenes`).
- `administracion-personal`: alta de personal con rol inicial atómica, consulta/asignación/revocación de roles con vigencia y autoprotección, y el listado paginado de eventos de seguridad.

### Modified Capabilities

Ninguna. Se conservan sin cambio los requisitos de `autenticacion-sesiones` (que sigue sin anticipar autorización), `contratos-estrictos`, `listados-paginados`, `clientes-vehiculos`, `catalogo-repuestos`, `modelo-datos`, `datos-iniciales`, `migraciones-esquema`, `configuracion-aplicacion` y `salud-servicio`. Proteger rutas o reutilizar helpers no cambia por sí mismo ningún requisito normativo existente; si al aplicar apareciera un cambio de comportamiento observable de una spec vigente, se agregará el delta MODIFIED correspondiente con decisión explícita, no de forma silenciosa.

## Impact

- Código previsto: `app/core/{dependencies,errores}.py` (`requiere_rol`, 403, helper de dueño), `main.py` (dos grupos y control del cambio obligatorio), `app/modules/usuarios/{schemas,repository,service,router,unit_of_work}.py` (alta, roles, eventos), `app/modules/clientes/router.py` (protección + `/mis-vehiculos`), `app/modules/repuestos/router.py` (protección y reemplazo del actor), `app/modules/ordenes/` (mínimo conforme para `/mis-ordenes`; EJ-6 lo completa).
- Persistencia: sin migraciones nuevas; se usan `asignacion_rol`, `evento_seguridad`, `vehiculo` y `orden` tal como los creó EJ-2, con el índice único parcial de RN-03 y las restricciones existentes para traducir `IntegrityError` a 409.
- Integración sensible: helpers compartidos de errores y dependencias (riesgo item 3) y seguridad de la API (riesgo item 2); la protección de rutas cambia el comportamiento de pruebas y `.http` ya existentes, que deben pasar a sesiones autenticadas sin alterar los contratos ya aprobados de EJ-3/4.
- Pruebas/documentación: nuevo `test/autorizacion.http`, adaptación de `test/clientes_vehiculos.http` y `test/repuestos.http`, fixtures pytest con sesión/roles reales, README y decisiones nuevas en `knowledge-base/09_decisiones_y_supuestos.md`. Sin dependencias nuevas.
- Aceptación: C-06 (parte: 401 vs 403 y `/mis-*`), C-07, C-08, C-09 completo y C-18 (403 a la recepción); C-06 completo y el 403 de orden ajena se cierran en EJ-6.
- Fuentes: `docs/TP_Cap1a6_Consigna.pdf` (EJ-5, US-014..017, RN-03..07, RN-17 y tabla de rutas), `CHANGES.md` (EJ-5 y T-4/T-8/T-11), KB 02/03/05/06/07/09/11; DD-01, DD-10, DD-18, DD-25..28, SU-03, SU-11. Los detalles no fijados por esas fuentes (formas de respuesta de los endpoints nuevos) se identifican como decisiones propuestas en `design.md`.
