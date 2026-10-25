# Flujos Principales

Cada flujo se documenta extremo a extremo según la arquitectura **Router → Service → UoW → Repository → Model**.

---

## Flujo 1: Auto-registro (RN-02)
**Disparador**: `POST /auth/registro` · **Actor**: visitante

**Pasos**:
1. Router valida el contrato (`extra="forbid"`, contraseña ≤ 72 bytes) → 422 si no cumple.
2. Service calcula el hash bcrypt **antes** de abrir el UoW (`to_thread` + semáforo).
3. Service abre `async with uow:`
   1. Crea `usuario`.
   2. Crea `asignacion_rol` con `CLIENTE`.
   3. Crea `cliente` con `usuario_id` (no reutiliza una ficha existente).
   4. Registra `evento_seguridad` del alta.
4. Al salir del bloque, el UoW confirma.
5. **Después del commit**, se emite el JWT (roles vigentes: `CLIENTE`) y se pone en la cookie `access_token` (DD-17).
6. Router responde 201 con `Set-Cookie` (cuerpo sin `password_hash` y sin token).

Cuerpo (DD-17): `{ "email", "password", "nombre", "documento", "telefono" }` — `nombre` va al usuario y a la ficha de cliente.

**Casos de error**:
- Correo o documento repetido → `IntegrityError` → rollback → **409 con mensaje propio**, ninguna fila suelta y **sin cookie** (C-02).

---

## Flujo 2: Login (RN-08, RN-09)
**Disparador**: `POST /auth/login` · **Actor**: cualquiera

```
Cliente → Router → AuthService ──► IntentoRepo (cuenta fallos 60s, email+ip, desde el último éxito)
                                    ├─ ≥5 → 429 + Retry-After (sin hash)
                                    └─ <5 → verificar bcrypt (hash real o ficticio, to_thread + semáforo)
                                             ├─ OK  → JWT{sub,iat,exp,roles vigentes} → Set-Cookie access_token
                                             └─ MAL → 401 (mismo cuerpo, mismo tiempo)
                 ↳ en todos los casos: anotar intento_acceso en SESIÓN y TRANSACCIÓN PROPIAS (commit siempre)
```

**Pasos**:
1. Contrato: correo + contraseña ≤ 72 bytes (422).
2. Límite de intentos: una consulta sobre `intento_acceso` (índice `email, ip, cuando`). Si hay 5 fallos en 60 s sin un éxito posterior → **429** con `Retry-After`, sin calcular ningún hash.
3. Busca el usuario por correo; verifica contra su hash o contra el **hash ficticio** precalculado en el lifespan.
4. Anota el intento (éxito/fallo) con el **UoW dedicado de intentos de acceso** (sesión y transacción propias, confirma siempre; DD-19).
5. Éxito: emite JWT con `iat` con fracción de segundo; cookie `access_token` (`HttpOnly`, `SameSite=Lax`, `Max-Age`, `Secure` configurable).
6. Respuesta: `{ "mensaje": "Sesión iniciada", "debe_cambiar_password": false, "expira_en_segundos": 1800 }`.

**Casos de error**:
- Correo inexistente o contraseña mala → 401 idéntico (C-04).
- Sexto intento fallido → 429 en pocos ms (C-05).
- Contraseña incorrecta o correo inexistente → 401 «El correo o la contraseña no son correctos.» (igual para cuentas activas e inactivas).
- Contraseña **correcta** y cuenta inactiva → 401 «Tu cuenta está desactivada. Comunicate con el taller para reactivarla.» (DD-24). Siempre se verifica el hash e `exito = false`.
- 429 → además se registra «Login bloqueado por demasiados intentos» en `evento_seguridad` (DD-26).

---

## Flujo 3: Petición protegida (autenticación + autorización)
**Disparador**: cualquier ruta del grupo protegido

**Pasos**:
1. `get_usuario_actual` lee `request.cookies["access_token"]` (nunca `Authorization`).
2. Decodifica y verifica firma/exp → 401 si falla.
3. Carga el usuario → 401 si no existe o `activo = false`.
4. Si `password_cambiada_en` existe y `iat < password_cambiada_en` (sin truncar) → 401.
5. Control del grupo protegido: `debe_cambiar_password = true` → **403**.
6. `requiere_rol(...)` consulta `asignacion_rol` vigentes (no revocadas, sin vencer) → 403 si no tiene el rol.
7. Handler / servicio.

---

## Flujo 4: Cambio de contraseña (RN-06, RN-07)
**Disparador**: `POST /auth/cambiar-password` · **Actor**: autenticado (también con cambio pendiente)

