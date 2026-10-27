# Implementación EJ-4 — Autenticación

Aplicar el change aprobado `openspec/changes/04-autenticacion/` con sus 22 tareas como fuente de verdad funcional; este archivo sólo registra ejecución, evidencias y commits.
Base: `c98b3c026a9f1c7fc698d39d0650be28fc080d26`; rama `feat/04-autenticacion`. Sin EJ-5, archive, merge ni push en este apply.

## Specs

- S1: «Por continua con: /opsx:apply 04-autenticacion». Alcance por referencia: `openspec/changes/04-autenticacion/{proposal.md,design.md,tasks.md}` y `specs/autenticacion-sesiones/spec.md`; conservar literalmente contratos, mensajes y escenarios de esos artefactos. La consigna y AGENTS.md siguen teniendo precedencia.

## Tasks

- T0 [in_progress] — S1 — parent: preparar rama, tracking, PostgreSQL aislada y preservar propuesta; commit: pendiente.
- T1 [pending] — S1 — worker acotado por context backstop: OPSX 1.1–1.3, fixtures/contratos/documentación; commit: pendiente.
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
