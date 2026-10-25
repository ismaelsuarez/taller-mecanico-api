# Reglas de Negocio

> Se conservan **los códigos originales de la consigna (RN-01 … RN-20)** porque la corrección y los casos de prueba los referencian. Se agrupan por dominio para facilitar la navegación. Las reglas técnicas que surgen de los ejercicios y requisitos no funcionales llevan el prefijo **RT-** (código propio de esta KB, no de la consigna).

## Dominio: Identidad y unicidad

- **RN-01** — El correo de un usuario y el documento de un cliente son únicos. La patente de un vehículo y el código de un repuesto son únicos entre los que no están dados de baja.
  *Garante*: UNIQUE e índices únicos parciales en la base; **409 con mensaje propio**. La unicidad **no** se verifica con una consulta previa.

## Dominio: Registro y usuarios (RN-02, RN-03, RN-05)

- **RN-02** — El auto-registro crea el usuario, su rol `CLIENTE` y su ficha de cliente: **o quedan las tres filas, o ninguna**. Si el documento ya es de un cliente del taller, el registro da **409** y **no se apropia de esa ficha**.
  *Garante*: un solo Unit of Work.
- **RN-03** — Un usuario tiene a lo sumo **una asignación abierta por rol**.
  *Garante*: índice único parcial; **409**.
- **RN-05** — Un administrador **no puede revocarse su propio rol ADMIN**, y el sistema **nunca queda sin administradores vigentes**.
  *Garante*: comprobación en el servicio; **409**.

## Dominio: Autenticación y sesión (RN-06 … RN-09)

- **RN-06** — Mientras un usuario tenga el cambio de contraseña pendiente, sólo puede usar las rutas de `/auth` y las de salud.
  *Garante*: dos grupos de rutas; **403**.
- **RN-07** — Al cambiar la contraseña, las sesiones emitidas antes dejan de valer, **aunque sean del mismo segundo que el cambio**; la que devuelve el propio cambio, no.
  *Garante*: comparación de `iat` con `password_cambiada_en`, **sin truncar**; **401**.
- **RN-08** — Después de **5 intentos fallidos con el mismo correo desde la misma dirección en 60 segundos**, el login responde **429 sin verificar la contraseña**. Un login correcto reinicia la cuenta: los fallos anteriores siguen en la tabla, pero dejan de contar.
  *Garante*: conteo sobre `intento_acceso`; cabecera `Retry-After`.
- **RN-09** — El login responde **lo mismo, y tarda lo mismo**, exista o no el correo.
  *Garante*: mismo mensaje; verificación contra un **hash ficticio**.

## Dominio: Autorización (RN-04, RN-17)

- **RN-04** — Los permisos se deciden con los **roles vigentes en la base, en cada petición**. Los roles que trae el token son informativos.
  *Garante*: dependencia que consulta `asignacion_rol`.
- **RN-17** — Lo propio sólo pide estar autenticado: un cliente ve sus vehículos y las órdenes de sus vehículos, y ninguna otra.
  *Garante*: rutas `/mis-*` y comprobación de dueño; **403**.

## Dominio: Órdenes de trabajo (RN-10 … RN-13, RN-19)

- **RN-10** — Una orden nace `PENDIENTE` con **al menos un ítem** y **sin repuestos repetidos**. El precio de cada ítem **se copia del repuesto**, y el total lo calcula el servidor.
  *Garante*: DTO; **el precio y el total nunca viajan en el cuerpo**.
- **RN-11** — Transiciones permitidas:
  - `PENDIENTE → EN_REPARACION` (la inicia un mecánico, que queda asignado)
  - `EN_REPARACION → TERMINADA` (la termina el mecánico asignado o un administrador)
  - `PENDIENTE → CANCELADA`

  *Garante*: servicio; **409 si el estado no lo permite**.
- **RN-12** — Cancelan una orden la recepción, el administrador o el dueño del vehículo. **El permiso se evalúa antes que el estado.**
  *Garante*: servicio; **403 antes que 409**.
- **RN-13** — Terminar una orden descuenta el stock de cada ítem, deja **un movimiento por cada salida** y **una línea de historial**. Si un repuesto no alcanza, **no queda ninguna de esas escrituras**.
  *Garante*: un solo Unit of Work; **409**.
- **RN-19** — Los estados posibles de una orden son las filas del catálogo `estado_orden`. El catálogo se consulta desde la API y **no se edita desde ella**. Si está vacío, crear una orden responde **409 con un mensaje propio**.
  *Garante*: clave foránea; repositorio de sólo lectura.

