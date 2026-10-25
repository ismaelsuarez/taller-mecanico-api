# Taller Mecánico (TP Programación III) — Instrucciones para Agentes

> Este archivo (y su copia `CLAUDE.md`) es lo PRIMERO que todo agente lee al entrar al repo.
> Generado a partir de `knowledge-base/` y `CHANGES.md`. No editar a mano sin re-sincronizar ambos archivos.

API REST asincrónica para un taller mecánico (clientes, vehículos, órdenes de trabajo, stock de repuestos y control de acceso por roles). Trabajo práctico integrador de los capítulos 1 a 6. **La consigna (`docs/TP_Cap1a6_Consigna.pdf`) es la única fuente de verdad**; la KB la transcribe y marca como **Suposición** todo lo que la consigna no fija.

---

## Stack Tecnológico

| Componente | Versión mínima | Uso |
|---|---|---|
| Python | 3.12 | Lenguaje |
| FastAPI | 0.111 | Framework web; todos los handlers con `async def` |
| SQLModel | 0.0.24 | Modelos de tabla |
| SQLAlchemy | 2.0, asincrónico | Motor, sesión y carga anticipada |
| asyncpg | 0.30 | Controlador asincrónico de PostgreSQL (se acepta psycopg 3 async) |
| PostgreSQL | 16 | Base de datos |
| Alembic | 1.13, plantilla asincrónica | Migraciones |
| pydantic-settings | 2.0 | Configuración leída del entorno |
| bcrypt | 4.0 | Hash de las contraseñas |
| PyJWT | 2.8 | Token firmado |
| uvicorn | El que instala `fastapi[standard]` | Servidor ASGI |
| pytest + httpx | — | Tests automáticos del proyecto (decisión del equipo, ver Reglas Duras) |
| Docker / Docker Compose | — | Entorno del equipo: `api` + `db` (`postgres:16`) (decisión del equipo, DD-32) |

Detalle completo: [knowledge-base/02_descripcion_general.md](knowledge-base/02_descripcion_general.md)

---

## Base de Conocimiento

La fuente de verdad del dominio vive en `knowledge-base/`. **Leé el archivo relevante ANTES de implementar.**

| Archivo | Cuándo leerlo |
|---|---|
| [01_vision_y_objetivos.md](knowledge-base/01_vision_y_objetivos.md) | Propósito, alcance y qué queda afuera (concurrencia, Redis) |
| [02_descripcion_general.md](knowledge-base/02_descripcion_general.md) | Stack, capas y **todos los endpoints** con sus códigos |
| [03_actores_y_roles.md](knowledge-base/03_actores_y_roles.md) | Roles, matriz RBAC, 401 vs 403 |
| [04_modelo_de_datos.md](knowledge-base/04_modelo_de_datos.md) | Tablas/columnas obligatorias, índices parciales, migraciones, seed |
| [05_reglas_de_negocio.md](knowledge-base/05_reglas_de_negocio.md) | RN-01..RN-20 (códigos de la consigna) y reglas técnicas RT-* |
| [06_funcionalidades.md](knowledge-base/06_funcionalidades.md) | Épicas por ejercicio e historias US-xxx |
| [07_flujos_principales.md](knowledge-base/07_flujos_principales.md) | Flujos E2E (login, terminar orden, cancelar, etc.) |
| [08_arquitectura_propuesta.md](knowledge-base/08_arquitectura_propuesta.md) | Estructura de directorios obligatoria, seguridad, variables de entorno |
| [09_decisiones_y_supuestos.md](knowledge-base/09_decisiones_y_supuestos.md) | Decisiones DD-xx y supuestos SU-xx |
| [10_preguntas_abiertas.md](knowledge-base/10_preguntas_abiertas.md) | ⚠️ Inconsistencias y preguntas para la cátedra |
| [11_casos_de_prueba_y_entrega.md](knowledge-base/11_casos_de_prueba_y_entrega.md) | Casos C-01..C-19, criterios de evaluación, formato de entrega |

