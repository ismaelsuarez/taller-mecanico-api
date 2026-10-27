# Tasks

Ejecución de `/opsx:apply 04-autenticacion`. Las casillas marcadas cuentan con evidencia registrada en `odd/tasks/04-autenticacion.md`; las restantes siguen pendientes. Referencias: [spec](specs/autenticacion-sesiones/spec.md) y [diseño](design.md), decisiones D1–D6. Mantener el orden secuencial de los grupos; tests y documentación acompañan cada comportamiento, no se posponen al cierre.

Unidades previstas: un grupo funcional por unidad revisable, subdividiendo si supera aproximadamente 400 líneas autorales, con tests/docs junto al código. Riesgos de implementación: seguridad (item 2), helpers/contratos compartidos (item 3) y semáforo existente (item 4 cuando se modifique su comportamiento). No agrupar todo EJ-4 en una sola revisión ni afirmar un tamaño exacto antes de ver el diff.

## 1. Contratos y preparación de pruebas aisladas

- [x] 1.1 Agregar fixture específica de autenticación sobre PostgreSQL de test con Alembic, hashes reales, roles y secuencias coherentes, sin reemplazar la fixture CRUD; verificar creación consecutiva de usuarios sin colisión y que las pruebas actuales de fixtures/CRUD siguen pasando.
- [x] 1.2 Implementar contratos de entrada/salida en `usuarios/schemas.py` conforme spec y D1, con `extra="forbid"` y 72 bytes UTF-8 en registro/login/actual/nueva; observar RED/GREEN para 72/73 bytes ASCII, 36/37 `ñ`, extras, campos ausentes y salida sin hash/token.
- [x] 1.3 Documentar las formas JSON propuestas de D1 como decisiones/supuestos del proyecto y límites de entrada; verificar correspondencia entre contratos y documentación, sin agregar complejidad de contraseña, normalización de correo ni requisitos de EJ-5.

## 2. Primitivas de seguridad reutilizables

- [x] 2.1 Ampliar el helper bcrypt existente para verificar contraseñas reales/ficticias y ejecutar también `gensalt` dentro del trabajo protegido por semáforo/`to_thread`; observar RED/GREEN del límite de concurrencia y avance del bucle, conservando el uso del helper por seed y lifespan.
- [x] 2.2 Agregar emisión/verificación JWT con clave fija, algoritmo configurado, claims requeridos, `sub` textual e `iat` fraccional; verificar firmas/claims inválidos, vencimiento y preservación de dos instantes distintos dentro del mismo segundo, sin depender de truncamiento de la biblioteca.
- [x] 2.3 Documentar helpers y configuración reutilizada, sin secretos ni nuevas variables innecesarias; ejecutar regresiones focalizadas de configuración, lifespan, salud y seed, verificando sus comportamientos previos y la ausencia de recursos creados al importar.

## 3. Registro atómico y cookie posterior al commit

- [ ] 3.1 Componer repositorios y UoW de usuarios con cliente/asignaciones/eventos en una sola sesión, manteniendo `flush` en repositorios y commit exclusivo del UoW; probar registro completo y rollback por unicidad/fallo de confirmación contra base real y observar estado desde otra sesión.
- [ ] 3.2 Implementar servicio y ruta de registro con hash previo a cualquier transacción, emisión de cookie tras commit y montaje abierto de `/auth`; observar RED/GREEN HTTP de 201, correo/documento duplicados 409, prohibición de apropiarse de ficha existente, extras 422 y ausencia de filas parciales/cookie en errores.
- [ ] 3.3 Incorporar C-02 en `test/auth.http` con respuestas esperadas, sesiones explícitas y ejecución tras seed de prueba; documentar registro en README/OpenAPI y verificar que contrato, atributos de cookie y eventos/actores coinciden con las respuestas observadas.

## 4. Login limitado y auditado

- [ ] 4.1 Agregar consulta del límite correo/IP y UoW de intentos con sesión independiente, junto con comentario de costo/rollback; observar RED/GREEN para cinco fallos, límite de 60 s, reinicio tras éxito sin borrado, aislamiento correo/IP y persistencia de intentos ante rollback de la petición.
- [ ] 4.2 Implementar login con lectura breve cerrada antes de bcrypt, verificación real/ficticia, caso inactivo DD-24 y traducción explícita 401/429 con `Retry-After`; probar sexto intento sin bcrypt, evento bloqueado, igualdad exacta de cuerpos 401, costo comparable, resultado exitoso y ausencia de cookie cuando falla el commit obligatorio.
- [ ] 4.3 Agregar C-04/C-05 a `test/auth.http`, documentar ventana y conteo de 429 de D3, mensajes y excepción transaccional; verificar OpenAPI 200/401/422/429, encabezado Retry-After, todas las filas/eventos esperados y regresiones de 404/409/422/paginación tras tocar errores compartidos.

