# Casos de Prueba, Evaluación y Entrega

## Casos de prueba mínimos

El proyecto incluye archivos `.http` en `test/` que demuestran los casos siguientes, **cada uno con la respuesta esperada en un comentario**, y un `test/solo_agregado.sql` para el caso C-14. **Antes de cada archivo se corre `python seed.py`.**

| Caso | Qué se demuestra | Resultado esperado | Reglas |
|---|---|---|---|
| C-01 | Un parámetro de ruta que no es entero, con la sesión iniciada | 422, sin ejecutar el handler | RT-PG-07 |
| C-02 | Registro; correo y documento repetidos | 201; 409 con mensaje propio, y el registro rechazado no deja ninguna fila suelta | RN-01, RN-02 |
| C-03 | La cookie del login | `Set-Cookie` con `HttpOnly`, `SameSite=Lax` y `Max-Age`; el cuerpo sin token; sin cookie o con `Authorization: Bearer`, 401 | RT-SE-07 |
| C-04 | Correo existente con contraseña mala, y correo inexistente | 401 con el mismo cuerpo y un tiempo parecido | RN-09 |
| C-05 | Seis intentos fallidos seguidos | El sexto, 429 con `Retry-After` y en pocos milisegundos; los cinco fallos están en `intento_acceso` | RN-08 |
| C-06 | 401 contra 403, y lo propio | Sin rol, 403; el cliente ve su orden (200) y no la ajena (403) | RN-04, RN-17 |
| C-07 | Revocar un rol con la sesión abierta; vencimientos inválidos | La misma cookie, 403 en la petición siguiente; `/auth/yo` muestra la diferencia; la fila revocada sigue. Un vencimiento en el pasado o sin zona horaria, 422 | RN-04, RT-SE-11 |
| C-08 | Autoprotección | El administrador no se revoca su ADMIN: 409 | RN-05 |
| C-09 | Cambio obligatorio | Bloqueado (403) salvo `/auth`; después del cambio, la cookie nueva vale y la anterior da 401, sin esperar entre el login y el cambio | RN-06, RN-07 |
| C-10 | Alta de una orden con dos ítems | 201 con los precios copiados, el total y el historial; con un repuesto inexistente, 409 y la orden no queda creada | RN-10 |
| C-11 | Terminar la orden 2, que pide más bujías que las que hay | 409; el estado, el stock, los movimientos y el historial quedan exactamente como estaban | RN-13 |
| C-12 | Reponer y terminar la orden 2 | 200; baja el stock, aparecen los movimientos y la línea de historial; el aviso sale en el registro después de la respuesta | RN-13, RN-14, RT-TX-07 |
| C-13 | Cancelar | El dueño cancela su orden pendiente (200); una orden ajena da 403; una terminada, 409 | RN-11, RN-12 |
| C-14 | UPDATE y DELETE sobre las tres tablas de sólo agregado en `psql`; una orden con un estado que no está en el catálogo | Los seis, rechazados por el disparador; el último, por la clave foránea | RN-15, RN-19 |
| C-15 | Detalle de una orden con 2 y con 4 ítems | La misma cantidad de consultas en la consola | RT-TX-06 |
| C-16 | Búsqueda con `' OR '1'='1`; paginación con filtro; PATCH parcial; PATCH del stock | Lista vacía con total 0; con `q=freno&size=1`, total 1 y pages 1, y `page=2` da 422; `size=500`, 422; sólo cambia lo enviado; 422 | RT-PG-01, 03, 05, 06 |
| C-17 | Catálogo de estados; filtrar órdenes por un estado que el contrato no declara | Los cuatro por posición, con TERMINADA y CANCELADA finales; sin sesión, 401; 422 | RN-19, RT-PG-08 |
| C-18 | Cambiar el precio de un repuesto y después sólo su descripción | Una línea nueva en `/repuestos/{id}/precios` con el precio anterior y el nuevo; el segundo PATCH no agrega ninguna; la recepción recibe 403 | RN-20 |
| C-19 | Dar de baja un vehículo sin órdenes y registrarlo con la misma patente para otro cliente | 204 y 201: el índice único parcial sólo cuenta los vigentes; una segunda patente vigente igual, 409 | RN-01, RN-16 |

### Varias sesiones a la vez (REST Client)

