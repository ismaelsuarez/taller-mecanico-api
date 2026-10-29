# Spec Delta

## ADDED Requirements

### Requirement: Repositorios de las tablas de sólo agregado sólo agregan

El acceso desde la aplicación a `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` MUST ofrecer sólo operaciones de alta y de lectura: ningún repositorio de esas tablas MUST exponer modificación ni borrado (RN-15 en la capa de aplicación, además del disparador de la base).

#### Scenario: Sin operaciones de modificación ni borrado
- **WHEN** se inspeccionan los repositorios de las tres tablas de sólo agregado
- **THEN** ninguno ofrece operaciones de actualización, borrado ni borrado lógico, y ninguno hereda del repositorio genérico que las trae

#### Scenario: El alta sigue funcionando dentro de su bloque
- **WHEN** una operación de varias escrituras (cambio de precio, reposición o transición de una orden) agrega su línea de auditoría
- **THEN** la línea queda escrita en la misma transacción que el cambio que registra y se revierte con él si el bloque falla
