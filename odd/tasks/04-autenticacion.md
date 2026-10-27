# Implementación EJ-4 — Autenticación

Aplicar el change aprobado `openspec/changes/04-autenticacion/` con sus 22 tareas como fuente de verdad funcional; este archivo sólo registra ejecución, evidencias y commits.
Base: `c98b3c026a9f1c7fc698d39d0650be28fc080d26`; rama `feat/04-autenticacion`. Sin EJ-5, archive, merge ni push en este apply.

## Specs

- S1: «Por continua con: /opsx:apply 04-autenticacion». Alcance por referencia: `openspec/changes/04-autenticacion/{proposal.md,design.md,tasks.md}` y `specs/autenticacion-sesiones/spec.md`; conservar literalmente contratos, mensajes y escenarios de esos artefactos. La consigna y AGENTS.md siguen teniendo precedencia.

## Tasks

- T0 [done] — S1 — parent: rama, tracking, runner y PostgreSQL aislada disponibles; commit: `7012216`.
- T1 [done] — S1 — OPSX 1.1–1.3 implementadas/verificadas, revisión nativa aprobada y consumida; commit: `e4eb8d8a9bf1b17c6738200f77db0849268343b0`.
- T2 [in_progress] — S1 — OPSX 2.1–2.3 implementadas/verificadas; pendiente revisión nativa; base: `e4eb8d8`; commit: `feat(auth): add async bcrypt verification and signed sessions` (SHA tras commit).
- T3 [pending] — S1 — worker acotado por context backstop: OPSX 3.1–3.3, registro atómico; commit: pendiente.
- T4 [pending] — S1 — worker acotado por context backstop: OPSX 4.1–4.3, login/límite/intentos; commit: pendiente.
- T5 [pending] — S1 — worker acotado por context backstop: OPSX 5.1–5.3, identidad/logout; commit: pendiente.
- T6 [pending] — S1 — worker acotado por context backstop: OPSX 6.1–6.3, cambio de contraseña; commit: pendiente.
- T7 [pending] — S1 — parent + verificador independiente: OPSX 7.1–7.4, suite/HTTP/diferencial/diagnósticos/revisión y cierre; commit: pendiente.

## Log

- L1: «Por continua con: /opsx:apply 04-autenticacion».
- L2: OpenSpec reconoce schema `spec-driven`, estado apply `ready`, 0/22 completadas. Los cuatro artefactos se releyeron al iniciar; cambios de alcance requieren decisión humana, no reducción silenciosa.
- L3: La propuesta se validó con `openspec validate 04-autenticacion --strict` antes de apply. Rama creada desde main; `.review-units/` preexistente se conserva y no se incorpora a commits.
- L4: Riesgos previstos: item 2 (autenticación), item 3 (helpers/errores compartidos), item 4 cuando se modifique comportamiento del semáforo. Verificación independiente además de pruebas funcionales; RDD on global, consentimiento nativo separado.
- L5: No se usa la delegación SDD retirada. Cada unidad delegada recibe este archivo y las referencias OPSX, permisos de edición acotados, RED/GREEN y sin autoridad para commit/push/revisión nativa. El padre registra cada checkbox con la ubicación actual devuelta por OPSX.
- L6: Docker db healthy; bases `taller_ej4_01a17ac1_impl` y `taller_ej4_01a17ac1_verify` creadas/disponibles sin eliminar volúmenes. Runner `.venv/bin/python` y dependencias importan correctamente. Tests con `POSTGRES_HOST=localhost` y `POSTGRES_TEST_DB` explícita.
- L7: Estrategia de entrega: unidades locales secuenciales revisables, tests/docs por comportamiento, aproximadamente 400 líneas por slice; no PR acumulada ni publicación automática. Primera frontera documental: `c98b3c0..7012216` (403 líneas). Cada unidad de alto riesgo tendrá su propio commit/base de revisión. El siguiente slice comienza en `7012216`; sin reducir pruebas o documentación para acomodar cifras.
- L8: T1 en ejecución con worker `mvqn0cy8-2-02a9`, alcance OPSX 1.1–1.3; sólo schemas de usuarios, tests auth aislados y decisiones KB. Sin checkboxes completados hasta recibir y verificar evidencia. El primer envío se rechazó antes de ejecutar por encabezado de superficies; se corrigió únicamente el separador Markdown exigido.

- L9: Worker T1 reporta RED/GREEN y 308 passed, 0 skipped (80.12 s); parent readback confirma alcance de siete archivos y DD-45. LSP activo: cuatro Python limpios. Assessment nativo no evaluable por untracked; escalación item 2 exige independiente. Verificador `mvqnlsdb-3-9ozi` en curso sobre base `_verify`; OPSX continúa 0/22 hasta admitir evidencia.

