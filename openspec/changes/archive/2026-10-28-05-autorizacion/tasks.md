# Tasks

Plan de ejecución de `/opsx:apply 05-autorizacion`. Las casillas se marcan sólo con evidencia registrada en `odd/tasks/05-autorizacion.md`. Referencias: [spec autorización](specs/autorizacion-roles/spec.md), [spec administración](specs/administracion-personal/spec.md) y [diseño](design.md), decisiones D1–D7. Mantener el orden secuencial de los grupos; tests y documentación acompañan cada comportamiento, no se posponen al cierre.

Unidades previstas: un grupo funcional por unidad revisable, subdividiendo si supera aproximadamente 400 líneas autorales, con tests/docs junto al código. Riesgos de implementación: seguridad/permisos (item 2) y helpers de errores/dependencias compartidos (item 3). No agrupar todo EJ-5 en una sola revisión ni afirmar un tamaño exacto antes de ver el diff.

## 1. Contratos de autorización y preparación de pruebas con sesión

- [x] 1.1 Agregar contratos de entrada/salida de D1 en `usuarios/schemas.py` (alta de personal, asignación de rol con `vence_en`, revocación, item de evento, `/mis-*` sobre el envoltorio existente) con `extra="forbid"`, mensajes humanos y sin `password_hash`; observar RED/GREEN de `rol: CLIENTE` → 422, campos extra → 422 y `vence_en` pasado/sin zona → 422.
- [x] 1.2 Agregar el error de autorización 403 con handler y mensaje humano en `app/core/errores.py`, conservando los traductores 401/422/429/404/409; verificar con pruebas de regresión que validación, paginación y conflictos siguen intactos (riesgo item 3).
- [x] 1.3 Preparar fixtures de pytest con sesión autenticada sobre PostgreSQL real con Alembic (login real, roles vigentes, `nuevo@example.com` con cambio pendiente) sin reemplazar las fixtures existentes; verificar que la suite focalizada previa sigue en verde antes de proteger rutas.

## 2. Identidad completa y rol por petición

- [x] 2.1 Completar `get_usuario_actual` en `app/core/dependencies.py` para los 401 de US-014 (cookie, firma, vencimiento, usuario inexistente/inactivo, `iat` anterior a `password_cambiada_en` sin truncar); observar RED/GREEN de cada caso sobre rutas de prueba, sin tocar todavía las rutas existentes.
- [x] 2.2 Implementar `requiere_rol(*roles)` con la consulta de roles vigentes del repositorio por petición (D3), sin caché y sin leer roles del JWT; observar RED/GREEN de 403 sin rol, 403 con rol vencido, 403 tras revocar con cookie abierta y 401 precediendo a cualquier 403.
- [x] 2.3 Documentar en la KB los controles y sus órdenes (D2/D3) y verificar que `/auth/yo` sigue mostrando roles vigentes vs token sin cambiar de contrato.

## 3. Protección de las rutas existentes y los dos grupos de rutas

- [x] 3.1 Proteger con `requiere_rol` las rutas de clientes, vehículos y repuestos según la matriz (cliente: ADMIN/RECEPCION; repuestos: lectura ADMIN/RECEPCION/MECANICO, escritura ADMIN); observar RED/GREEN de 403 por rol ausente y 200 con el rol vigente, incluido C-18 (recepción 403 en precio/descripción sin historial nuevo).
- [x] 3.2 Reemplazar `actor_temporal` por `get_usuario_actual` en las escrituras de auditoría (T-4) y eliminar la dependencia temporal; verificar que movimientos e historiales quedan firmados por el usuario de la sesión y que sin sesión no se escribe nada.
- [x] 3.3 Reorganizar `main.py` en el grupo abierto (`/health/*`, `/auth/*`) y el protegido con el control del cambio obligatorio montado una sola vez (T-11, DD-10); observar RED/GREEN de C-09 completo: 403 en todo lo protegido con cambio pendiente, `/auth/*` y `/health/*` desbloqueados, y cookie nueva tras el cambio.
- [x] 3.4 Adaptar fixtures y archivos `.http` existentes a sesiones autenticadas sin alterar sus contratos de respuesta, y correr la suite completa para confirmar que la única diferencia esperada es la capa de sesión.

## 4. Alta de personal (ADMIN)

