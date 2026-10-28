# Design

## Context

Ver `proposal.md` para motivación y alcance; `specs/autorizacion-roles/spec.md` y `specs/administracion-personal/spec.md` fijan los comportamientos. Este diseño es necesario por la complejidad de permisos por petición, protección de rutas ya existentes y revocación con sesiones abiertas.

| Evidencia actual | Consecuencia de diseño |
|---|---|
| `dependencies.py:25-48` conserva `actor_temporal` y un `get_usuario_actual` mínimo que sólo devuelve identidad para `/auth/yo` | Ampliar ese módulo con `requiere_rol` y el helper de dueño; eliminar `actor_temporal` al final del change, no antes de tener sus reemplazos verificados |
| `main.py:42-54` monta todo en un único grupo abierto (T-11) | Separar `rutas_abiertas` (salud y `/auth`) de `rutas_protegidas` con el control del cambio obligatorio montado una sola vez sobre el grupo (DD-10) |
| La matriz RBAC exige roles distintos dentro del mismo router (repuestos: lectura a tres roles, escritura sólo ADMIN) | `requiere_rol` se declara **por ruta**, no por router; el grupo sólo aporta sesión + control de cambio pendiente |
| `errores.py` maneja 401/422/429/404/409, todavía sin 403 | Agregar la excepción de autorización con su handler y mensaje humano (DD-25), conservando los traductores existentes |
| `asignacion_rol` ya tiene índice único parcial `WHERE revocada_en IS NULL`, CHECK de roles y `evento_seguridad` completa (EJ-2) | Sin migraciones: la unicidad de RN-03 y la traducción de `IntegrityError` a 409 salen de la base |
| El módulo `usuarios` ya compone `UsuarioRepository`, `AsignacionRolRepository`, `EventoSeguridadRepository` y `UnitOfWorkUsuario` para registro/login/cambio | Reutilizar esa misma sesión y UoW para alta de personal, roles y eventos; no crear un servicio de autorización paralelo |
| `app/modules/ordenes/` existe con `models.py` real y el resto en docstrings (T-1) | Acoger ahí `GET /mis-ordenes` con repositorio/UoW mínimos y conformes; EJ-6 completa el módulo |
| 595 pruebas y cuatro `.http` asumen hoy rutas abiertas | Las fixtures y archivos `.http` pasan a sesiones autenticadas **sin cambiar los contratos ya aprobados** de EJ-3/4; sólo se agrega la capa de sesión |

## Goals / Non-Goals

**Goals:** que ninguna ruta de datos quede sin protección, que el permiso se decida en la base en cada petición, que la revocación surta efecto de inmediato, que la auditoría firme con el usuario real y que toda la evidencia (C-06 parcial, C-07, C-08, C-09 y C-18) se produzca sobre PostgreSQL real con Alembic.

**Non-Goals:** endpoints y permisos de órdenes de trabajo (EJ-6), jerarquía de repositorios y UoW formalizados (EJ-6), aviso en segundo plano (EJ-8), migraciones o cambios de esquema, caché de roles, refresh tokens, listas de revocación de JWT, RBAC por permisos granulares (el modelo es por roles vigentes), y cualquier publicación (`apply`, archive, commit o push) como parte de este pedido de propuesta.

## Decisions

### D1 — Formas de respuesta propuestas

La consigna fija códigos y rutas, pero no todas las claves de salida de los endpoints nuevos. Se proponen estos detalles de interfaz para revisión; se documentan en la KB al aplicar (D-4), no se presentan como exigencias textuales:

| Operación | Forma propuesta |
|---|---|
| `POST /usuarios` 201 | Reutiliza `UsuarioLectura` de EJ-4 (`{id, email, nombre, ...}`, nunca `password_hash` ni la contraseña) |
| `GET /usuarios/{id}/roles` 200 | `{"items": [{rol, desde, vence_en, otorgada_por}]}` — sólo vigentes, **sin** paginación (la tabla de códigos no contempla 422 de página y son pocas filas) |
| `POST /usuarios/{id}/roles` 201 | La asignación creada: `{rol, desde, vence_en, otorgada_por}` |
| `DELETE /usuarios/{id}/roles/{rol}` 200 | `{"mensaje": "Rol MECANICO revocado"}` (Flujo 5 fija 200, no 204) |
| `GET /eventos` 200 | Envoltorio estándar con `items: [{id, cuando, actor, accion}]` |
| `GET /mis-vehiculos`, `GET /mis-ordenes` 200 | Envoltorio estándar `{items, total, page, size, pages}` (US-017 lo pide paginado; página fuera de rango → 422) |
| Cualquier 401/403 | `{"detail": "<mensaje humano en español>"}` con el mismo formato de los 401 de EJ-4 |

`POST /usuarios/{id}/roles` acepta los cuatro valores del CHECK de `asignacion_rol`, incluido `CLIENTE`: la restricción de DD-18 (`CLIENTE` → 422) pertenece sólo al cuerpo de `POST /usuarios`, que da de alta personal. Alternativa descartada: duplicar la restricción y dejar imposible vincular un cliente existente a su rol.

