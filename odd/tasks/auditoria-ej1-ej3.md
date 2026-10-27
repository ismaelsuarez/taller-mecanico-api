# Correcciones de auditoría EJ-1..3

Alcance autorizado: corregir los cuatro hallazgos de la auditoría antes de EJ-4 y verificar en PostgreSQL aislada. No iniciar EJ-4, cambiar paginación ni publicar.
Base: `18d039a`; rama: `fix/auditoria-ej1-ej3`. Las citas siguientes proceden del informe entregado y de la autorización del usuario.

## Specs

- S1: «Alta — contratos numéricos incompatibles con la persistencia.» «El padre confirmó que `model_validate` acepta precios `"0.001"`/`"100000000"` y cantidades `2147483648`. PATCH y reposición no traducen los errores resultantes (`app/modules/repuestos/service.py:84-85,108`).» «Viola RN-18/EJ-3.»
- S2: «Media — los tests no usan el esquema real de migraciones.» «`test/pytest/conftest.py:123-124`, `test/pytest/test_modelos.py:307` y `test/pytest/test_repositorios_uow.py:57` utilizan `create_all`.» «Violación confirmada de A-3: esas fixtures no aplican la segunda migración y carecen de sus tres triggers.»
- S3: «Media — errores de validación técnicos y en inglés.» «`app/core/errores.py:38-39` sólo registra traductores de errores de dominio. Los `.http` esperan expresamente `Input should…` y `Field required` (`test/clientes_vehiculos.http:12,56-57`).» «Viola S-9/DD-25 y la spec archivada de contratos estrictos.»
- S4: «Media — seed confirma fuera de un UoW.» «`seed.py:301-305` utiliza `conexion.begin()`, que confirma al salir sin pasar por Unit of Work.» «Viola B-8/DD-19. La recarga sí está agrupada atómicamente: el defecto es arquitectónico, no una pérdida demostrada de atomicidad.»
- S5: «Recomiendo corregir estos cuatro puntos antes de EJ-4 y después verificar contra PostgreSQL de test con las migraciones reales.» Autorización: «Si te autorizo».

## Tasks

- T0 [done] — S5 — parent: PostgreSQL y bases aisladas disponibles; commit: cierre documental `docs: record verified audit remediation`.
- T1 [done] — S2,S4 — worker persistencia: fixtures Alembic + seed por UoW, RED/GREEN; commits: `0f05531` (S2/logging), `4c7dc63` (S4).
- T2 [done] — S1 — worker números: límites representables, reposición sin overflow y regresiones HTTP; commit: `566bd0c`.
- T3 [done] — S3 — worker mensajes: 422 humanos, seguros y en español, tests y ejemplos .http; commit: `21b20ec`.
- T4 [done] — S1-S5 — parent: documentación/specs, suite integrada, diagnóstico y verificador independiente; evidencia funcional: `4c7dc63`, documentación de cierre: `docs: record verified audit remediation`.
- T5 [done] — S5 — parent: assessment por unidad y cierre; commits de comportamiento `566bd0c`, `21b20ec`, `0f05531`, `4c7dc63`; cierre documental: `docs: record verified audit remediation` (este commit; SHA en Engram).

## Log

