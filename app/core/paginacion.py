"""Envoltorio de los listados y cálculo de las páginas (EJ-3, spec listados-paginados).

RT-PG-05: `{items, total, page, size, pages}` con `page ≥ 1`, `size` 1..100
(def. 20); pedir una página más allá de la última da 422 con el mensaje
«La página N no existe: hay M»; con cero resultados hay una página vacía.
El router declara `params: Annotated[ParametrosPagina, Query()]` y llama a
`pagina(...)` con los items ya cortados y el `total` del mismo filtro.
"""

from collections.abc import Sequence
from math import ceil
from typing import Generic, TypeVar

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ParametrosPagina(BaseModel):
    """Query params de todo listado; la validación la hace FastAPI → 422."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class Pagina(BaseModel, Generic[T]):
    """Envoltorio de la respuesta de un listado."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int
    page: int
    size: int
    pages: int


def pagina(items: Sequence[T], total: int, page: int, size: int) -> Pagina[T]:
    """Arma el envoltorio; lanza 422 si la página pedida no existe (RT-PG-05)."""
    pages = max(1, ceil(total / size)) if size > 0 else 1
    if page > pages:
        raise HTTPException(
            status_code=422,
            detail=f"La página {page} no existe: hay {pages}",
        )
    return Pagina(items=list(items), total=total, page=page, size=size, pages=pages)