### D2 — Dependencias de autorización y dónde se aplica cada control

Tres controles con responsabilidades separadas, en este orden de intención:

1. **Identidad** (`get_usuario_actual`, ya existente): cookie única → 401 ante cualquier fallo (token, usuario, `iat` vs `password_cambiada_en` sin truncar).
2. **Cambio obligatorio** (control del grupo protegido, montado una sola vez en `main.py`): sobre la identidad ya resuelta, `debe_cambiar_password = true` → 403; corre para todas las rutas del grupo y sólo para ellas.
3. **Rol** (`requiere_rol(*roles)`): dependencia de fábrica aplicada **por ruta** según la matriz; consulta los roles vigentes y devuelve 403 si falta el requerido.

`requiere_rol` depende a su vez de la identidad, de modo que el resultado sea correcto cualquiera sea el orden en que FastAPI resuelva las dependencias: sin sesión siempre hay 401, y con sesión siempre se llega a un 403 (de cambio pendiente o de rol) nunca a un 200 indebido. El orden efecto 401 → 403 se verifica con un test explícito, no se supone.

`/mis-vehiculos` y `/mis-ordenes` piden sesión pero ningún rol: sólo reciben el control del grupo. Las rutas de órdenes de EJ-6 se declararán con `requiere_rol` al crearlas; la de cancelar queda sin `requiere_rol` (el dueño no es personal) y la decisión 403/409 es del servicio, según la nota de `knowledge-base/02_descripcion_general.md`.

Alternativa descartada: imponer `requiere_rol` como dependencia única del grupo (rompe `/mis-*` y las rutas condicionadas) o confiar en los roles del JWT para evitar la consulta (viola RN-04).

### D3 — Roles vigentes por petición, sin caché

Un método de `UsuarioRepository` carga los roles vigentes del usuario (`revocada_en IS NULL` y `vence_en` nulo o futuro) con una consulta parametrizada; se ejecuta en cada petición protegida. Sin caché en memoria ni en Redis: el coste aceptado de DD-01 (una consulta extra por petición) es justamente lo que hace que revocar le quite el permiso a una sesión abierta (C-07). El JWT conserva sus roles informativos para `/auth/yo`; nunca se escriben de vuelta ni se usan para decidir.

### D4 — Alta de personal, roles y revocación en un solo UoW

Alta (`POST /usuarios`): validar contrato (incluido `rol` de personal) → calcular el hash de la provisoria fuera de transacción (RT-SE-03) → abrir `UnitOfWorkUsuario` → insertar usuario (`debe_cambiar_password = true`), asignación (`otorgada_por` = admin de la sesión) y evento → confirmar → responder con `UsuarioLectura`. El correo repetido llega como `IntegrityError` del índice único y se traduce a 409; si el commit falla, no queda ninguna de las tres filas.

Asignar rol: contrato con `vence_en` opcional, con zona horaria y futuro (422, no 409 — RT-SE-11); usuario inexistente → 404. Dentro de un solo UoW: si hay fila abierta **vencida** del mismo rol se cierra (`revocada_en = ahora`) y se abre la nueva; si la fila abierta sigue vigente, el índice único parcial produce `IntegrityError` → 409. Cerrar y abrir en la misma transacción evita quedar sin rol intermedio.

Revocar: comprobar primero la autoprotección (RN-05) — no revocar el propio ADMIN, y contar administradores vigentes antes de escribir; dejaría en cero → 409 sin tocar la fila. Luego `revocada_en = ahora` sobre la asignación abierta, sin `DELETE`. 404 si no había fila abierta. El evento se registra en el mismo UoW que el cambio (RT-SE-10) y la sesión del afectado cae en 403 en su siguiente petición, sin tocar cookies ni tokens.

El alta, la asignación y la revocación comparten el UoW de usuarios ya existente; ninguna de estas operaciones confirma fuera de él (B-8) y ninguna construye su UoW en el servicio (B-2).

### D5 — Lo propio y el helper de dueño

`GET /mis-vehiculos` vive en el módulo `clientes`: busca la ficha del usuario (`cliente.usuario_id`) y pagina sus vehículos vigentes. `GET /mis-ordenes` vive en el módulo `ordenes`, que hoy sólo tiene modelos: se le agrega el mínimo conforme de repository/unit_of_work/service/router (T-2) para paginar las órdenes de los vehículos del cliente, **todas**, incluidas las de vehículos dados de baja (DD-28). Sin ficha → página vacía con 200 (SU-11).

El helper de comprobación de dueño (T-8) es una función reutilizable que, dado usuario y una orden, devuelve si el usuario es personal (ADMIN/RECEPCION/MECANICO — SU-03) o el dueño del vehículo. En EJ-5 se prueba con `/mis-ordenes` y sus bordes; EJ-6 lo conecta al 403 de `GET /ordenes/{id}` y de cancelar, sin reescribirlo.

La paginación reutiliza el envoltorio y las reglas RT-PG-05 ya implementadas; no se crea un paginador nuevo para estas rutas.

### D6 — Errores de autorización y eventos de seguridad

