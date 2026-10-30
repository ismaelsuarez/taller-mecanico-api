# Proposal

## Why

EJ-1..7 están archivados y publicados (1053 tests). El Ejercicio 8 (8 pts, governance **MEDIO**: rendimiento y tareas en segundo plano) cierra la entrega con dos garantías que la consigna evalúa pero que todavía nadie demostró ni implementó: el detalle de una orden debe resolverse con un **número fijo de consultas** que no crezca con la cantidad de ítems (RT-TX-06 / C-15, hoy sin evidencia ni prueba) y el aviso al cliente al terminar una orden, que EJ-6 entregó **sin aviso** a propósito (T-9), todavía no existe: no hay `BackgroundTasks` en ningún punto del código. Sin este change falta la evidencia C-15 exigida en el formato de entrega y el caso C-12 queda incompleto.

## What Changes

- **Aviso en segundo plano (US-024, RT-TX-07, DD-07, T-9)**: nueva unidad `app/modules/ordenes/avisos.py` con `async def avisar_cliente(...)`: `await asyncio.sleep(0.5)` y un mensaje en el registro (`logging.getLogger("app.ordenes.avisos")`, misma convención que `app.salud`). El **router** de `POST /ordenes/{id}/terminar` lo agenda con `BackgroundTasks` **después** de que el servicio devolvió con éxito: 404, 403 y 409 salen por excepción y nunca llegan a `add_task`, así que no se agenda nada si la operación no se confirmó y el aviso corre **después de enviar la respuesta**. El servicio no conoce `BackgroundTasks` (sigue siendo el dueño exclusivo del UoW, T-9/RT-TX-02).
- **Carga anticipada auditada (US-023, RT-TX-05)**: revisión de todos los repositorios para confirmar que toda relación que una respuesta lee se precarga dentro del método que la necesita; se corrige sólo lo que la auditoría encuentre. Sin cambios de esquema, migraciones ni de `seed.py`.
- **Consultas fijas en el detalle (US-023, RT-TX-06, C-15)**: prueba pytest que mide las consultas de `GET /ordenes/{id}` (o del repositorio de detalle) con **2 y con 4 ítems** y exige el mismo número. Evidencia en `docs/evidencias/C-15-consultas-fijas.txt`: fragmento de consola con `SQL_ECHO=true` (la variable ya existe, DD-30) de una orden de 2 ítems (la orden 1 del seed) y de otra de 4 ítems creada por la API en el mismo bloque, más el README que explica cómo producirla.
- **Asincronía auditada (RT-TX-07, criterio «ninguna llamada bloqueante»)**: inspección de que todos los handlers de `app/modules/*/router.py` son `async def` y de que no hay llamadas bloqueantes (bcrypt ya sale del bucle desde EJ-4); prueba de inspección que lo fije.
- **Caso C-12 completo**: `test/ordenes.http` suma el aviso de la terminación (200 + registro posterior) y el bloque de C-15; se leen las respuestas esperadas en comentarios (D-3) y se corren tras `python seed.py`.
- **Cierre de la entrega**: `README.md` final con los pasos desde cero, checklist completa de `knowledge-base/11_casos_de_prueba_y_entrega.md` (C-01..C-19, `test/solo_agregado.sql`, capturas C-14 y C-15) y anotación de las decisiones nuevas en la KB (D-4).

**Fuera de alcance:** migraciones, cambios de esquema y de `seed.py`; endpoints nuevos; reintento o cola de avisos si el proceso se reinicia (DD-07 lo deja para el cap. 8); control de concurrencia del stock (DD-08); reordenar carpetas o renombrar rutas/tablas (A-1, A-2).

## Capabilities

### New Capabilities

- `asincronia-segundo-plano`: handlers asíncronos sin llamadas bloqueantes y el aviso en segundo plano al terminar una orden (RT-TX-07, DD-07, US-024).

### Modified Capabilities

- `ordenes-trabajo`: el requisito «Terminación atómica que descuenta stock» —que EJ-6 escribió a propósito «sin aviso» (T-9)— se reescribe como «Terminación de una orden con stock, historial y aviso»: el escenario de C-12 pasa a cubrir el aviso agendado después de la respuesta y el 409 sigue sin agendar ninguno.
- `persistencia-transaccional`: se agrega el requisito de que el detalle de una orden se resuelva con un **número fijo de consultas** que no crece con la cantidad de ítems (RT-TX-06, C-15) y un escenario de auditoría de que ninguna respuesta dependa de la carga perezosa (RT-TX-05).

## Impact

- **Código**: nuevo `app/modules/ordenes/avisos.py`; `app/modules/ordenes/router.py` (`terminar_orden` recibe `BackgroundTasks` y agenda el aviso sólo tras el éxito). Sólo eso está previsto: cualquier corrección extra que encuentre la auditoría de precarga se registra antes de escribirse.
- **Persistencia**: sin migraciones ni cambios en `seed.py`; `SQL_ECHO` ya existe y sigue en `false` por defecto.
- **Pruebas/entregables**: ampliación de `test/ordenes.http` (C-12 con aviso, C-15); pytest nuevo en `test/pytest/asincronia/` (consultas fijas 2 vs 4 ítems, aviso sólo si se confirmó, handlers `async def`); evidencia en `docs/evidencias/C-15-consultas-fijas.txt` junto a la C-14 de EJ-7.
- **Documentación**: `README.md` (pasos desde cero, cómo producir la evidencia C-15, checklist de entrega completa), KB `09_decisiones_y_supuestos.md` (D-4) y `11_casos_de_prueba_y_entrega.md` (checklist marcada), `CHANGES.md` (checkbox `[x]` de EJ-8 en el commit de cierre).
- **Riesgo**: MEDIO (sin riesgo de datos; el punto delicado es no agendar el aviso en un 409 y no romper el conteo fijo de consultas al tocar el repositorio).
- **Aceptación**: C-15 (evidencia + misma cantidad de consultas con 2 y con 4 ítems), C-12 completo (aviso en el registro después de la respuesta, ausente en los 409), handlers `async def` sin llamadas bloqueantes, `alembic upgrade head → downgrade base → upgrade head` y `python seed.py` en verde, checklist de entrega completa.
- **Fuentes**: `docs/TP_Cap1a6_Consigna.pdf` (Ejercicio 8, C-12, C-15, evidencia de entrega, criterio «Lecturas sin N+1 y asincronía» 8 %), `CHANGES.md` (EJ-8, T-9, T-10), KB 05 (RT-TX-05..07), 06 (US-023, US-024), 07 (Flujo 8), 09 (DD-07, DD-30), 11 (C-12, C-15, checklist).
