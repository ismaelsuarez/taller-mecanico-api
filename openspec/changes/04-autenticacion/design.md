# Design

## Context

Ver `proposal.md` para motivación y alcance; `specs/autenticacion-sesiones/spec.md` fija los comportamientos. Este diseño es necesario por la complejidad de autenticación, transacciones y revocación temporal.

| Evidencia actual | Consecuencia de diseño |
|---|---|
| `security.py:16-32` ya tiene hashing, semáforo y `to_thread`; `gensalt` se evalúa antes del salto al hilo | Ampliar el helper existente y mover también la generación de sal al trabajo protegido fuera del bucle; no duplicar infraestructura |
| `main.py:19-34` configura semáforo, hash ficticio, motor y fábrica en lifespan | Reutilizar esos recursos; no crear motores, hashes o claves al importar |
| `seed.py:47-52` reutiliza seguridad y configura su semáforo en 1 | Preservar ese uso independiente y comprobar regresión; el lifespan de la API establece su propia configuración |
| `usuarios/{schemas,repository,unit_of_work,service,router}.py` contienen sólo docstrings | Implementar allí; no crear una arquitectura paralela |
| Modelos de usuarios/roles/intentos/eventos y vínculo único de cliente ya existen | Sin migración prevista; usar restricciones de la base y traducir `IntegrityError` |
| `UnitOfWork.__aenter__` no inicia por sí mismo una transacción; SQLAlchemy puede iniciarla con una lectura | Cerrar la fase de lectura antes de bcrypt; poner el hash antes del `async with` de escritura no alcanza si hubo lecturas previas |
| La fixture API inserta id=1 con hash no autenticable, sin roles ni avance de secuencia | Crear fixture de autenticación separada, con hashes reales, roles y secuencias correctas sobre PostgreSQL aislada/Alembic |
| `errores.py:41-43,102-122` registra sólo 404/409 y 422 seguro | Agregar handlers explícitos de autenticación, no reutilizar el fallback 409 para 401/429 |

## Goals / Non-Goals

**Goals:** mantener sesión/cookie y auditoría coherentes con la confirmación, preservar precisión temporal, reutilizar capas existentes y producir evidencia reproducible con base real.

**Non-Goals:** serialización de logins concurrentes, Redis, refresh tokens, listas de revocación para logout, permisos RBAC o protección global del CRUD. No iniciar implementaciones con este pedido de propuesta. Las invariantes ya fijadas por la consigna no se presentan como supuestos nuevos.

## Decisions

### D1 — Formas JSON complementarias propuestas

La consigna/KB fija el cuerpo del registro y del login, pero no todas las claves de las otras respuestas. Se proponen estos detalles de interfaz para revisión, no se atribuyen a contratos existentes:

| Operación | Forma propuesta adicional |
|---|---|
| Registro 201 | `{mensaje: "Registro completado", debe_cambiar_password: false, expira_en_segundos: duración_configurada}` |
| Cambio: entrada | `{password_actual, password_nueva}` con extras prohibidos y límite UTF-8 en ambos campos |
| Cambio 200 | `{mensaje: "Contraseña actualizada", debe_cambiar_password: false, expira_en_segundos: duración_configurada}` |
| Logout 200 | `{mensaje: "Sesión cerrada"}` |
| Yo 200 | `{usuario: {id, email, nombre, debe_cambiar_password}, roles_vigentes: [rol], roles_token: [rol]}` |

Alternativa descartada: inventar un DTO genérico nuevo para todo el CRUD o incluir el token en estas respuestas. No se agregan reglas de complejidad de contraseña, normalizaciones de correo o políticas de cuenta no previstas por el proyecto. Al aplicar, documentar estos detalles como supuestos/decisiones de la KB según D-4 y mantener OpenAPI y ejemplos alineados.

### D2 — Capas y límites transaccionales

El router/dependencias construye y entrega los UoW sin abrir; el servicio los abre y los repositorios sólo hacen `flush`. El UoW de usuarios compone repositorios de usuario, asignación, evento y cliente con la misma sesión para el registro. No encadenar el servicio de clientes con otro UoW que confirme por separado.

Registro: validar → calcular hash sin transacción → abrir UoW de usuarios → insertar las cuatro entidades → salir y confirmar → emitir JWT/cookie en router. Un fallo de `flush` o del commit no llega al paso de cookie. La unicidad se decide en la base, nunca mediante una consulta previa de disponibilidad.