## 5. Identidad por cookie y cierre de sesión

- [ ] 5.1 Implementar dependencia mínima reutilizable que lee sólo cookie y verifica JWT/usuario activo/revocación temporal; observar RED/GREEN HTTP para falta de cookie, Bearer sin cookie, firma/claims inválidos, expiración y usuario inexistente/inactivo, sin cablear permisos RBAC.
- [ ] 5.2 Implementar `/auth/yo` con roles vigentes precargados y roles JWT diferenciados, y logout público con eliminación coherente de cookie; probar roles revocados/vencidos tras emitir token, ausencia de hash, logout con/sin cookie y 401 posterior al eliminarla.
- [ ] 5.3 Completar C-01/C-03 y ejemplos yo/logout en `test/auth.http`, con cookies de sesiones nombradas sin cookie jar implícito; verificar respuestas/OpenAPI y documentar expresamente que el CRUD/actor temporal se conserva abierto hasta EJ-5.

## 6. Cambio de contraseña y renovación de sesión

- [ ] 6.1 Implementar comprobación actual y cálculo del hash nuevo fuera de transacciones, seguidos de actualización atómica de hash/timestamp/bandera/evento; observar RED/GREEN de actual incorrecta 401, límites 422 y rollback por fallo de commit sin cambios parciales ni cookie nueva.
- [ ] 6.2 Emitir la cookie de reemplazo después de confirmar y aplicar comparación temporal sin truncamiento; probar vía HTTP login y cambio dentro del mismo segundo: cookie vieja 401, nueva 200 en yo, contraseña vieja inválida, bandera limpia y evento con actor correcto.
- [ ] 6.3 Agregar C-09 parcial a `test/auth.http` y documentar cuerpos D1, nueva cookie e invalidación inmediata; verificar ejecución con cambio pendiente y dejar explícito que el bloqueo global 403 corresponde a EJ-5.

## 7. Verificación integrada y preparación del relevo

- [ ] 7.1 Ejecutar suite pytest completa sobre PostgreSQL aislada con esquema migrado y todos los ejemplos de `test/auth.http` tras seed; comprobar C-01..C-05 y C-09 parcial, sin saltados, preservando salud/CRUD/seed y registrando resultados reales, no sólo existencia de tests.
- [ ] 7.2 Ejecutar una comparación diferencial de las superficies ajenas que compartan helpers modificados contra la base previa, verificando códigos, cuerpos y encabezados relevantes; corregir cualquier diferencia no pedida y fijarla con regresión, sin introducir dependencia de Git en tests versionados.
- [ ] 7.3 Obtener verificación independiente por riesgos de seguridad y código compartido, revisar los deltas con las reglas nativas vigentes y comprobar ausencia de secretos, tokens en cuerpos, lectura de Authorization, commits fuera de UoW y conexión retenida durante bcrypt; registrar aprobación, fallos o bloqueos sin inventar evidencia.
- [ ] 7.4 Validar el change con OpenSpec y conciliar spec/diseño/tasks, README, OpenAPI, ejemplos y decisiones KB ya actualizados por cada grupo; comprobar el handoff EJ-4 sin marcar EJ-5 iniciado. Repetir ciclo Alembic up/down/up sólo si surgió un cambio de esquema autorizado; no ejecutar limpiezas sobre desarrollo.

## Workflow follow-up

- Con la implementación y su verificación completas, ejecutar `/opsx:archive 04-autenticacion` según el flujo autorizado; no forma parte de esta propuesta.
- Verificar las specs canónicas resultantes y marcar EJ-4 en `CHANGES.md` en el commit de cierre correspondiente.
- Sincronizar memoria y publicar únicamente con autorización de entrega vigente; no inferir permiso de push/merge a partir de `propose` ni de una revisión aprobada.
- El relevo a EJ-5 requiere EJ-4 archivado, commiteado y empujado. No iniciar EJ-5 en este change.
