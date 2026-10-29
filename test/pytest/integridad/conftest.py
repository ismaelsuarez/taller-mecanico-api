"""Fixtures de EJ-7 (integridad): reutiliza la base y la API sembradas de EJ-6, sin duplicarlas."""

from ordenes.conftest import (  # noqa: F401  (fixtures reales: Alembic + `seed.py` en subproceso)
    EntornoSembrado,
    api_sembrada,
    base_sembrada,
)
