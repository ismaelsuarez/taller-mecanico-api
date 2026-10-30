"""Fixtures de EJ-8 (asincronía y consultas fijas): reutiliza la base y la API sembradas de EJ-6."""

from ordenes.conftest import (  # noqa: F401  (fixtures reales: Alembic + `seed.py` en subproceso)
    Datos,
    EntornoSembrado,
    api_sembrada,
    base_sembrada,
    fabrica,
    _passwords_del_seed,
)