Login/cambio: materializar los datos necesarios en una fase corta de lectura con UoW; salir de ella liberando la conexión antes de verificar/calcular hashes; luego abrir la fase de escritura necesaria. Mantener datos primitivos de la lectura para no disparar carga perezosa. La sesión sigue siendo propiedad de su dependencia, que la cierra; no cerrar sesiones desde UoW. No introducir commits manuales para resolver la transacción implícita.

Cambio: tras comprobar la contraseña actual y calcular el nuevo hash fuera de transacción, actualizar hash/timestamp/bandera/evento en un único UoW; después emitir la cookie. Alternativa descartada: mantener una transacción abierta durante bcrypt o emitir `Set-Cookie` desde dentro del servicio antes de confirmar.

### D3 — Intentos independientes y límite de login

Usar el índice existente `(email, ip, cuando)`. Obtener en una consulta el conteo de fallos dentro de 60 s y posteriores al último éxito, junto con el fallo vigente más antiguo. No consultar/verificar credenciales si el límite está alcanzado.

Detalle propuesto: ventana `(ahora - 60 s, ahora]`, fallos estrictamente posteriores al último éxito; `Retry-After = max(1, ceil(segundos_restantes_del_fallo_más_antiguo))` cuando hay bloqueo. Una consulta posterior vuelve a evaluar el límite: el encabezado no promete acceso si hubo nuevos fallos. Los 429 se guardan como `exito=false` y participan del conteo, sin inventar una columna/categoría que permita excluirlos. Éxito reinicia por referencia temporal, no elimina filas.

El router construye también un UoW dedicado de intentos con sesión propia, creada/cerrada por una dependencia separada. El servicio lo usa para registrar el resultado antes de devolverlo o propagar el rechazo. Comentar explícitamente que esas filas sobreviven al rollback de la petición y el costo de la conexión/transacción adicional. No usar `BackgroundTasks` ni commits desde repositorios.

El evento del 429 se confirma en el UoW normal de usuarios antes de devolver el rechazo; el intento se confirma con independencia del resultado de esa transacción. Mantener como excepción transaccional especial la escritura del intento, no convertir todos los eventos en auditoría fuera de la transacción. Un fallo de persistencia obligatoria no se transforma en login exitoso ni en cookie.

Alternativas descartadas: contadores en memoria, borrar intentos antiguos tras éxito, bloqueo fijo adicional de 60 s o excluir silenciosamente las filas bloqueadas del conteo.

### D4 — Bcrypt, JWT y dependencia mínima

Ampliar `security.py` con verificación real/ficticia y generación/verificación JWT usando configuración existente. Tanto `gensalt` como hash/check corren bajo el semáforo y dentro del trabajo ejecutado con `to_thread`. El hash ficticio se calcula una vez por lifespan; no se recalcula por correo inexistente.

Emitir `sub` como identificador textual, `iat` como timestamp numérico fraccional, `exp` acorde a la duración y roles vigentes como información. Validar firma, algoritmo configurado, expiración, tipos y presencia de claims; no elegir algoritmo desde datos no confiables del token. No convertir `iat` a entero ni depender de conversión automática de `datetime` que pierda microsegundos.

Comparar el valor fraccional original con `password_cambiada_en` UTC. El nuevo token se emite después de la confirmación usando una marca temporal que no sea anterior al cambio persistido. Probar dos marcas distintas dentro del mismo segundo sin esperas artificiales de un segundo. La clave es la configurada, no se genera al iniciar la aplicación.

`get_usuario_actual` leerá sólo `request.cookies`, comprobará usuario activo, revocación temporal y aportará identidad reutilizable para EJ-5. Los roles vigentes se cargan explícitamente en repositorio cuando son necesarios para emisión/yo; no conceden ni deniegan permisos sobre CRUD todavía. Se conserva `actor_temporal` hasta EJ-5.

Alternativa descartada: truncar `iat`, aceptar Bearer como respaldo, confiar en roles del JWT como autorización o duplicar luego la dependencia para EJ-5.

### D5 — Errores, cookies y montaje

Agregar errores de autenticación con handlers 401/429 explícitos y posibilidad de `Retry-After`; preservar handlers 404/409, error textual de paginación y 422 sin eco. Los validadores de contraseñas no incluyen el valor recibido en sus mensajes. Añadir etiquetas humanas de campos de auth sólo cuando sea necesario, con tests de regresión del traductor compartido.