Con la extensión «REST Client», cada login se nombra con `# @name` y los pedidos de esa sesión llevan `# @no-cookie-jar` y el encabezado:

```http
Cookie: {{loginAdmin.response.headers.Set-Cookie}}
```

Así un mismo archivo puede tener la sesión del administrador y la de la recepción al mismo tiempo (necesario para C-07).

## Requisitos no funcionales

| Requisito | Detalle |
|---|---|
| Asincronía | Todos los handlers con `async def`; bcrypt siempre fuera del bucle |
| Credenciales | Ninguna contraseña ni clave de firma en el código —tampoco como valor por defecto—, en `alembic.ini` ni en el repositorio |
| Token | Sólo en la cookie `HttpOnly`; nunca en el cuerpo ni leído de la cabecera `Authorization` |
| Esquema | Sólo con Alembic; la aplicación no usa `create_all` |
| Transacciones | Ningún repositorio confirma; ningún servicio construye su Unit of Work; el Unit of Work no cierra la sesión |
| Carga perezosa | Prohibida: toda relación que se lee se precarga en el repositorio |
| SQL | Nunca armado por concatenación con datos del usuario |
| Errores | Mensajes propios; nunca el texto de la base ni una traza; ninguna entrada inválida termina en un 500 |
| Unicidad | Garantizada por la base; no se verifica con una consulta previa |
| Diagnóstico | Las consultas se pueden ver en la consola (`SQL_ECHO=true` o equivalente) |

## Criterios de evaluación

| Criterio | Peso | Qué se mira |
|---|---|---|
| Proyecto, configuración y ciclo de vida | 8 % | Estructura, Settings sin secretos por defecto, motor y fábrica creados en el lifespan, `get_session`, salud |
| Modelos, relaciones y migraciones | 14 % | Restricciones, índices únicos parciales, catálogo con clave foránea, navegación, dos migraciones (una a mano), upgrade y downgrade |
| Contratos y CRUD | 10 % | Contratos separados, `extra="forbid"`, códigos, ninguna entrada inválida en 500, PATCH parcial, envoltorio y paginación de la sección 2.9 |
| Autenticación | 16 % | bcrypt fuera del bucle y con semáforo, orden del login, límite, hash ficticio, cookie HttpOnly |
| Autorización | 14 % | 401 y 403, roles vigentes en la base, autoprotección, dos grupos de rutas, `iat`, lo propio |
| Repositorios y Unit of Work | 20 % | Dos jerarquías, clase del modelo, `flush` y no `commit`, precarga en el repositorio, quién crea, abre, confirma y cierra, operaciones de varias escrituras |
| Integridad | 10 % | Disparador de sólo agregado en las tres tablas; historial de precios en la misma transacción; intento de acceso en su propia sesión |
| Lecturas sin N+1 y asincronía | 8 % | Consultas fijas en el detalle; ninguna llamada bloqueante; aviso en segundo plano |

> ⚠️ **Bloqueante**: un proyecto que no levanta, que no crea su esquema con `alembic upgrade head` sobre una base vacía o que contiene credenciales reales en el repositorio **no se corrige hasta que se subsane**.

## Formato de entrega

- Repositorio con el código fuente completo, `requirements.txt`, `env.example`, `alembic.ini`, la carpeta `migrations/` y la carpeta `test/`. **El archivo `.env` no se sube.**
- `README.md` con los pasos para levantar el proyecto desde cero: entorno virtual, dependencias, `.env` (con cómo generar la clave de firma), `alembic upgrade head`, `python seed.py` y arranque del servidor.
- **Evidencia del caso C-15**: una captura o un fragmento de la consola con las consultas del detalle de una orden con 2 ítems y de otra con 4.
- **Evidencia del caso C-14**: una captura de `psql` con los seis rechazos del disparador y el de la clave foránea.

### Checklist de entrega

- [x] `.env` en `.gitignore`; `env.example` sin secretos
- [x] `alembic upgrade head` → `downgrade base` → `upgrade head` sobre base vacía
- [x] `python seed.py` deja el estado inicial
- [x] `test/*.http` con C-01..C-19 y respuestas esperadas en comentarios
- [x] `test/solo_agregado.sql`
- [x] Captura C-14 (psql) y C-15 (consola con SQL)
- [x] README con los pasos desde cero