> ⚠️ No quedan preguntas abiertas: todas se resolvieron en `09_decisiones_y_supuestos.md` (DD-14..DD-32). Los pedidos verbales del docente están en DD-17, DD-19 y DD-20. Si aparece una duda nueva, se anota en `10_preguntas_abiertas.md` (regla D-4).

---

## Skills Disponibles

| Agente | Rol | Skills que carga |
|---|---|---|
| **Backend Core** | FastAPI, contratos, routers, servicios, configuración | `fastapi`, `fastapi-templates` (sólo como referencia, ver regla A-2), `pydantic`, `python-configuration`, `python-error-handling` |
| **Persistencia** | Modelos, migraciones, repositorios, Unit of Work, consultas sin N+1 | `sqlmodel`, `sqlalchemy`, `alembic`, `postgresql-table-design`, `supabase-postgres-best-practices`, `python-design-patterns` |
| **Seguridad** | bcrypt, JWT en cookie, roles vigentes, límite de intentos | `auth-implementation-patterns` (ignorar su consejo de `Bearer`, ver regla A-4), `security-best-practices` |
| **Asincronía** | Handlers async, `to_thread`, semáforo, `BackgroundTasks` | `async-python-patterns` |
| **Calidad** | TDD, pytest + httpx, casos `.http` | `tdd`, `python-testing-patterns` |
| **Entorno** | Dockerfile + Compose (`api` + `db`) | `docker-build-strategies`, `docker-compose-patterns` |
| **Orquestación** | OPSX, commits por unidad de trabajo, docs | `work-unit-commits`, `cognitive-doc-design`, `kb-creator`, `roadmap-generator`, `agents-md-generator` |

Cargá la skill correspondiente al contexto ANTES de escribir código.

Las skills son **del proyecto**, no globales: viven en `.agents/skills/` (enlazadas en `.claude/skills/`). 18 se restauran desde `skills-lock.json` con `bash scripts/setup.sh`; las 5 de orquestación y documentación (`work-unit-commits`, `cognitive-doc-design`, `kb-creator`, `roadmap-generator`, `agent-instruction`) están versionadas en el repo. Nunca referencies rutas absolutas de una máquina.

> Los compact rules de cada skill los resuelve el orquestador desde `.atl/skill-registry.md` (generado por `skill-registry`; no versionado — no está en el repo). Esta tabla solo mapea skill→rol.

---

## Roadmap de Changes

El plan de implementación completo está en [CHANGES.md](CHANGES.md). Resumen:

- **Total**: 8 changes, uno por ejercicio de la consigna, **estrictamente secuenciales** (trabajo en equipo por relevos).
- **Camino crítico** (8): `EJ-1 → EJ-2 → EJ-3 → EJ-4 → EJ-5 → EJ-6 → EJ-7 → EJ-8`.
- **Primer change**: `EJ-1` (`01-proyecto-config-lifespan`).

| EJ | Change | Puntos |
|---|---|---|
| EJ-1 | `01-proyecto-config-lifespan` | 8 |
| EJ-2 | `02-modelos-migraciones-seed` | 14 |
| EJ-3 | `03-contratos-crud` | 10 |
| EJ-4 | `04-autenticacion` | 16 |
| EJ-5 | `05-autorizacion` | 14 |
| EJ-6 | `06-repositorios-uow-ordenes` | 20 |
| EJ-7 | `07-integridad` | 10 |
| EJ-8 | `08-lecturas-sin-n1-asincronia` | 8 |

**Antes de cualquier `/opsx:propose`**: leé [CHANGES.md](CHANGES.md) (regla de relevo, decisiones transversales T-1..T-11, "Leer antes" y "Definition of Done / handoff" del change).

---

## Reglas Duras (específicas del proyecto)

> Reglas **globales** ya definidas en `~/.claude/CLAUDE.md` (orquestador, governance, Strict TDD, engram, Conventional Commits sin co-autoría IA, no commitear sin pedido): el proyecto las **hereda**, no se repiten acá. Acá viven solo las reglas **específicas de este proyecto**. Son contrato: romperlas es un defecto. Ante conflicto entre la KB y este archivo, prevalecen estas reglas; ante conflicto entre este archivo y la consigna, prevalece la consigna.

