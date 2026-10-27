# Implementación EJ-4 — Autenticación

Aplicar el change aprobado `openspec/changes/04-autenticacion/` con sus 22 tareas como fuente de verdad funcional; este archivo sólo registra ejecución, evidencias y commits.
Base: `c98b3c026a9f1c7fc698d39d0650be28fc080d26`; rama `feat/04-autenticacion`. Sin EJ-5, archive, merge ni push en este apply.

## Specs

- S1: «Por continua con: /opsx:apply 04-autenticacion». Alcance por referencia: `openspec/changes/04-autenticacion/{proposal.md,design.md,tasks.md}` y `specs/autenticacion-sesiones/spec.md`; conservar literalmente contratos, mensajes y escenarios de esos artefactos. La consigna y AGENTS.md siguen teniendo precedencia.

## Tasks

- T0 [done] — S1 — parent: rama, tracking, runner y PostgreSQL aislada disponibles; commit: `7012216`.
- T1 [in_progress] — S1 — OPSX 1.1–1.3 implementadas/verificadas; pendiente revisión nativa de unidad; commit: `feat(auth): add validated contracts and isolated fixtures` (SHA se registra tras commit).
- T2 [pending] — S1 — worker acotado por context backstop: OPSX 2.1–2.3, bcrypt/JWT y regresiones; commit: pendiente.
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
