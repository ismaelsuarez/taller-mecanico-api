# Visión y Objetivos

> Fuente única: `docs/TP_Cap1a6_Consigna.pdf` (Programación III · UTN · Unidades 1 a 6 · "Del objeto a la transacción").
> Todo lo que no figura en la consigna está marcado como **Suposición** y registrado en [09](09_decisiones_y_supuestos.md) / [10](10_preguntas_abiertas.md).

## Propósito del sistema

**API REST asincrónica para el trabajo diario de un taller mecánico: órdenes de trabajo, stock de repuestos y control de acceso, construida con FastAPI y PostgreSQL.**

Un taller mecánico necesita una API para su trabajo diario. La recepción da de alta a los clientes y a sus vehículos, y abre una orden de trabajo por cada ingreso, con la falla que describe el cliente y los repuestos que se van a usar. Un mecánico toma la orden, la repara y la da por terminada: en ese momento se descuenta del stock cada repuesto usado. El administrador mantiene el catálogo de repuestos, repone el stock y administra al personal y sus roles. Los clientes se registran solos en la web y consultan el estado de sus vehículos.

Es un **trabajo práctico integrador**: el dominio está elegido para que cada capítulo (1 a 6) tenga un lugar concreto donde aparecer.

## Objetivos pedagógicos (lo que el proyecto debe demostrar)

1. Construir una API asincrónica en capas —**Router → Service → UoW → Repository → Model**— donde cada capa sabe lo suyo y nada más.
2. Traducir un modelo con asociación, composición, uno a uno y una tabla de catálogo a un esquema relacional versionado con **Alembic**, incluida una migración escrita a mano.
3. Autenticar con contraseñas guardadas con **bcrypt** y un token en una **cookie HttpOnly**, sin frenar el servidor y sin revelar qué cuentas existen.
4. Autorizar consultando los roles **en la base en cada petición**, con vigencia, y distinguir siempre entre **401 y 403**.
5. Agrupar en **una sola transacción** las escrituras de una operación de negocio, de modo que un fallo en el medio no deje datos a medias.
6. Delegar en la base las garantías que la base puede dar: unicidad, claves foráneas, comprobaciones y el sólo agregado.

### Mapa dominio → capítulo

| Lo que pide el dominio | Por qué | Capítulo |
|---|---|---|
| La orden nace con sus ítems; un ítem no existe sin su orden | Composición: los datos de cada ítem viajan dentro del alta de la orden | 4 |
| Un cliente puede tener o no un usuario, y a lo sumo uno | Uno a uno opcional: `cliente.usuario_id` UNIQUE y nulo permitido | 4 |
| Un vehículo vendido se da de baja, sus órdenes viejas siguen y el comprador lo puede registrar con la misma patente | Borrado lógico e índice único parcial | 4 y 6 |
| Cuatro roles, que el administrador asigna y revoca con vigencia | La autorización se decide en la base, no en el token | 5 |
| El registro crea el usuario, su rol y su ficha de cliente | Tres escrituras que no tienen sentido por separado | 6 |
| Terminar una orden descuenta el stock de cada repuesto | Cuatro clases de escritura en una sola transacción | 6 |
| El límite de intentos de login se calcula contando una tabla | El intento tiene que sobrevivir al rollback del login fallido | 5 y 6 |
| Los estados de una orden son una lista fija que el sistema necesita para funcionar | Catálogo: tabla de referencia, apuntada con FK y cargada por `seed.py` | 4 |
| El historial de estados, los movimientos de stock y los cambios de precio no se corrigen | Sólo agregado, impuesto por la base | 6 |

## Objetivos por actor

