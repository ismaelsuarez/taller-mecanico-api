# Spec Delta

## REMOVED Requirements

- Terminación atómica que descuenta stock
  **Reason**: EJ-6 la entregó deliberadamente sin aviso (T-9); EJ-8 agrega el aviso en segundo plano y el escenario de C-12 pasa a cubrirlo, así que el requisito se reescribe con otro nombre y otro escenario.
  **Migration**: Reemplazado por «Terminación de una orden con stock, historial y aviso» en esta misma delta.

## ADDED Requirements

### Requirement: Terminación de una orden con stock, historial y aviso

Terminar una orden `EN_REPARACION` MUST, en una sola transacción, descontar el stock de cada ítem por el punto único de escritura, dejar un movimiento de salida por ítem (cantidad negativa, `orden_id`, motivo «Salida por orden de trabajo #N», firmado por quien termina), pasar a `TERMINADA` con una línea de historial y responder 200. `mecanico_id` no cambia (DD-31). Otro estado → 409 (RN-11, RN-13). Confirmada la terminación MUST quedar agendado el aviso en segundo plano que define `asincronia-segundo-plano` (RT-TX-07, T-9); con un 404, 403 o 409 MUST quedar sin agendar ningún aviso.

#### Scenario: Reponer y terminar la orden 2 (C-12)
- **WHEN** el administrador repone 2 bujías y `mecanico@example.com` termina la orden 2
- **THEN** responde 200 con estado `TERMINADA`, el stock de la bujía queda en 0, aparece un movimiento de −4 con motivo «Salida por orden de trabajo #2», una línea `EN_REPARACION → TERMINADA` firmada por el mecánico y el aviso en segundo plano queda agendado para salir en el registro después de la respuesta

#### Scenario: El ADMIN termina sin cambiar el mecánico
- **WHEN** un ADMIN termina una orden `EN_REPARACION` con stock suficiente
- **THEN** responde 200, `mecanico_id` conserva al mecánico que la inició y el historial y los movimientos llevan el `usuario_id` del ADMIN

#### Scenario: Orden que no está en reparación
- **WHEN** el mecánico asignado o un ADMIN terminan una orden `PENDIENTE`, `TERMINADA` o `CANCELADA`
- **THEN** responde 409 sin modificar stock, movimientos, estado ni historial

#### Scenario: Repuesto dado de baja después del alta
- **WHEN** se termina una orden cuyo repuesto fue dado de baja después de crearla, con stock suficiente
- **THEN** responde 200 y descuenta el stock de ese repuesto como de cualquier otro (DD-21)
