"""solo_agregado — función + triggers que rechazan UPDATE y DELETE en las tablas de auditoría.

ESTA MIGRACIÓN FUE ESCRITA A MANO Y LEÍDA COMPLETA ANTES DE APLICARLA (regla A-3, DD-06).
La comparación automática de Alembic no ve funciones ni triggers: por eso va aparte.

Tablas protegidas (RN-15): historial_estado_orden, movimiento_stock, historial_precio_repuesto.
El disparador se dispara en UPDATE y DELETE, venga de donde venga (aplicación, psql u otro rol).
El downgrade elimina los triggers y la función.

Revision ID: a1b2c3d4e5f6
Revises: f8513bf4e6fc
Create Date: 2026-10-26 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f8513bf4e6fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Las tres tablas de sólo agregado (RN-15).
TABLAS_AUDITORIA = (
    "historial_estado_orden",
    "movimiento_stock",
    "historial_precio_repuesto",
)

FUNCION = """
CREATE OR REPLACE FUNCTION solo_agregado() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'La tabla % es de sólo agregado: no se puede modificar ni borrar.', TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

BORRAR_FUNCION = "DROP FUNCTION IF EXISTS solo_agregado() CASCADE;"


def upgrade() -> None:
    """Crea la función y los tres triggers de sólo agregado."""
    op.execute(FUNCION)
    for tabla in TABLAS_AUDITORIA:
        op.execute(f"""
            CREATE TRIGGER trg_{tabla}_solo_agregado
            BEFORE UPDATE OR DELETE ON {tabla}
            FOR EACH ROW EXECUTE FUNCTION solo_agregado();
        """)


def downgrade() -> None:
    """Elimina los triggers y la función."""
    for tabla in TABLAS_AUDITORIA:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tabla}_solo_agregado ON {tabla};")
    op.execute(BORRAR_FUNCION)
