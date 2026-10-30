# Design

## Context

Ver `proposal.md` para motivación y alcance; los comportamientos los fijan los deltas de `specs/asincronia-segundo-plano`, `specs/ordenes-trabajo` y `specs/persistencia-transaccional`. El diseño hace falta porque EJ-8 es una **auditoría con dos piezas nuevas**: el aviso con `BackgroundTasks` todavía no existe en el código, y el resto (carga anticipada y handlers asíncronos) ya está implementado y hay que demostrarlo sin romperlo.

| Evidencia actual (observada en el código) | Consecuencia de diseño |
|---|---|
| No hay ninguna mención a `BackgroundTasks`, `add_task` ni un aviso en `app/`, `main.py` ni `test/` (búsqueda en todo el repo) | D1/D2: la pieza nueva es el aviso; todo lo demás es auditoría |
| `ordenes/router.py::terminar_orden` (línea 129) sólo pasa `uow` e `identidad` al servicio; el servicio abre el UoW y devuelve o lanza | D1: el `BackgroundTasks` entra en el **router**, después del `await` del servicio (T-9) |
| `ordenes/service.py::terminar_orden` (298) sale del bloque con `return await _registrar_transicion(...)`; los 404/403/409 salen por excepción antes | D1: agendar **después** del `await` da gratis «sólo si se confirmó»: una excepción nunca llega al `add_task` |
| `health/router.py` ya usa `logging.getLogger("app.salud")` y un mensaje en español sin datos internos | D2: mismo patrón, `logging.getLogger("app.ordenes.avisos")` |
| `OrdenRepository.get_detalle_con_items_e_historial` (59) trae vehículo→cliente (`joinedload`), ítems→repuesto (`selectinload`+`joinedload`) e historial (`selectinload`) con `populate_existing=True` | D3/D4: una sola consulta raíz + tres de precarga; ninguna crece con los ítems → la base del conteo fijo ya existe |
| `service.crear_orden` (198) y `_registrar_transicion` (250) releen el detalle con ese método antes de serializar; `armar_detalle` (120) lee `orden.vehiculo.cliente.nombre` y `item.repuesto.*` | D4: toda serialización del detalle pasa por la precarga; si aparece un camino que no lo hace, falla en asincrónico (carga perezosa prohibida) |
| `OrdenResumenLectura` tiene sólo columnas propias (`id`, `vehiculo_id`, `estado`, `falla`, `creada_en`, `mecanico_id`, `total`): el listado no lee ninguna relación | D4: los listados no pueden tener N+1; se fija por prueba, no se cambia código |
| Precargas existentes en `usuarios/repository.py` (roles), `clientes/repository.py` (vehículos + criterio de vigencia) y `repuestos/repository.py` (movimientos y precios) | D4: auditoría por inspección + prueba; sin cambio previsto |
| Los `def` de `app/modules/*/router.py` son sólo fábricas de dependencias (`construir_uow`, `poner_cookie_sesion`), nunca handlers; bcrypt ya corre en `asyncio.to_thread` bajo semáforo (`core/security.py:35`) | D5: la asincronía exigida ya está; se fija con un detector |
| El seed sólo tiene órdenes de **2** ítems (orden 1) y de **1** ítem con cantidad 4 (orden 2): no existe ninguna de 4 ítems | D3: la orden de 4 ítems se crea por la API en el `.http` y con `Datos.orden(items=(...))` en pytest |
| `SQL_ECHO` ya existe en `Settings` y en `env.example` (default `false`); no hay evidencia C-15 en `docs/evidencias/` (sólo está `C-14-solo-agregado.txt`) | D6: la evidencia se produce con la variable en `true`, mismo molde que EJ-7 |
| `test/pytest/ordenes/conftest.py` ya expone `fabrica`, `Datos` y `api_sembrada` (API real sobre `seed.py`) con `entrar(email)` | D3/D7: fixtures nuevas encima de estas, sin duplicarlas |

## Goals / Non-Goals

**Goals:** que el criterio «Lecturas sin N+1 y asincronía» (8 %) encuentre el aviso en el registro después de la respuesta y ausente en los 409, el detalle con la misma cantidad de consultas con 2 y con 4 ítems (C-15, con evidencia guardada), y todos los handlers `async def` sin llamadas bloqueantes; que la auditoría de carga anticipada quede **declarada por prueba** y que cualquier hallazgo quede corregido o registrado (D-4), sin ampliar el alcance en silencio.

