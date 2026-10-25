# Actores y Roles

## Actores del sistema

| Actor | Descripción | Cómo interactúa |
|---|---|---|
| Visitante | Persona sin sesión | Health, registro, login, logout |
| `CLIENTE` | Cliente que se auto-registró (o cuyo usuario está vinculado a una ficha de cliente) | `/mis-vehiculos`, `/mis-ordenes`, detalle de sus órdenes, cancelar sus órdenes pendientes, `/estados-orden`, `/auth/*` |
| `RECEPCION` | Personal de recepción | Alta de clientes y vehículos, baja de vehículos, alta y cancelación de órdenes, consulta de repuestos y órdenes |
| `MECANICO` | Personal de taller | Inicia órdenes (queda asignado), termina las órdenes que tiene asignadas, consulta repuestos y órdenes |
| `ADMIN` | Administrador | Todo lo de recepción + catálogo de repuestos, reposición, precios, alta de personal, roles, eventos de seguridad; puede terminar cualquier orden |
| `SISTEMA` | Actor **de texto** (no es un usuario) | Aparece en `evento_seguridad.actor` para los datos iniciales |

Roles válidos (CHECK en `asignacion_rol.rol`): **`ADMIN`, `RECEPCION`, `MECANICO`, `CLIENTE`**.

## Modelo de roles

- `usuario` **no tiene columna `rol`**. Los roles de una persona son las filas de `asignacion_rol` **vigentes**: no revocadas (`revocada_en IS NULL`) y sin vencer (`vence_en` nulo o futuro).
- Revocar un rol escribe `revocada_en`; la fila **nunca se borra** → queda el historial de quién tuvo qué rol y hasta cuándo (sección 5.9).
- A lo sumo **una asignación abierta por (usuario, rol)** → índice único parcial `(usuario_id, rol) WHERE revocada_en IS NULL` (RN-03).
- Reasignar un rol **vencido** cierra la fila anterior y abre una nueva.
- Los roles del token son **informativos**; los permisos se deciden con los roles vigentes **en la base, en cada petición** (RN-04). Revocar un rol le quita el permiso a una sesión ya abierta, sin esperar a que el token venza.
- Un usuario puede tener varios roles a la vez (la tabla lo permite). **Suposición** — ver [09](09_decisiones_y_supuestos.md).

## RBAC — Matriz de permisos

Leyenda: ✅ permitido · 🔸 condicionado · — no permitido (403)

| Endpoint | ADMIN | RECEPCION | MECANICO | CLIENTE / sólo autenticado |
|---|---|---|---|---|
| `GET /auth/yo`, `POST /auth/cambiar-password` | ✅ | ✅ | ✅ | ✅ |
| `POST /usuarios`, `GET/POST /usuarios/{id}/roles`, `DELETE /usuarios/{id}/roles/{rol}` | ✅ (RN-05) | — | — | — |
| `GET /eventos` | ✅ | — | — | — |
| `POST /clientes`, `GET /clientes/{id}`, `POST /clientes/{id}/vehiculos`, `DELETE /vehiculos/{id}` | ✅ | ✅ | — | — |
| `GET /mis-vehiculos`, `GET /mis-ordenes` | ✅ | ✅ | ✅ | ✅ (sólo lo propio) |
| `GET /repuestos`, `GET /repuestos/{id}` | ✅ | ✅ | ✅ | — |
| `POST /repuestos`, `PATCH`, `DELETE`, `/reponer`, `/movimientos`, `/precios` | ✅ | — | — | — |
| `POST /ordenes` | ✅ | ✅ | — | — |
| `GET /ordenes` | ✅ | ✅ | ✅ | — |
| `GET /ordenes/{id}` | ✅ | ✅ | ✅ (cualquiera, DD-27) | 🔸 sólo si es dueño del vehículo |
| `POST /ordenes/{id}/iniciar` | — | — | ✅ | — |
| `POST /ordenes/{id}/terminar` | ✅ | — | 🔸 sólo el mecánico asignado | — |
| `POST /ordenes/{id}/cancelar` | ✅ | ✅ | — | 🔸 sólo el dueño del vehículo |
| `GET /estados-orden` | ✅ | ✅ | ✅ | ✅ |

Notas:
- "El personal" en `GET /ordenes/{id}` = ADMIN, RECEPCION, MECANICO, y ve **cualquier** orden (DD-27).
- `/ordenes/{id}/iniciar` es **sólo MECANICO** (la tabla de endpoints no incluye ADMIN).
- `/mis-*` sólo pide estar autenticado (RN-17); un usuario sin ficha de cliente obtiene una lista vacía (SU-11). `/mis-vehiculos` muestra sólo los vigentes y `/mis-ordenes` todas, incluidas las de vehículos dados de baja (DD-28).

## 401 vs 403

| Situación | Código | Quién lo decide |
|---|---|---|
| Sin cookie, token inválido o vencido, usuario inexistente o inactivo, token anterior al último cambio de contraseña (RN-07) | **401** | `get_usuario_actual` |
| Token enviado por `Authorization: Bearer` y no por cookie | **401** (C-03) | `get_usuario_actual` (lee sólo `request.cookies`) |
| Autenticado pero sin el rol vigente requerido | **403** | `requiere_rol` (consulta `asignacion_rol`) |
| Cambio de contraseña pendiente y ruta protegida | **403** | control montado en el grupo protegido (RN-06) |
| Autenticado pero el recurso no es propio (`/ordenes/{id}`, cancelar) | **403** | servicio (comprobación de dueño, RN-17 / RN-12) |

## Rutas públicas

- `GET /health/live`
- `GET /health/ready`
- `POST /auth/registro`
- `POST /auth/login`
- `POST /auth/logout`

`GET /auth/yo` y `POST /auth/cambiar-password` están en el **grupo abierto** (no los bloquea el cambio obligatorio) pero requieren sesión.

## Usuarios iniciales (seed)

| Correo | Rol | Notas |
|---|---|---|
| `admin@example.com` | ADMIN | |
| `admin2@example.com` | ADMIN | Permite probar que el sistema nunca queda sin admins (RN-05) |
| `recepcion@example.com` | RECEPCION | |
| `mecanico@example.com` | MECANICO | Asignado a la orden 2 |
| `mecanico2@example.com` | MECANICO | |
| `cliente@example.com` | CLIENTE | Usuario de la clienta Laura |
| `nuevo@example.com` | MECANICO | Con cambio de contraseña obligatorio (`debe_cambiar_password = true`) |