Centralizar emisión/eliminación de `access_token` con los atributos de la spec; proponer `Path=/` coherente para ambos y sin Domain explícito. Montar el router `/auth` como abierto; yo/cambio agregan su dependencia local de autenticación. Logout no exige token válido ni revoca JWT copiados.

Alternativa descartada: usar el traductor 409 existente para todas las excepciones nuevas, duplicar 422 o proteger todo el árbol de rutas antes de EJ-5.

### D6 — Verificación y unidades de trabajo para apply

Cada regla nueva comienza con RED y termina con GREEN usando pytest/httpx y PostgreSQL real aislada con Alembic. Fixtures auth con identidades/roles reales, ids generados o secuencias sincronizadas; no adaptar globalmente el admin ficticio del CRUD sin necesidad. Los tests de rollback y commit fallido observan estado con otra sesión; se permite inyectar un fallo en el límite del UoW sin reemplazar la base real por mocks.

Los escenarios de tiempo combinan evidencia del recorrido real/ficticio, observación del trabajo fuera del bucle y mediciones repetidas comparables; no fijar un umbral absoluto de milisegundos para hardware desconocido. Controlar el reloj en los bordes temporales de pruebas sin falsear el almacenamiento ni saltar verificaciones JWT.

| Casos | Evidencia prevista |
|---|---|
| C-01 | 422 de ruta inválida con cookie válida, sin cambio del contrato existente |
| C-02 | Registro atómico, duplicados, cookie sólo tras commit y ausencia de filas sueltas |
| C-03 | Atributos cookie, cuerpo sin token y Bearer sin cookie → 401 |
| C-04 | Mismo cuerpo 401 y costo comparable para inexistente/contraseña incorrecta |
| C-05 | Cinco fallos, sexto sin bcrypt, Retry-After, persistencia y reset/aislamiento |
| C-09 parcial | Cookie nueva válida/anterior inválida dentro del mismo segundo; bandera limpia; no prueba aún el 403 global |

`test/auth.http` usa respuestas esperadas comentadas y sesiones explícitas (`# @name`, `# @no-cookie-jar`, `Cookie: {{loginX.response.headers.Set-Cookie}}`), con seed sobre base de prueba antes del archivo. Completar suite integrada y regresiones de salud/seed/CRUD. Comparar antes/después los comandos/endpoints ajenos que compartan helpers modificados, sin incorporar lecturas de historia Git a tests versionados.

Implementar secuencialmente unidades revisables con tests/docs asociados; las tareas no autorizan publicación. Por seguridad y código compartido, la implementación necesita verificación independiente; el circuito nativo de revisión se decide por sus reglas vigentes, sin dar por aprobada esta propuesta por haber validado su sintaxis.

## Risks / Trade-offs

- [Cookie antes del commit o fallo de auditoría oculto] → Router emite únicamente tras éxito de los UoW requeridos; probar fallo al confirmar.
- [Autobegin retiene conexión durante bcrypt] → Separar fases de lectura/CPU/escritura y comprobar el límite real, no sólo la posición textual del `async with`.
- [Pérdida de fracción temporal] → Preservar NumericDate fraccional extremo a extremo y probar revocación en el mismo segundo.
- [Regresión en errores, seed o salud compartidos] → Tests previos, suite completa y comparación diferencial de superficies compartidas.
- [Fixture no autenticable o secuencia desfasada] → Fixture auth separada con base migrada y hashes reales.
- [Paralelismo de peticiones] → No se promete exclusión entre logins concurrentes; sigue fuera del alcance de la consigna. No añadir locks/Redis ni ampliar alcance incidentalmente.
- [Percepción de seguridad completa] → README deja explícito que el CRUD continúa abierto hasta EJ-5.

## Migration Plan

No se prevén migraciones, nuevos secretos ni dependencias. Mantener `JWT_SECRET`, valores configurados, seed y esquema existentes. Aplicar sólo después de aprobar la propuesta; verificar en base de test reconstruible, nunca vaciar desarrollo. Reversión de código por unidades, sin reescribir datos ni historial; no ejecutar archive, commits de entrega o push como parte de `propose`.

No hay decisiones de producto bloqueantes identificadas. D1 y los detalles temporales/de cookie propuestos deben quedar visibles en la revisión y registrarse en la KB al implementar, no presentarse como exigencias textuales de la consigna.
