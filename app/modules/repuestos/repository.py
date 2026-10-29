"""Repositorios de cada entidad del módulo repuestos (Repuesto, MovimientoStock y HistorialPrecio) — EJ-3.

`MovimientoStockRepository` y `HistorialPrecioRepository` son de sólo escritura
(apend-only, RN-15): sólo `add`, nunca update ni delete. El punto único de
escritura de stock (RN-14, T-3) vive en `RepuestoRepository.registrar_movimiento`.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errores import StockInsuficiente
from app.core.repository import SoftDeleteRepository
from app.modules.repuestos.models import HistorialPrecio, MovimientoStock, Repuesto


class RepuestoRepository(SoftDeleteRepository[Repuesto]):
    def __init__(self, sesion: AsyncSession) -> None:
        super().__init__(sesion, Repuesto)

    async def buscar_vigentes(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[Repuesto], int]:
        """Búsqueda «contiene» por descripción con parámetros ligados (RT-PG-06, C-16).

        Devuelve (página, total) con los mismos filtros; excluye dados de baja.
        """
        consulta = select(Repuesto).where(Repuesto.borrado_en.is_(None))
        if q:
            # ILIKE con parámetro ligado: nunca SQL armado con datos del usuario.
            consulta = consulta.where(Repuesto.descripcion.ilike(f"%{q}%"))

        conteo = await self.sesion.execute(
            select(func.count()).select_from(consulta.subquery())
        )
        total = conteo.scalar_one()

        consulta = (
            consulta.order_by(Repuesto.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        resultado = await self.sesion.execute(consulta)
        return list(resultado.scalars().all()), total

    async def get_by_id_con_movimientos_y_precios(self, id: int) -> Repuesto | None:
        """Repuesto con sus movimientos y su historial de precios (T-10)."""
        resultado = await self.sesion.execute(
            select(Repuesto)
            .where(Repuesto.id == id, Repuesto.borrado_en.is_(None))
            .options(
                selectinload(Repuesto.movimientos),
                selectinload(Repuesto.historial_precios),
            )
        )
        return resultado.scalars().first()

    async def get_movimientos(self, repuesto_id: int) -> list[MovimientoStock]:
        """Movimientos en orden cronológico; sólo los del repuesto pedido."""
        resultado = await self.sesion.execute(
            select(MovimientoStock)
            .where(MovimientoStock.repuesto_id == repuesto_id)
            .order_by(MovimientoStock.cuando, MovimientoStock.id)
        )
        return list(resultado.scalars().all())

    async def get_historial_precios(self, repuesto_id: int) -> list[HistorialPrecio]:
        resultado = await self.sesion.execute(
            select(HistorialPrecio)
            .where(HistorialPrecio.repuesto_id == repuesto_id)
            .order_by(HistorialPrecio.cuando, HistorialPrecio.id)
        )
        return list(resultado.scalars().all())

    async def registrar_movimiento(
        self,
        repuesto: Repuesto,
        cantidad: int,
        motivo: str,
        usuario_id: int,
        orden_id: int | None = None,
    ) -> MovimientoStock:
        """PUNTO ÚNICO DE ESCRITURA DE STOCK (RN-14, T-3): movimiento + `stock` juntos.

        Lo usan el alta con `stock_inicial`, la reposición y (EJ-6) la terminación
        de órdenes. `cantidad > 0` suma, `cantidad < 0` resta (SU-08).

        La guarda vive acá y no en el llamador (D5): una salida mayor al stock lanza
        `StockInsuficiente` (409) **antes** de agregar el movimiento o tocar el stock,
        así ningún llamador futuro deja stock negativo; el `CHECK` de la base queda
        como última defensa.
        """
        if repuesto.stock + cantidad < 0:
            raise StockInsuficiente(repuesto.descripcion, repuesto.codigo, repuesto.stock, -cantidad)
        movimiento = MovimientoStock(
            repuesto_id=repuesto.id,
            orden_id=orden_id,
            usuario_id=usuario_id,
            cantidad=cantidad,
            motivo=motivo,
            cuando=datetime.now(timezone.utc),
        )
        self.sesion.add(movimiento)
        repuesto.stock += cantidad
        await self.sesion.flush()
        return movimiento


class MovimientoStockRepository:
    """Sólo lectura/escritura de movimientos (apend-only, RN-15)."""

    def __init__(self, sesion: AsyncSession) -> None:
        self.sesion = sesion

    async def add(self, movimiento: MovimientoStock) -> MovimientoStock:
        self.sesion.add(movimiento)
        await self.sesion.flush()
        return movimiento


class HistorialPrecioRepository:
    """Sólo lectura/escritura del historial de precios (apend-only, RN-15)."""

    def __init__(self, sesion: AsyncSession) -> None:
        self.sesion = sesion

    async def add(self, linea: HistorialPrecio) -> HistorialPrecio:
        self.sesion.add(linea)
        await self.sesion.flush()
        return linea

    async def add_si_hubo_cambio(
        self,
        repuesto: Repuesto,
        precio_anterior: Decimal,
        precio_nuevo: Decimal,
        usuario_id: int,
    ) -> HistorialPrecio | None:
        """RN-20: línea sólo si el precio cambió de verdad (CHECK `<>` lo garantiza)."""
        if precio_anterior == precio_nuevo:
            return None
        linea = HistorialPrecio(
            repuesto_id=repuesto.id,
            usuario_id=usuario_id,
            precio_anterior=precio_anterior,
            precio_nuevo=precio_nuevo,
            cuando=datetime.now(timezone.utc),
        )
        self.sesion.add(linea)
        await self.sesion.flush()
        return linea
