# Preguntas Abiertas

> La consigna es la única fuente: cuando algo no está fijado, se implementa con el supuesto de [09](09_decisiones_y_supuestos.md) y se deja anotado acá para consultar con la cátedra.

## Inconsistencias detectadas

### IN-01 — Diagrama de clases vs. tabla de columnas
**Figura 1 dice**: `AsignacionRol` sin `otorgada_por`; `Usuario` sin `password_cambiada_en`; `HistorialEstadoOrden`, `MovimientoStock` e `HistorialPrecio` sin `usuario_id`; `Cliente` sin `usuario_id` (sólo la relación).
**Tabla del modelo dice**: todas esas columnas existen.
**Impacto**: bajo; los nombres de la tabla son los obligatorios.
**Resolución propuesta**: la tabla manda; el diagrama sólo muestra relaciones.

### IN-02 — Nombre de clase vs. tabla del historial de precios
**Diagrama/módulos**: `HistorialPrecio`. **Tabla**: `historial_precio_repuesto`.
**Resolución propuesta**: clase `HistorialPrecio` con `__tablename__ = "historial_precio_repuesto"`.

### IN-03 — Orden 1 del seed sin ítems especificados
**RN-10**: una orden nace con al menos un ítem. **Datos iniciales**: la orden 1 no lista ítems.
**Resuelta** (2026-10-25): DD-15 — 1 filtro + 4 L de aceite, total 56500.00.

### IN-04 — Historial y movimientos de las órdenes del seed
El seed carga la orden 2 en `EN_REPARACION`, pero no dice si lleva su historial (`null→PENDIENTE`, `PENDIENTE→EN_REPARACION`).
**Resuelta** (2026-10-25): DD-14 — historial coherente con su estado (alta por recepción, inicio por mecanico@).

## Preguntas resueltas (2026-10-25, revisión con el equipo)

| Pregunta (era Alta) | Resolución |
|---|---|
| `usuario_id` de las escrituras del seed | DD-14 |
| Ítems de la orden 1 del seed | DD-15 |
| Precio y código de la bujía | DD-16 (`BUJ-014`, 6500.00) |
| Cuerpo de `POST /auth/registro` | DD-17 (plano + cookie de sesión, pedido verbal del docente) |
| Cuerpo de `POST /usuarios` | DD-18 (con rol inicial de personal) |

Pedidos verbales del docente registrados en la misma revisión: DD-19 (todo commit pasa por un UoW) y DD-20 (clave JWT fija).

## Preguntas abiertas (priorizadas)

**No quedan preguntas abiertas** (2026-10-25). Las de prioridad Media y Baja se resolvieron con el criterio de producción del equipo:

| Pregunta (prioridad) | Resolución |
|---|---|
| ¿Se puede dar de baja un repuesto en órdenes abiertas? (Media) | DD-21 — sí, 204 |
| ¿Se puede terminar una orden cuyo repuesto se dio de baja después? (Media) | DD-21 — sí, normal |
| `DELETE` sobre un recurso ya dado de baja (Media) | DD-22 — 404 |
| `stock_inicial = 0` (Media) | DD-23 — se permite, sin movimiento |
| Login de usuario inactivo (Media) | DD-24 — 401 genérico; mensaje claro sólo con contraseña correcta |
| Acciones de `evento_seguridad` (Media) | DD-26 |
| Qué órdenes ve un MECANICO (Media) | DD-27 — cualquiera |
| `/mis-*` y vehículos dados de baja (Media) | DD-28 |
| Motivos de `movimiento_stock` (Baja) | DD-29 |
| Cuerpo de `/reponer` (Baja) | DD-29 |
| Nombres de variables de entorno (Baja) | DD-30 |
| ¿El ADMIN que termina queda como `mecanico_id`? (Baja) | DD-31 — no |
| ¿Docker? (Baja) | DD-32 — app + base |

Pedido general del usuario registrado en la misma revisión: DD-25 (mensajes de error en lenguaje humano).

Si durante la implementación aparece una duda nueva, se agrega acá con su prioridad (regla D-4 de `AGENTS.md`).

## Discovery (`state.kb.discovery`)

Todos los campos se pudieron inferir con confianza alta desde la consigna, salvo:

- [DISCOVERY] `needs_infra`: `true` — PostgreSQL 16 + Docker (app + base) para el equipo (DD-32). Resuelto.