Diagrama de estados:

```
           iniciar (MECANICO, queda asignado)          terminar (mecánico asignado | ADMIN)
PENDIENTE ─────────────────────────────────► EN_REPARACION ───────────────────────────────► TERMINADA (final)
    │
    │ cancelar (RECEPCION | ADMIN | dueño)
    ▼
CANCELADA (final)
```

Cualquier otra transición → 409.

## Dominio: Stock y repuestos (RN-14, RN-16, RN-20)

- **RN-14** — El stock de un repuesto **sólo cambia a través de movimientos**: el alta con stock inicial, la reposición y la terminación de órdenes. **No se edita por PATCH.**
  *Garante*: punto único de escritura de stock.
- **RN-16** — Un vehículo o un repuesto dado de baja **deja de aparecer** y **no se puede usar en órdenes nuevas**, pero sus datos se conservan. Un vehículo con órdenes abiertas —en un estado que el catálogo no marca como final— **no se da de baja**.
  *Garante*: borrado lógico; `es_final`; **409**.
- **RN-20** — Cada cambio del precio de un repuesto deja una línea en `historial_precio_repuesto`, **en la misma transacción** que el cambio. Un PATCH que **no cambia el precio no deja línea**.
  *Garante*: un solo Unit of Work; CHECK `precio_nuevo <> precio_anterior`.

## Dominio: Integridad y auditoría (RN-15)

- **RN-15** — `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto` son de **sólo agregado**: nadie puede modificar ni borrar sus filas.
  *Garante*: disparador en la base, instalado por migración (escrita a mano).

## Dominio: Errores (RN-18)

- **RN-18** — Ningún error devuelve al cliente texto interno de la base, que le entregaría el mapa del esquema (sección 4.13). **Ninguna entrada inválida termina en un 500.**
  *Garante*: traducción del `IntegrityError`; validación en el contrato.

## Dominio: Contratos y paginación (RT-PG)

- **RT-PG-01** — Contratos de entrada con `extra="forbid"`: nadie se registra con un rol ni edita el stock por PATCH (→ 422).
- **RT-PG-02** — Contratos separados de los modelos de tabla; ninguna respuesta incluye `password_hash`.
- **RT-PG-03** — Los PATCH aplican sólo los campos enviados (`exclude_unset`, sección 2.6).
- **RT-PG-04** — Códigos: 201 al crear, 204 al dar de baja, 404 si el recurso de la ruta no existe, 409 si choca con lo guardado, 422 si el cuerpo o los parámetros no cumplen el contrato.
- **RT-PG-05** — Envoltorio `{items, total, page, size, pages}`: `page` empieza en 1; `size` de 1 a 100 (por defecto 20); pedir una página más allá de la última da **422** (mensaje: «La página 3 no existe: hay 2»); `total` cuenta con los mismos filtros que la página; con cero resultados hay **una página, vacía**.
- **RT-PG-06** — La búsqueda de repuestos por descripción usa **parámetros ligados**; nunca SQL armado por concatenación con datos del usuario.
- **RT-PG-07** — Un parámetro de ruta que no es entero da **422 sin ejecutar el handler** (C-01).
- **RT-PG-08** — Filtrar órdenes por un estado que el contrato (enum) no declara da **422** (C-17).

## Dominio: Seguridad técnica (RT-SE)