Se agrega `NoAutorizado` (o equivalente) con handler 403 y mensaje humano propio, sin reutilizar el traductor 409 ni exponer el motivo interno («No tenés permiso para realizar esta acción.» y variantes puntuales cuando el motivo sea conocido y seguro: autoprotección y último administrador de RN-05). Los 401 de identidad conservan sus mensajes de EJ-4; los 422 siguen con el traductor de validación ya auditado. Se corren las regresiones de errores compartidos porque `registrar_traductores` es código común (riesgo item 3).

Los eventos nuevos usan exactamente las acciones de DD-26 («Alta de personal con rol X», «Rol X asignado a Y», «Rol X revocado a Y») con `actor` = correo del administrador (o del usuario, según la acción), y se confirman en el mismo UoW que el cambio que registran. Los logins comunes no generan evento: siguen en `intento_acceso`.

### D7 — Verificación y unidades de trabajo para apply

Cada grupo comienza con RED y termina con GREEN usando pytest/httpx sobre PostgreSQL real aislada con Alembic; ninguna regla se prueba con mocks de la base. Las fixtures de CRUD existentes ganan una sesión autenticada (login real sobre la misma base) sin cambiar los cuerpos esperados.

| Caso | Evidencia prevista |
|---|---|
| C-06 parcial | 401 sin sesión vs 403 sin rol sobre la misma ruta, y `/mis-vehiculos` / `/mis-ordenes` propios y vacíos |
| C-07 | Revocación con cookie abierta → 403 en la petición siguiente; `/auth/yo` muestra la diferencia; fila conservada; `vence_en` pasado o sin zona → 422 |
| C-08 | El admin no se revoca su ADMIN: 409; y el caso de quedar sin administradores: 409 |
| C-09 completo | Bloqueo 403 en todo lo protegido con cambio pendiente, `/auth/*` y `/health/*` desbloqueados, cookie nueva válida y anterior 401 |
| C-18 | La recepción recibe 403 al cambiar precio o descripción y el historial no cambia |

`test/autorizacion.http` usa sesiones simultáneas (`# @name`, `# @no-cookie-jar`, `Cookie: {{loginX.response.headers.Set-Cookie}}`) con ADMIN y RECEPCION, tras `python seed.py`. `test/clientes_vehiculos.http` y `test/repuestos.http` sólo ganan la capa de sesión; sus respuestas esperadas no cambian salvo el 403 de C-18. Además: suite completa, comparación diferencial de las superficies que compartan `errores.py`/`dependencies.py` con la base previa (EJ-4), y verificación independiente por los riesgos item 2 (seguridad/permisos) e item 3 (helpers compartidos).

Unidades revisables secuenciales de aproximadamente 400 líneas autorales con tests/docs junto al comportamiento; commit por unidad cuando corresponda, decidido en apply, nunca en esta propuesta.

## Risks / Trade-offs

- [Rutas que estaban abiertas dejan de responder a pruebas y `.http` existentes] → Adaptar fixtures y archivos en la misma unidad que protege cada ruta, con regresión completa; no se relaja ninguna protección para que las pruebas pasen.
- [Confundir 401 con 403, o aplicar el cambio pendiente a `/auth/*`] → Tests explícitos de orden (401 sin sesión antes que cualquier 403) y de los dos grupos sobre las mismas rutas.
- [Revocación que no surte efecto hasta que venza el token] → Decisión D3: consulta por petición sin caché; prueba C-07 con cookie previa a la revocación.
- [Carrera entre cierre y reapertura de un rol, o revocación simultánea del último ADMIN] → Transacción única + índice único parcial traducido a 409; conteo de administradores vigentes dentro del mismo UoW; sin garantías extra de concurrencia fuera de la consigna (mismo criterio que DD-08).
- [Regresión en errores compartidos (422/409/401) por agregar el 403] → Handler propio y diferencial contra EJ-4 de las superficies ajenas que usan `registrar_traductores`.
- [La consulta de roles por petición agrega latencia] → Aceptado por DD-01; se mide sólo como regresión relativa, sin umbral absoluto de milisegundos.
- [Helper de dueño probado contra datos que recién llegan en EJ-6] → Acotado a `/mis-ordenes` en este change y documentado para EJ-6, sin anticipar endpoints.
- [Percepción de seguridad completa] → El README deja explícito que los permisos de órdenes y su 403 por orden ajena se cierran en EJ-6 (C-06 completo).

## Migration Plan

No se prevén migraciones, nuevas variables de entorno ni dependencias: el esquema de EJ-2 ya cubre `asignacion_rol` y `evento_seguridad`, y el índice parcial de RN-03 ya existe. Se conservan `JWT_SECRET`, cookies, seed y contratos de EJ-4 sin cambios. La reversión es por unidades de código, sin reescribir datos ni historial. La verificación corre sobre bases de test reconstruibles, nunca sobre la base de desarrollo. `apply`, archive, commits de entrega y push no forman parte de esta propuesta; tampoco el marcaje de EJ-5 en `CHANGES.md`.

No hay decisiones de producto bloqueantes: D1 y los detalles de salida propuestos deben quedar visibles en la revisión y registrados en la KB al aplicar.