**Pasos**:
1. Contrato: contraseña actual + nueva, ambas ≤ 72 bytes.
2. Verifica la actual (bcrypt fuera del bucle); calcula el hash nuevo antes de abrir el UoW.
3. UoW: actualiza `password_hash`, `password_cambiada_en = now()` (precisión completa), `debe_cambiar_password = false`; registra `evento_seguridad`.
4. Después de anotar el cambio, emite un token nuevo (su `iat` es posterior) y lo pone en la cookie.
5. La cookie anterior da 401 aunque sea del mismo segundo (C-09).

**Casos de error**: contraseña actual incorrecta → 401 (según tabla de códigos: 200, 401, 422).

---

## Flujo 5: Gestión de roles (RN-03, RN-05)
**Disparador**: `POST /usuarios/{id}/roles` / `DELETE /usuarios/{id}/roles/{rol}` · **Actor**: ADMIN

**Alta de personal** (`POST /usuarios`, DD-18):
1. Contrato: `{email, nombre, password_provisoria, rol}` con `rol ∈ {ADMIN, RECEPCION, MECANICO}` (`CLIENTE` → 422).
2. Hash de la contraseña provisoria antes de abrir el UoW.
3. Un solo UoW: `usuario` (`debe_cambiar_password = true`) + `asignacion_rol` (`otorgada_por` = admin actual) + `evento_seguridad`. Correo repetido → 409. 201.

**Asignar**:
1. Contrato: `rol` válido, `vence_en` opcional con zona y futuro (si no, 422).
2. Usuario inexistente → 404.
3. Si hay una fila abierta **vencida** del mismo rol → se cierra (`revocada_en`) y se abre una nueva.
4. Si hay una fila abierta **vigente** → 409 (índice único parcial).
5. Registra `evento_seguridad`. 201.

**Revocar**:
1. Usuario o asignación abierta inexistente → 404.
2. Si es el propio ADMIN revocándose ADMIN, o dejaría el sistema sin admins vigentes → 409.
3. Escribe `revocada_en` (la fila no se borra). Registra evento. 200.
4. La sesión ya abierta del afectado recibe 403 en la siguiente petición (C-07).

---

## Flujo 6: Alta de orden de trabajo (RN-10, RN-16, RN-19)
**Disparador**: `POST /ordenes` · **Actor**: RECEPCION, ADMIN

Cuerpo (no viajan precio, total, estado ni fecha):
```json
{ "vehiculo_id": 2, "falla": "Ruido al frenar",
  "items": [ { "repuesto_id": 2, "cantidad": 1 }, { "repuesto_id": 4, "cantidad": 3 } ] }
```

**Pasos**:
1. DTO: ≥ 1 ítem, sin `repuesto_id` repetidos, `cantidad > 0` → 422.
2. UoW:
   1. Verifica catálogo no vacío (si vacío → 409 mensaje propio).
   2. Carga el vehículo vigente (inexistente o dado de baja → 409).
   3. Carga los repuestos vigentes (alguno inexistente o dado de baja → 409; la orden no queda creada).
   4. Crea `orden_trabajo` en `PENDIENTE` con ítems (precio copiado), calcula `total = Σ cantidad × precio_unitario`.
   5. Agrega `historial_estado_orden` `(null → PENDIENTE, usuario actual)`.
3. 201 con el detalle:

```json
{ "id": 3, "estado": "PENDIENTE", "patente": "AC456EF", "total": "68000.00",
  "creada_en": "2026-10-23T02:18:54.332849Z", "mecanico_id": null,
  "falla": "Ruido al frenar", "cliente": "Laura Cliente",
  "items": [
    { "repuesto_id": 2, "codigo": "FRE-010", "descripcion": "Pastillas de freno delanteras",
      "cantidad": 1, "precio_unitario": "32000.00", "subtotal": "32000.00" },
    { "repuesto_id": 4, "codigo": "ACE-530", "descripcion": "Aceite 5W30 por litro",
      "cantidad": 3, "precio_unitario": "12000.00", "subtotal": "36000.00" } ],
  "historial": [ { "desde_estado": null, "hasta_estado": "PENDIENTE", "usuario_id": 3,
                   "cuando": "2026-10-23T02:18:54.366899Z" } ] }
```

---

## Flujo 7: Iniciar orden (RN-11)
**Disparador**: `POST /ordenes/{id}/iniciar` · **Actor**: MECANICO

1. Orden inexistente → 404.
2. Estado ≠ `PENDIENTE` → 409.
3. UoW: `estado = EN_REPARACION`, `mecanico_id = usuario actual`, línea de historial. 200.

---