- L10: Verificador T1: 82 passed, 0 skipped (1.64 s) y 81 assertions públicas adicionales; sin hallazgos de seguridad. 1.2/1.3 conformes; 1.1 verificada en fixtures, regresión CRUD sólo evidencia del writer (308 passed), no atribuida al verificador. LSP 4/4 limpio. OPSX confirma 1/22 → 2/22 → 3/22 al marcar cada casilla.
- L11: Al declarar/stagear archivos intencionales, assessment normalizado: nativeRisk high por ruta auth, 374 líneas, reviewDue=true/high_risk. Corresponde revisión nativa de la unidad contra `7012216`, además de la verificación independiente observada. No se afirma aprobación nativa todavía.
- L12: T1 cerrada: commit `e4eb8d8` (377 líneas), revisión `review-ccfe6e9f73edc6bc`, tres lentes risk/readability/reliability aprobadas sin corrección. Acknowledgement nativo confirmó authority=burned, target `sha256:ec671644068d804c700fbb688aba3899559557cf4b5a66674213f82b75ef1e5f`, revisión consumida `sha256:6dcbf901bf6b46d9c53853299bfa3cbc8ef1252788a11dfbfd7a3187d38a35d5`. OPSX 3/22. Continúa T2; nada publicado.

- L13: T2 delegada a worker `mvqo6q4x-4-w0dc`: OPSX 2.1–2.3, superficies `app/core/security.py`, dos tests auth bcrypt/JWT y README. Base `e4eb8d8`; sin endpoints, commits ni revisión delegada. El padre conserva verificación independiente y comparación diferencial de seed/lifespan/health antes de cerrar la unidad. `openspec validate 04-autenticacion --strict` pasó después de T1.

- L14: T2 se detuvo sin cambios ni pruebas por `tmp_path` fuera de las superficies delegadas. El padre eligió A y verificó que `test/pytest/.tmp-t2-e4eb8d8` no existe ni es symlink; se autoriza únicamente ese directorio para temporales propios con `--basetemp`, sin ampliar producto ni tocar desarrollo. Continuación del mismo worker mediante `subagent_continue`, nuevo task ID `mvqoc13x-5-88pn`; mantiene las cuatro superficies originales y agrega sólo temporales, que deben limpiarse al terminar.

- L15: Worker T2 entregó cuatro archivos, 336 líneas modificadas; RED/GREEN reportado y regresión combinada 176 passed, 0 skipped (16.96 s). Parent readback completado; LSP activo tres Python limpios. Temporales vacíos del writer eliminados con rmdir, archivos de la unidad stageados intencionalmente. Sin checkbox T2 ni commit aún.
- L16: Verificador T2 `mvqoyn0w-6-qb2q` en curso: suite combinada independiente y un script diferencial contra `e4eb8d8` para seed/lifespan/salud, sólo DB `_verify`. Temporales y copia de base limitados a `test/pytest/.tmp-t2-verify-e4eb8d8/` (ausente/no symlink verificado); no cambios de fuente, `.review-units/` preservado. Riesgos 2/3/4; assessment inicial no evaluable por untracked, aún no hay revisión nativa T2.

- L17: Avance del verificador T2: suite independiente autorizada exit 0, 176 passed, 0 skipped (18.53 s); las cuatro superficies stageadas coinciden con working tree, sin mutaciones nuevas reportadas. Continúa el único diferencial `e4eb8d8` vs candidato, secuencial tras la suite, con scratch y DB `_verify` ya acotados. Evidencia parcial: no cerrar T2 ni iniciar otro verificador/diferencial mientras esté en curso.

- L18: Verificador T2 PASS 2.1/2.2/2.3: 176 passed/0 skipped; diferencial único exit0, 16 subprocesos, ocho igualdades BASE/candidato y dos idempotencias. Incluye seed sin migrar/primero/repetido/costes4y7, Alembic,13tablas/5secuencias/42hashes, lifespan y salud. Sólo normaliza sales bcrypt verificadas y marcas temporales seed; sin diferencias no pedidas. Evidencia completa resumida en Engram2339. OPSX admitió 4/22 → 5/22 → 6/22; T2 aún no tiene revisión nativa.
- L19: Limpieza del child bloqueada por su harness, no defecto funcional. Parent validó ruta, huellas,54archivos/12directorios/cero symlinks y caché pytest del script; eliminó sólo scratch generado, exit0. La primera guardia había detectado esa caché adicional y no borró nada. DB y `.review-units/` preservados.