### A · Contrato de la consigna

- **A-1** NUNCA renombrar ni quitar tablas, columnas o rutas indicadas en la consigna → usar exactamente los nombres de `knowledge-base/04_modelo_de_datos.md` y `02_descripcion_general.md` (se pueden **agregar** columnas).
- **A-2** NUNCA adoptar la estructura de carpetas de `fastapi-templates` u otra plantilla → la estructura obligatoria es la de `knowledge-base/08_arquitectura_propuesta.md` (`main.py`, `seed.py`, `app/core/*`, `app/modules/<módulo>/{models,schemas,repository,unit_of_work,service,router}.py`, `migrations/`, `test/`).
- **A-3** NUNCA crear el esquema con `create_all` → sólo Alembic (plantilla async); la segunda migración (disparador de sólo agregado) se escribe a mano. Cada migración lleva un comentario que dice que se leyó antes de aplicarla.
- **A-4** NUNCA enviar el token en el cuerpo ni leerlo de la cabecera `Authorization` → viaja sólo en la cookie `access_token` (`HttpOnly`, `SameSite=Lax`, `Max-Age`, `Secure` configurable) y la dependencia lo lee de `request.cookies`. Cualquier consejo de `Bearer` de una skill no aplica acá (C-03 exige 401 con `Bearer`).
- **A-5** NUNCA editar el catálogo `estado_orden` desde la API ni en migraciones → la migración lo crea vacío y `seed.py` carga sus 4 filas.

### B · Capas y asincronía

- **B-1** NUNCA llamar `commit()` desde un repositorio → `add`/`update` hacen `flush()`; confirma sólo el Unit of Work al salir del bloque.
- **B-2** NUNCA construir el Unit of Work en un servicio → el router lo construye con una dependencia y lo pasa sin abrir; el servicio lo abre con `async with`.
- **B-3** NUNCA cerrar la sesión desde el Unit of Work → la sesión la crea y la cierra `get_session`.
- **B-4** NUNCA depender de la carga perezosa → toda relación que se lee se precarga (`selectinload`/`joinedload`) dentro del método del repositorio que la necesita.
- **B-5** NUNCA escribir un handler `def` ni hacer llamadas bloqueantes → todos los handlers `async def`; bcrypt siempre con `asyncio.to_thread` bajo un semáforo, y el hash se calcula **antes** de abrir la transacción.
- **B-6** NUNCA crear el motor o la fábrica de sesiones al importar un módulo → se crean en el `lifespan` y viven en `app.state`.
- **B-7** NUNCA modificar el stock de un repuesto fuera del punto único de escritura → alta con stock inicial, reposición y terminación de órdenes pasan por la misma función (movimiento + stock).
- **B-8** NUNCA hacer `commit()` fuera de un Unit of Work, en ningún flujo → todo commit lo hace un UoW al salir de su bloque (pedido del docente, DD-19). `intento_acceso`, que debe confirmarse en sesión y transacción propias, usa un **UoW dedicado** con su propia sesión.

### S · Datos y seguridad

