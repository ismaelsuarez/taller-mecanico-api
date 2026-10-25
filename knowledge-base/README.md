# Taller Mecánico — Base de Conocimiento

Base de conocimiento generada a partir de `docs/TP_Cap1a6_Consigna.pdf` (Programación III · UTN · TP Unidades 1 a 6: *"Taller mecánico: órdenes de trabajo, stock y acceso con FastAPI y PostgreSQL"*). La consigna es la **única fuente de verdad**: lo que no figura en ella está marcado como **Suposición**.

## Índice de Archivos

| Archivo | Contenido |
|---|---|
| [01_vision_y_objetivos.md](01_vision_y_objetivos.md) | Propósito, objetivos pedagógicos, actores, alcance y fuera de alcance, pesos de evaluación |
| [02_descripcion_general.md](02_descripcion_general.md) | Stack obligatorio, arquitectura en capas, configuración, **todos los endpoints de referencia** |
| [03_actores_y_roles.md](03_actores_y_roles.md) | Roles, matriz RBAC, 401 vs 403, rutas públicas, usuarios del seed |
| [04_modelo_de_datos.md](04_modelo_de_datos.md) | 13 tablas con columnas y restricciones obligatorias, ERD, índices parciales, migraciones, seed |
| [05_reglas_de_negocio.md](05_reglas_de_negocio.md) | RN-01..RN-20 (códigos de la consigna) + reglas técnicas RT-* |
| [06_funcionalidades.md](06_funcionalidades.md) | Épicas por ejercicio (Ej. 1–8) e historias US-001..US-024 con criterios |
| [07_flujos_principales.md](07_flujos_principales.md) | Registro, login, petición protegida, roles, órdenes (alta/iniciar/terminar/cancelar), stock, precios, paginación |
| [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md) | Patrones, estructura de directorios obligatoria, seguridad, variables de entorno |
| [09_decisiones_y_supuestos.md](09_decisiones_y_supuestos.md) | DD-01..DD-35 (incluye pedidos verbales del docente) y supuestos SU-01..SU-14 |
| [10_preguntas_abiertas.md](10_preguntas_abiertas.md) | Inconsistencias IN-01..IN-04 y preguntas para la cátedra |
| [11_casos_de_prueba_y_entrega.md](11_casos_de_prueba_y_entrega.md) | Casos C-01..C-19, requisitos no funcionales, criterios de evaluación, formato de entrega |

## Quick Start para Desarrolladores

1. Entender el dominio → [01](01_vision_y_objetivos.md), [03](03_actores_y_roles.md)
2. Entender los datos → [04](04_modelo_de_datos.md)
3. Entender las reglas → [05](05_reglas_de_negocio.md)
4. Entender la arquitectura → [02](02_descripcion_general.md), [08](08_arquitectura_propuesta.md)
5. Implementar → [07](07_flujos_principales.md), [06](06_funcionalidades.md)
6. Verificar contra la corrección → [11](11_casos_de_prueba_y_entrega.md)
7. Antes de codificar → [10](10_preguntas_abiertas.md)

## Resumen Ejecutivo

API REST asincrónica (FastAPI + SQLModel/SQLAlchemy 2.0 async + PostgreSQL 16 + Alembic) para un taller mecánico: clientes y vehículos, órdenes de trabajo con ítems, stock de repuestos por movimientos y control de acceso con 4 roles vigentes en la base. El foco evaluado es la arquitectura **Router → Service → UoW → Repository → Model**, la autenticación con bcrypt + JWT en cookie HttpOnly, la autorización 401/403 consultando la base, y la atomicidad de las operaciones multi-escritura (registro, terminar orden, cambio de precio), con las garantías de integridad delegadas en la base (índices únicos parciales, FKs al catálogo, CHECKs y disparador de sólo agregado).