| Actor | Objetivo principal | Objetivos secundarios |
|---|---|---|
| Recepción (`RECEPCION`) | Dar de alta clientes y vehículos y abrir órdenes de trabajo | Cancelar órdenes pendientes, dar de baja vehículos, consultar repuestos y órdenes |
| Mecánico (`MECANICO`) | Tomar una orden, repararla y darla por terminada | Consultar repuestos y órdenes |
| Administrador (`ADMIN`) | Mantener el catálogo de repuestos, reponer stock y administrar personal y roles | Todo lo de recepción; terminar cualquier orden; ver eventos de seguridad, movimientos e historial de precios |
| Cliente (`CLIENTE`) | Registrarse solo en la web y consultar el estado de sus vehículos | Ver sus órdenes y cancelar las suyas pendientes |
| Sistema (`SISTEMA`, actor de texto) | Cargar los datos iniciales | Registrarse como actor en `evento_seguridad` |

## Alcance (TP Unidades 1–6)

- Ciclo de vida de la app (lifespan), configuración desde el entorno y endpoints de salud (`/health/live`, `/health/ready`).
- Modelo de dominio completo con restricciones, 3 índices únicos parciales, catálogo `estado_orden` y 3 tablas de sólo agregado.
- Esquema creado **exclusivamente** con Alembic: 2 migraciones (una autogenerada, una escrita a mano con el disparador).
- Contratos (DTOs) separados de los modelos, CRUD, paginación con envoltorio `{items, total, page, size, pages}`.
- Autenticación: registro, login con límite de intentos, logout, `GET /auth/yo`, cambio de contraseña; JWT en cookie HttpOnly.
- Autorización: roles vigentes consultados en la base en cada petición, asignación/revocación con vencimiento, autoprotección del ADMIN, cambio obligatorio de contraseña, "lo propio" (`/mis-*`).
- Repositorios genéricos (`BaseRepository[T]`, `SoftDeleteRepository[T]`), Unit of Work base y por módulo, operaciones multi-escritura atómicas.
- Lecturas sin N+1 (carga anticipada declarada en el repositorio), todo `async def`, aviso al cliente con `BackgroundTasks`.
- `seed.py` con los datos iniciales obligatorios y casos de prueba en `test/*.http` + `test/solo_agregado.sql`.

## Fuera de alcance (explícito en la consigna)

- **Concurrencia (capítulo 7)**: no se evalúa. Dos órdenes que se terminan al mismo tiempo pueden producir una *actualización perdida* de stock (el CHECK impide el negativo, no la pérdida). El bloqueo que la evita es tema de la próxima clase.
- **Colas de tareas con Redis (capítulo 8)**: el aviso al cliente se resuelve con `BackgroundTasks` en el mismo proceso. Se acepta que si el proceso se reinicia el aviso se pierde y que no hay reintento (el aviso es simulado).
- **Segundo mecanismo de sólo agregado por permisos del rol de base** (sección 6.9): no se pide; el TP usa un solo rol de base.
- Envío real de notificaciones: el aviso es simulado (`await asyncio.sleep(0.5)` + mensaje en el registro).
- Edición del catálogo de estados desde la API (RN-19).
- Frontend: la consigna sólo pide la API. **Suposición**: "se registran solos en la web" se refiere al endpoint `POST /auth/registro`, no a construir una web.

## Métricas de éxito (criterios de evaluación)

| Criterio | Peso |
|---|---|
| Proyecto, configuración y ciclo de vida | 8 % |
| Modelos, relaciones y migraciones | 14 % |
| Contratos y CRUD | 10 % |
| Autenticación | 16 % |
| Autorización | 14 % |
| Repositorios y Unit of Work | 20 % |
| Integridad | 10 % |
| Lecturas sin N+1 y asincronía | 8 % |

**Condición bloqueante**: un proyecto que no levanta, que no crea su esquema con `alembic upgrade head` sobre una base vacía o que contiene credenciales reales en el repositorio **no se corrige hasta que se subsane**.

Detalle de casos de prueba, criterios y entrega: [11_casos_de_prueba_y_entrega.md](11_casos_de_prueba_y_entrega.md).