- **S-1** NUNCA usar `float` para dinero → `NUMERIC` en la base y `Decimal` en Python; fechas siempre `timestamptz`.
- **S-2** NUNCA verificar unicidad con una consulta previa → la garantiza la base (UNIQUE / índice único parcial) y el `IntegrityError` se traduce a 409 con mensaje propio.
- **S-3** NUNCA armar SQL concatenando datos del usuario → siempre parámetros ligados.
- **S-4** NUNCA declarar un contrato de entrada sin `extra="forbid"` ni devolver `password_hash` → contratos (`schemas.py`) separados de los modelos de tabla; PATCH con `exclude_unset`.
- **S-5** NUNCA devolver texto interno de la base ni una traza, ni dejar que una entrada inválida termine en 500 → mensajes propios; validación en el contrato (incluido el límite de 72 bytes de todo campo que va a bcrypt).
- **S-6** NUNCA poner contraseñas, clave de firma ni credenciales en el código (tampoco como default), en `alembic.ini` ni en el repo → `Settings` sin defaults para secretos; `.env` en `.gitignore`; `env.example` sin secretos. Las contraseñas de mentira del seed viven sólo en `seed.py`.
- **S-7** NUNCA generar la clave de firma del JWT al arrancar (`secrets.token_*` en runtime, valor aleatorio por defecto) → `JWT_SECRET` es **fijo** y se lee de `.env`; si cambiara en cada reinicio, todos los usuarios tendrían que volver a loguearse (pedido del docente + consigna 5.12, DD-20).
- **S-8** NUNCA emitir la cookie de sesión antes de que el UoW confirme → login y registro (que también deja la sesión iniciada, DD-17) ponen `Set-Cookie access_token` sólo tras un commit exitoso.
- **S-9** NUNCA mostrar al usuario un mensaje técnico (texto de la base, nombres de tablas/columnas/restricciones, trazas, códigos internos) → todo mensaje de error va en **español claro y humano**, p. ej. «Ya existe un cliente con ese documento.» (DD-25). Login: «El correo o la contraseña no son correctos.»; cuenta inactiva con contraseña correcta: «Tu cuenta está desactivada. Comunicate con el taller para reactivarla.» (DD-24).

### D · Trabajo en equipo

- **D-1** NUNCA usar `C-xx` para referirse a un change → los changes son `[EJ-N]`; `C-01..C-19` son exclusivamente los casos de prueba de la consigna.
- **D-2** NUNCA empezar un change sin que el anterior esté archivado, commiteado y empujado → `git pull` antes de empezar; al cerrar: Definition of Done del change, `/opsx:archive`, commit, push y checkbox `[x]` en `CHANGES.md` en el mismo commit.
- **D-3** NUNCA escribir un `.http` sin la respuesta esperada en un comentario → un bloque por caso `C-xx`, sesiones múltiples con `# @name` + `# @no-cookie-jar` + `Cookie: {{loginX.response.headers.Set-Cookie}}` (ver `knowledge-base/11_casos_de_prueba_y_entrega.md`); correr `python seed.py` antes de cada archivo.
- **D-4** NUNCA dejar un supuesto nuevo sólo en el código → anotarlo en `knowledge-base/09_decisiones_y_supuestos.md` (y la duda en `10_preguntas_abiertas.md`) para el siguiente compañero.

### E · Convenciones de código y tests

- **E-1** Idioma: los identificadores que la consigna no fija (servicios, métodos, variables) van en **español**, coherentes con el dominio (`get_usuario_actual`, `requiere_rol`, `terminar_orden`). Se respetan tal cual los nombres técnicos que la consigna da en inglés (`get_by_id`, `get_all`, `soft_delete`, `get_by_id_including_deleted`, `flush`).
- **E-2** Tests: los `.http` de `test/` son la **entrega** (C-01..C-19). Además, el ciclo RED/GREEN usa **pytest + httpx** contra una **PostgreSQL real de test** (sin mocks de la base) en `test/pytest/`. EJ-1 deja configurado el runner; cada change agrega los tests de su ejercicio.
- **E-3** Python 3.12 con type hints en firmas públicas; `snake_case` para funciones/variables y `PascalCase` para clases.

---

## Flujo de Trabajo

```
1. git pull (importa engram) + leer la KB (knowledge-base/) → entender el dominio
2. Identificar el siguiente [EJ-N] pendiente en CHANGES.md → respetar el orden estricto
3. /opsx:propose 0N-nombre                               → proposal + design + specs + tasks
4. /opsx:apply (cargando skills, TDD con pytest)          → respetando las reglas duras
5. Definition of Done: .http del ejercicio + alembic up/down/up + seed
6. /opsx:archive 0N-nombre + marcar [x] + commit
7. bash scripts/sync-memoria.sh (Windows: scripts\sync-memoria.bat) + git push → relevo
```

Aplicar TODAS las reglas duras en cada paso. Ante conflicto entre la KB y este archivo, las reglas duras prevalecen.