- L1: «Si te autorizo».
- L2: Autorización responde a «¿Autorizás esas correcciones y levantar el servicio de base para verificarlas, sin iniciar todavía EJ-4?».
- L3: `git pull` ya actualizado en auditoría previa; árbol limpio en 18d039a. Rama de correcciones creada. RDD on (global).
- L4: `docker compose up -d --wait db` exitoso. Bases nuevas de pruebas: `taller_audit_01a17ac1_persist`, `taller_audit_01a17ac1_numeros`, `taller_audit_01a17ac1_errores`, `taller_audit_01a17ac1_final`. No se borra el volumen ni se prueba sobre la base de desarrollo.
- L5: Riesgo previsto: item 3 (traductor compartido de validación afecta endpoints existentes); verificación independiente requerida. Las bases de prueba son reconstruibles; no se modifica el esquema productivo ni se cambia el formato persistido.
- L6: T2/S1: RED reproducido contra PostgreSQL (4 precios, 2 cantidades, 3 acumulaciones); GREEN 99 passed, 0 skipped en test_repuestos_limites.py + test_repuestos.py. Padre revisó contratos, servicio, tests y .http. Assessment del diff vivo no disponible por archivos nuevos sin declarar; se evalúa la unidad comprometida por separado.
- L7: T2 comprometido en 566bd0c (371 líneas autorales, tests/docs incluidos). Assessment committedOnly también no evaluable: el proveedor exige declaración de archivos nuevos ajenos a la unidad. Sin reviewDue disponible, no se inicia revisión de T2 ni se atribuye aprobación; autoverificación del escritor válida según plan devuelto.
- L8: T3: 47 casos nuevos y 115 pruebas focalizadas aprobadas, 0 skips. Falta alinear OpenAPI con `detail: [{msg}]` y el error textual de paginación; continuación mvq05zyo-5-3d01 en curso. Assessment requiere verificador independiente por item 3; nativeRisk no evaluable por archivos nuevos.
- L9: T1/S2,S4: 115 passed en orden normal e inverso, 0 skips; RED por triggers ausentes y contrato UoW. Padre revisó fixture, guardia y seed. Risk item 2: guardia de destino de limpieza; requiere verificador independiente.
- L10: T3/S3 completo, incluido OpenAPI: RED 1 failed, GREEN 48 passed. Modelos 422 sólo en clientes/repuestos, sin 422 en salud. Resta integración y comparación diferencial.
- L11: Comparación diferencial finalizada (job-5, exit 0): 21 escenarios HTTP base 18d039a vs candidato, salida/código/stderr idénticos; sólo `cuando` normalizado. Bases aisladas numeros/errores, scratch local eliminado.
- L12: LSP activo sobre 12 Python: 8 limpios, 4 con hallazgos; 34 diagnósticos (32 Pyright, 2 Semgrep) en líneas verificadas idénticas a la base. No se afirma tipado limpio. Suite integrada job-4 y verificador mvq0dauf-6-1ge7 pendientes.
- L13: Suite integrada job-4: exit 1, 347 passed, 1 failed, 0 skipped. test_el_503_registra_la_causa_en_el_log_sin_secretos no capturó el aviso esperado. T1 se reabre por interferencia de logging al integrar Alembic; diagnóstico/corrección acotados antes de repetir suite sobre candidato cambiado.
- L14: T3 comprometido en 21b20ec (380 líneas autorales). Assessment committedOnly sobre 566bd0c: nativeRisk medium, reviewDue=false (under_budget); escalación item 3 mantiene verificador independiente. No se inicia revisión nativa ni se afirma aprobación.
- L15: Verificador independiente ejecutó 16 tests (exit 0, sin skips), 31 peticiones leídas de los dos .http con seed antes de cada archivo y 34 comprobaciones complementarias (exit 0). Sin nuevos defectos en alcance; cierre global pendiente del fallo de logging.
- L16: Estrategia de entrega: sólo commits locales revisables, sin push/PR. Límites de unidades: 18d039a→566bd0c (numéricos, 371 líneas), 566bd0c→21b20ec (422, 380 líneas); fixtures/logging y seed se conservarán en commits separados de aproximadamente 400 líneas. Documentación/seguimiento final en último commit. Una eventual publicación/PR requiere decisión del usuario; no se revisa la rama acumulada como candidato.
- L17: Logging corregido en migrations/env.py: preservar handlers existentes; CLI sin handlers usa fileConfig(disable_existing_loggers=False). RED secuencia original también falla (2 passed/1 failed), por lo que no se atribuye exclusivamente al cambio. GREEN focalizado 36 passed/0 skipped. Suite corregida job-6 y delta independiente en ejecución.
- L18: Cierre funcional: job-6 exit 0, 350 passed en 107.44s, 0 skipped. Incluye ciclo migraciones up/down/up, triggers, seed, CRUD y salud. Delta logging independiente: 2 passed en 1.61s, exit 0; S1-S4 PASS y S5 satisfecho por suite integrada observada.
- L19: Unidades locales adicionales: 21b20ec→0f05531 (fixtures/logging, 331 líneas), 0f05531→4c7dc63 (seed/UoW, 203 líneas). Assess de cada una: nativeRisk medium, reviewDue=false, under_budget. No se ejecutó revisión nativa; sí verificación independiente de riesgos 2/3. Última unidad sólo documentación/seguimiento, sin nuevas funcionalidades.
- L20: LSP de migrations/env.py y test_fixtures_migradas.py tras corregir logging: 2 archivos limpios. Persisten los 34 diagnósticos anteriores sobre líneas preexistentes; no se corrigen ni se afirma análisis estático integral limpio.
- L21: Cierre: cuatro hallazgos corregidos y verificados; EJ-4 no iniciado. Cinco unidades locales contando este cierre documental. PostgreSQL queda levantado y las bases de auditoría disponibles. Sin push, merge ni PR. Siguiente paso humano: revisar y decidir publicación/integración antes del relevo.