- **RT-SE-01** — bcrypt con **costo declarado en la configuración**, nunca fijo en el código.
- **RT-SE-02** — Toda llamada a bcrypt corre **fuera del bucle de eventos** (`asyncio.to_thread`) y bajo un **semáforo** que limita cuántas corren a la vez.
- **RT-SE-03** — El hash se calcula **antes de abrir la transacción** (si no, la conexión quedaría tomada ~300 ms sin usar la base).
- **RT-SE-04** — Todo campo que termina en bcrypt —también la contraseña del login y la actual del cambio— acepta **como máximo 72 bytes** (bytes, no caracteres: una «ñ» ocupa dos) → 422, nunca 500.
- **RT-SE-05** — Orden del login: (1) límite de intentos (una consulta; si se superó, 429 + `Retry-After` sin calcular ningún hash); (2) verificación contra el hash del usuario o contra el hash ficticio.
- **RT-SE-06** — JWT firmado con `sub`, `iat` (con fracción de segundo), `exp` y los roles vigentes al emitirlo.
- **RT-SE-07** — El token viaja **sólo** en la cookie `access_token`: `HttpOnly`, `SameSite=Lax`, `Max-Age` = duración del token, `Secure` configurable. El cuerpo del login no lo trae; la dependencia lo lee de `request.cookies` (nunca de `Authorization`).
- **RT-SE-08** — Ninguna contraseña ni clave de firma en el código (tampoco como valor por defecto), en `alembic.ini` ni en el repositorio.
- **RT-SE-09** — Cada intento de login, correcto o fallido, se anota en `intento_acceso` desde **una sesión y una transacción propias, que se confirman siempre**, mediante un **UoW dedicado** (DD-19). Es la única escritura que no comparte la transacción de su petición. El código lo declara en un comentario, junto con su costo: deja filas aunque la petición falle.
- **RT-SE-12** — La clave de firma del JWT es **fija** (`JWT_SECRET` del entorno) y nunca se genera al arrancar: si cambiara en cada reinicio, todas las sesiones se invalidarían (DD-20; consigna 5.12 + pedido del docente).
- **RT-SE-13** — El registro deja la sesión iniciada: 201 con `Set-Cookie access_token` emitida después del commit del UoW (DD-17).
- **RT-SE-10** — El historial de seguridad (`evento_seguridad`) registra las altas, los cambios de rol y de contraseña, y los datos iniciales con el actor `SISTEMA` (texto, no un usuario).
- **RT-SE-11** — Vencimiento de un rol: debe llegar **con zona horaria** y **en el futuro**; si no, **422** (no 409).

## Dominio: Transacciones y persistencia (RT-TX)

- **RT-TX-01** — Ningún repositorio confirma: `add` y `update` hacen `flush()`, nunca `commit()`. **Todo commit del sistema pasa por un Unit of Work** (DD-19, pedido del docente), incluido el de `intento_acceso`.
- **RT-TX-02** — Ningún servicio construye su Unit of Work; el router lo construye con una dependencia y se lo pasa sin abrir; el servicio lo abre con `async with`.
- **RT-TX-03** — El Unit of Work confirma al salir del bloque, revierte si sale con excepción y **no cierra la sesión** (no la creó).
- **RT-TX-04** — Las operaciones de RN-02, RN-13 y RN-20 se escriben **cada una en un solo bloque** de UoW.
- **RT-TX-05** — Carga perezosa **prohibida**: toda relación que se lee se precarga en el repositorio, declarada dentro del método que la necesita.
- **RT-TX-06** — El detalle de una orden se resuelve con un **número fijo de consultas** que no crece con la cantidad de ítems (C-15).
- **RT-TX-07** — El aviso al cliente al terminar una orden se agenda con `BackgroundTasks`, corre **después de enviar la respuesta** y **sólo si la operación se confirmó**.

## Dominio: Decisiones del equipo (RT-EQ)

- **RT-EQ-01** — Todo mensaje de error para el usuario va en español claro, sin jerga técnica ni nombres de tablas, columnas, restricciones o trazas (DD-25).
- **RT-EQ-02** — Baja de repuesto siempre 204; las órdenes ya creadas con ese repuesto siguen su ciclo normal (DD-21).
- **RT-EQ-03** — `DELETE` sobre un recurso ya dado de baja → 404 (DD-22).
- **RT-EQ-04** — `stock_inicial ≥ 0`; con 0 no hay movimiento (DD-23).
- **RT-EQ-05** — Login de cuenta inactiva: 401 genérico salvo contraseña correcta → mensaje «Tu cuenta está desactivada…» (DD-24).
- **RT-EQ-06** — `evento_seguridad` registra altas, roles, cambios de contraseña, bloqueo por intentos (429) y datos iniciales (DD-26).
- **RT-EQ-07** — El personal ve cualquier orden; `/mis-vehiculos` sólo vigentes, `/mis-ordenes` todas (DD-27, DD-28).
- **RT-EQ-08** — Motivos de stock armados por el servidor; `/reponer` con `motivo` opcional (DD-29).
- **RT-EQ-09** — Terminar no cambia `mecanico_id` (DD-31).

## Excepciones globales

- Toda ruta protegida: **401** sin sesión y **403** con cambio de contraseña pendiente.
- `IntegrityError` siempre traducido a un mensaje propio (409/422 según el caso).
- Las consultas se pueden ver en consola (`SQL_ECHO=true` o equivalente).