- [x] 4.1 Implementar `POST /usuarios` con hash previo a la transacción y un solo UoW de usuario + asignación (`otorgada_por` = admin) + evento (DD-18, B-8); observar RED/GREEN de 201, correo repetido 409 sin filas parciales, `CLIENTE` 422 y rollback completo ante fallo de confirmación.
- [x] 4.2 Verificar que `debe_cambiar_password = true`, el evento con acción/actor de DD-26 y la ausencia de `password_hash` en la respuesta se cumplen, y que el usuario dado de alta queda bloqueado en 403 en el grupo protegido hasta cambiar la contraseña.

## 5. Asignación y revocación de roles

- [x] 5.1 Implementar `POST /usuarios/{id}/roles` con `vence_en` opcional validado (422 pasado/sin zona), cierre de la fila vencida + apertura de la nueva en un solo UoW y 409 por duplicado vigente vía índice parcial (RN-03, RT-SE-11); observar RED/GREEN de los cuatro caminos y del evento registrado.
- [x] 5.2 Implementar `DELETE /usuarios/{id}/roles/{rol}` con `revocada_en` sin borrar la fila, 404 sin asignación abierta y autoprotección RN-05 (409 propio y 409 por quedar sin administradores); observar RED/GREEN de C-08 y del efecto inmediato 403 en la sesión revocada de C-07.
- [x] 5.3 Implementar `GET /usuarios/{id}/roles` (sólo vigentes, 404/403) y completar C-07 en `test/autorizacion.http` con sesiones simultáneas ADMIN/RECEPCION, incluida la fila revocada que sigue existiendo.

## 6. Eventos de seguridad y rutas de lo propio

- [x] 6.1 Implementar `GET /eventos` (ADMIN, paginado con el envoltorio existente, 422 fuera de rango, 403 sin rol) y verificar que aparecen las acciones de DD-26 con sus actores, sin secretos ni mensajes internos.
- [x] 6.2 Implementar `GET /mis-vehiculos` (sólo vigentes) y `GET /mis-ordenes` (todas, incluidas las de vehículos dados de baja) paginados y sólo autenticados (RN-17, DD-28, SU-11), con respuesta vacía 200 para usuarios sin ficha de cliente; observar RED/GREEN de cada caso y de los 401 sin sesión.
- [x] 6.3 Implementar el helper de comprobación de dueño (T-8) con su prueba de personal vs dueño, dejándolo documentado para el 403 de órdenes de EJ-6; incorporar C-06 parcial (401 vs 403 y `/mis-*`) a `test/autorizacion.http`.

## 7. Verificación integrada y preparación del relevo

- [x] 7.1 Ejecutar la suite pytest completa sobre PostgreSQL aislada con esquema migrado y todos los `.http` tras `python seed.py`; comprobar C-06 parcial, C-07, C-08, C-09 y C-18, sin saltados, preservando registro/login/CRUD/seed/salud y registrando resultados reales.
- [x] 7.2 Ejecutar una comparación diferencial de las superficies ajenas que compartan `errores.py` y `dependencies.py` contra la base previa (EJ-4), verificando códigos, cuerpos y encabezados; corregir cualquier diferencia no pedida y fijarla con regresión.
- [x] 7.3 Obtener verificación independiente por los riesgos item 2 (permisos/seguridad) e item 3 (helpers compartidos), revisar los deltas con las reglas nativas vigentes y comprobar ausencia de rutas sin protección, roles tomados del JWT, commits fuera de UoW y secretos; registrar aprobación o fallos sin inventar evidencia.
- [x] 7.4 Conciliar specs/diseño/tasks, README, OpenAPI y decisiones KB (D1 y pendientes) con lo observado, validar el change con OpenSpec y comprobar el handoff EJ-5 sin marcar EJ-6. Sin cambios de esquema, no se repite el ciclo Alembic up/down/up; sin limpiezas sobre desarrollo.

## Workflow follow-up

- Con la implementación y su verificación completas, ejecutar `/opsx:archive 05-autorizacion` según el flujo autorizado; no forma parte de esta propuesta.
- Verificar las specs canónicas resultantes y marcar EJ-5 en `CHANGES.md` en el commit de cierre correspondiente.
- Sincronizar memoria y publicar únicamente con autorización de entrega vigente; no inferir permiso de push/merge a partir de `propose` ni de una revisión aprobada.
- El relevo a EJ-6 requiere EJ-5 archivado, commiteado y empujado. No iniciar EJ-6 en este change.