**Non-Goals:** migraciones, cambios de esquema o de `seed.py`; endpoints nuevos; reintento, cola ni persistencia del aviso si el proceso se reinicia (DD-07 lo deja para el cap. 8); control de concurrencia del stock (DD-08); medir tiempos de respuesta o hacer benchmark; tocar el contrato de respuesta de `POST /ordenes/{id}/terminar`.

## Decisions

### D1 — El aviso se agenda en el router, después del `await` del servicio

`terminar_orden` en `app/modules/ordenes/router.py` recibe `background_tasks: BackgroundTasks` y ejecuta:

```python
orden = await service.terminar_orden(uow, identidad, orden_id)
background_tasks.add_task(avisar_cliente, ...)
return orden
```

- **«Sólo si se confirmó» cae de la estructura**: 404 (orden inexistente), 403 (sin permiso) y 409 (otro estado o stock insuficiente) salen del servicio como excepción, que FastAPI traduce antes de la línea del `add_task`. No hay que preguntar por el resultado ni capturar nada.
- **«Después de enviar la respuesta» es de Starlette**: `BackgroundTasks` corre cuando termina de enviarse el cuerpo. Si la tarea se agendara dentro del servicio, estaría igual de tarde, pero el servicio empezaría a conocer HTTP (T-9/RT-TX-02: el servicio sólo conoce el UoW).
- **Alternativa descartada**: que el servicio reciba `BackgroundTasks` y agende dentro/justo después del bloque. Acopla el dominio a FastAPI, obliga a pasarle el objeto por todas las capas y complica el «después del commit» (la excepción de stock insuficiente saldría por el mismo camino que un 409 real).
- **Alternativa descartada**: un manejador de eventos o middleware que observe la respuesta. No puede distinguir un 200 de un 409 sin mirar el cuerpo o el estado, que es exactamente lo que RT-TX-07 prohíbe confundir.

### D2 — La unidad del aviso: dato plano, medio segundo, registro en español

Nuevo `app/modules/ordenes/avisos.py`:

```python
logger = logging.getLogger("app.ordenes.avisos")   # misma convención que "app.salud"

async def avisar_cliente(orden_id: int, cliente: str) -> None:
    """Aviso en segundo plano (RT-TX-07, DD-07): corre DESPUÉS de la respuesta. ..."""
    await asyncio.sleep(0.5)
    logger.info("Aviso al cliente %s: la orden #%s terminó y ya puede retirar el vehículo.", cliente, orden_id)
```

- **Recibe datos planos** (`int`, `str`) tomados de la respuesta que ya está por salir: la tarea **no abre sesión ni consulta la base** (la sesión de la petición ya hizo su trabajo y puede estar cerrada; el spec prohíbe que el aviso agregue escrituras).
- `asyncio.sleep(0.5)` cumple el «medio segundo» de la consigna sin bloquear el bucle (RT-TX-07, US-024); el mensaje va en español claro y sin datos internos (RT-EQ-01, S-9).
- **Alternativa descartada**: `time.sleep(0.5)` — bloquearía el bucle de eventos, que es justo lo que este ejercicio audita.
- **Hallazgo de la implementación (corrección registrada antes de escribirse, Impact del proposal)**: con el mensaje en `logger.info`, la consola de la API **no** lo mostraba: uvicorn sólo configura sus propios loggers (`uvicorn`, `uvicorn.error`, `uvicorn.access`) y la aplicación nunca configura `logging`, así que `app.*` hereda el nivel WARNING de root y un `info` se descarta antes de llegar a ningún handler (el 503 de `app.salud` se ve porque es `warning`). Como C-12 exige que «el aviso **salga** en el registro» y `.http` debe documentar la salida real (D-3), `main.py` suma `configurar_registro_app()`, llamada desde el `lifespan`: un handler propio de `app.*` a stderr con nivel `INFO` y formato `%(levelname)s %(name)s: %(message)s`, **sólo si `app` todavía no tiene handlers** (idempotente para los tests que arrancan la app varias veces). Descartado: bajar el aviso a `warning` (es informativo, ensuciaría la consola de futuros warnings reales) y `logging.basicConfig` a nivel INFO (subiría también urllib3/sqlalchemy y el resto de la app).

### D3 — Cómo se mide «el mismo número de consultas» (C-15)

Dos medidas complementarias, ninguna depende de leer `SQL_ECHO` a mano:

1. **Prueba automática (la que falla)**: contador con el evento `before_cursor_execute` del motor (`motor.sync_engine` para el motor asíncrono) alrededor de `OrdenRepository.get_detalle_con_items_e_historial` sobre dos órdenes reales de la misma base —una de 2 ítems y otra de 4— y aserción de **igualdad** de conteos (y de que el conteo no depende de las líneas de historial). Se corre con la sesión propia de la prueba: ningún ruido de autenticación entra en el conteo.
   - **Alternativa descartada**: capturar la consola con `SQL_ECHO` y contar líneas. Es frágil (el login, el healthcheck y el pool también imprimen) y sólo sirve para la evidencia humana, no para fallar.
2. **Evidencia C-15 (la que se entrega)**: mismo molde que C-14 (design de EJ-7, D4): `SQL_ECHO=true`, se levanta la API, se piden por HTTP el detalle de la orden 1 del seed (2 ítems) y el de una orden creada con 4 ítems, y el fragmento de consola se guarda en `docs/evidencias/C-15-consultas-fijas.txt`. El README explica cómo producirlo y qué se mira: las mismas sentencias, con el mismo número de filas de resultado por consulta.
   - La **captura de pantalla** que pide la entrega la toma una persona con ese mismo comando; el archivo guardado es la evidencia reproducible.

### D4 — Auditoría de carga anticipada: qué se mira y qué se corrige

El alcance de la auditoría (RT-TX-05, T-10) es cerrado y se recorre en este orden:

1. Cada `service.py` que serializa relaciones → verificar que el objeto vino de un método de repositorio que las precarga (`armar_detalle` sólo recibe órdenes de `get_detalle_con_items_e_historial`; `GET /clientes/{id}` usa `get_by_id_con_vehiculos`; `/repuestos/{id}/movimientos` y `/precios` usan los `selectinload` del repositorio; `GET /usuarios/{id}/roles` usa `get_por_id_con_roles`/`get_vigentes_de`).
2. Listados: confirmar que sus contratos leen sólo columnas propias (`OrdenResumenLectura`, `Pagina[...]`), de modo que no hay relación que precargar.
3. Prueba de inspección en `test/pytest/asincronia/`: ningún `service.py` ni `router.py` llama `execute(` sobre la sesión (ya hay algo parecido en `test_capas.py`; se reutiliza el detector si existe) y los métodos de repositorio que devuelven entidades con relaciones declaran `options(...)`.
4. **Se corrige sólo si la auditoría encuentra un hueco**, y la corrección se registra en el ODD y en el design antes de escribirse (igual que EJ-7).

Si todo está conforme, la auditoría queda **verde de entrada** (caracterización), con prueba de sensibilidad declarada (D7).

### D5 — Handlers asíncronos: detector, no revisión manual

Inspección por AST sobre `app/modules/*/router.py`: las funciones decoradas con `@router.get|post|patch|put|delete` están declaradas `async def`; y en `app/` no aparecen `time.sleep`, módulos síncronos de HTTP ni lectura de archivos dentro del bucle. El detector se prueba sobre un archivo temporal con un `def` de handler (mismo patrón que el detector de `commit()` de `test_capas.py`), para que la prueba no sea una afirmación vacía.
bcrypt ya cumple (RT-SE-02/03, `core/security.py` con `to_thread` + semáforo): sólo se reafirma, no se reimplementa.

### D6 — Evidencia, `.http` y cierre de la entrega

- `test/ordenes.http` suma dos bloques con su respuesta esperada en comentario (D-3 de `AGENTS.md`): **C-12 con aviso** (reponer → terminar → 200 y, en el comentario, que el aviso aparece en la consola **después** de la respuesta; y el caso 409 del C-11 **sin** aviso) y **C-15** (detalle de la orden 1 de 2 ítems y de una orden nueva de 4 ítems, apuntando a la evidencia). El archivo se corre tras `python seed.py`.
- `README.md`: pasos desde cero (ya existentes), más «Cómo producir la evidencia C-15» y la checklist de `knowledge-base/11_casos_de_prueba_y_entrega.md` completa (C-01..C-19, `solo_agregado.sql`, capturas C-14 y C-15).
- Sin cambios en `seed.py`, `env.example` (ya tiene `SQL_ECHO`) ni en `alembic.ini`.

### D7 — Strict TDD en un change con dos auditorías y una pieza nueva