## Flujo 8: Terminar orden (RN-11, RN-13, RN-14) — operación crítica
**Disparador**: `POST /ordenes/{id}/terminar` · **Actor**: mecánico asignado o ADMIN

```
Router ─► OrdenService.terminar(uow, id, usuario, background_tasks)
            async with uow:
              orden = uow.ordenes.get_con_items(id)        → 404   (repuestos con get_by_id_including_deleted, DD-21)
              permiso (asignado | ADMIN)                     → 403
              estado == EN_REPARACION                         → 409
              para cada ítem:
                 stock.registrar_salida(repuesto, cantidad, orden, usuario)   ← punto único de escritura
                     (stock insuficiente → excepción → rollback total → 409)
                 → UPDATE repuesto.stock ; INSERT movimiento_stock (cantidad negativa, motivo «Salida por orden de trabajo #N», DD-29)
              orden.estado = TERMINADA ; INSERT historial_estado_orden (usuario = quien termina; mecanico_id NO cambia, DD-31)
            ← commit
          background_tasks.add_task(avisar_cliente, ...)    ← sólo si se confirmó
Response 200 ──► luego corre el aviso: await asyncio.sleep(0.5) + log
```

Cuatro clases de escritura en una sola transacción: `repuesto.stock`, `movimiento_stock`, `orden_trabajo.estado`, `historial_estado_orden`.

**Casos de error**:
- Orden 2 del seed (4 bujías, stock 2) → **409**; estado, stock, movimientos e historial quedan exactamente igual (C-11).
- Tras reponer bujías → 200, baja el stock, aparecen movimientos y línea de historial; el aviso sale en el log después de la respuesta (C-12).

> **Fuera de alcance**: dos terminaciones simultáneas pueden producir una actualización perdida del stock (cap. 7).

---

## Flujo 9: Cancelar orden (RN-11, RN-12)
**Disparador**: `POST /ordenes/{id}/cancelar` · **Actor**: RECEPCION, ADMIN o dueño del vehículo — **sin `requiere_rol`**

1. Orden inexistente → 404.
2. **Primero el permiso**: si no es RECEPCION/ADMIN vigente ni dueño del vehículo → 403.
3. **Después el estado**: si no es `PENDIENTE` → 409.
4. UoW: `estado = CANCELADA` + línea de historial. 200.

---

## Flujo 10: Reposición de stock (RN-14)
**Disparador**: `POST /repuestos/{id}/reponer` · **Actor**: ADMIN

1. Contrato: `{cantidad (> 0), motivo? (≤ 120)}` (422 si no cumple; DD-29).
2. Repuesto inexistente o dado de baja → 404.
3. UoW: punto único de escritura → `stock += cantidad` + `movimiento_stock` positivo con el motivo enviado o «Reposición». 200 con el repuesto y su stock.

---

## Flujo 11: Cambio de precio (RN-20)
**Disparador**: `PATCH /repuestos/{id}` · **Actor**: ADMIN

1. Contrato: sólo `descripcion` y/o `precio` (`extra="forbid"` → `stock` da 422); `exclude_unset`.
2. UoW: si `precio` viene y es distinto del actual → actualiza y agrega `historial_precio_repuesto (anterior, nuevo, usuario)` en la misma transacción; si no cambia el precio → no hay línea. 200.
3. RECEPCION → 403 (C-18).

---

## Flujo 12: Baja lógica de vehículo (RN-16)
**Disparador**: `DELETE /vehiculos/{id}` · **Actor**: RECEPCION, ADMIN

1. Vehículo inexistente o ya dado de baja → 404 (DD-22).
2. Si tiene órdenes en un estado con `es_final = false` → 409.
3. `soft_delete` → `borrado_en = now()`. 204.
4. Otro cliente puede registrar la misma patente (201); una segunda patente vigente igual → 409 (C-19).

---

## Flujo 13: Listado paginado
**Disparador**: `GET /repuestos?q=freno&page=1&size=1` (y demás listados)

1. Contrato: `page ≥ 1`, `1 ≤ size ≤ 100` (500 → 422).
2. `total = count(con los mismos filtros)`; `pages = max(1, ceil(total / size))`.
3. `page > pages` → 422 «La página N no existe: hay M».
4. Búsqueda con parámetros ligados: `q=' OR '1'='1` devuelve lista vacía con `total 0` (C-16).

```json
{ "items": [ { "id": 1, "codigo": "FIL-001", "descripcion": "Filtro de aceite", "precio": "8500.00", "stock": 10 },
             { "id": 2, "codigo": "FRE-010", "descripcion": "Pastillas de freno delanteras", "precio": "32000.00", "stock": 4 } ],
  "total": 4, "page": 1, "size": 2, "pages": 2 }
```