| Prueba | Estado esperado del primer run | Cómo se prueba que puede fallar |
|---|---|---|
| Aviso en el registro tras el 200 (C-12) | **RED** (no existe `add_task` ni mensaje) | — |
| Aviso ausente en el 409 (C-11) | **RED** por la misma causa | — |
| El aviso sale **después** de la respuesta (comparación de instantes) | **RED** | Sólo puede fallar hacia el lado «muy tarde»: se afirma `instante_del_registro > instante_de_recepción`; si se agendara antes (imposible con D1) fallaría |
| Consultas fijas 2 vs 4 ítems | Caracterización (verde) | Sensibilidad: réplica del método con una consulta extra **por ítem** dentro del bucle (monkeypatch) hace fallar la igualdad de conteos |
| Handlers `async def` + sin bloqueos | Caracterización (verde) | Detector sobre archivo temporal con un `def` de handler → falla |
| Servicios sin SQL directo | Caracterización (verde) | Detector sobre archivo temporal con `sesion.execute` en un `service.py` → falla |

Las pruebas verdes de entrada se declaran como caracterización con su prueba de sensibilidad, igual que EJ-7 (D9); el RED real lo pone el aviso, que es la única pieza inexistente.

## Risks / Trade-offs

- [La tarea corre después de que FastAPI cerró la sesión de la petición] → el aviso recibe datos planos y **no toca la base** (D2); el spec lo prohíbe explícitamente.
- [El aviso se pierde si el proceso se reinicia en ese medio segundo y no hay reintento] → aceptado por DD-07; fuera de alcance (cap. 8).
- [El conteo de consultas de un HTTP completo incluye login, roles y healthcheck] → la prueba de igualdad se hace sobre el método de repositorio con sesión propia (invariante) y la evidencia humana compara los dos fragmentos de consola, donde esas consultas son constantes (D3).
- [No existe ninguna orden de 4 ítems en el seed] → se crea por la API en el `.http` y con `Datos.orden` en pytest; el `seed.py` no se toca (su estado inicial es contrato de EJ-2).
- [`SQL_ECHO=true` en el `.env` de alguien ensucia la consola y puede filtrar sentencias] → default `false`, sólo se enciende para producir la evidencia; el README lo dice.
- [Renombrar el requisito «Terminación atómica que descuenta stock» en `specs/ordenes-trabajo`] → OpenSpec no permite renombrar escenarios dentro de un `MODIFIED`; se hizo `REMOVED` + `ADDED` con Reason/Migration para que el escenario de C-12 deje de decir «sin aviso». Riesgo de lectura cruzada: mitigado citando el requisito por su nombre nuevo en el README/KB donde haga falta.
- [Las pruebas de caracterización pasan sin haber visto RED] → excepción declarada con prueba de sensibilidad (D7); la verificación independiente la revisa.

## Migration Plan

Sin migraciones y sin cambios de datos. DoD: `alembic upgrade head → downgrade base → upgrade head` sobre base vacía, `python seed.py`, suite completa en verde (más las 2 fallas ambientales conocidas de Windows/loopback), `.http` del ejercicio tras `python seed.py`, evidencia `docs/evidencias/C-15-consultas-fijas.txt` guardada y checklist de entrega completa. Rollback: revertir los commits del change (código del aviso, pruebas, evidencia y docs).

## Supuestos y decisiones para la KB (D-4, se escriben en el apply)

- **DD nueva** — Aviso en segundo plano (EJ-8): unidad `avisos.py` con datos planos y sin acceso a la base; se agenda en el router sólo cuando el servicio devolvió; mensaje y logger concretos; sin reintento (DD-07).
- **DD nueva** — Medición de consultas fijas (EJ-8): contador por evento `before_cursor_execute` sobre el método de repositorio, más evidencia de consola con `SQL_ECHO=true` (D3).
- **SU nuevo** — La orden de 4 ítems de C-15 no existe en el seed y se crea por la API en el `.http`/prueba; `seed.py` conserva su estado inicial.
- **Actualización de DD-07** — Se confirma el texto de la tarea (`sleep(0.5)` + registro) y que se agenda desde el router (T-9).

## Open Questions

- Ninguna bloqueante. El texto exacto del aviso («…la orden #N terminó y ya puede retirar el vehículo») es una decisión menor registrada en la DD nueva; si el equipo lo quiere distinto, cambia un string sin tocar specs ni tareas.
