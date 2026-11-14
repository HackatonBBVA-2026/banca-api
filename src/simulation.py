import asyncio
from datetime import datetime
from decimal import Decimal
import random
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.broadcaster import Broadcaster, broadcaster as default_broadcaster
from src.config import get_settings
from src.database import db_write_lock
from src.models import Comercio, Cuenta, Movimiento
from src.schemas import MovimientoResponse, SimulacionStatusResponse, TickOverrideRequest

# Default transaction templates for simulation (75% expense, 15% transfer, 10% income)
EXPENSE_TEMPLATES = [
    ("Alimentación", "Supermercados", "Metro - Compra de víveres", "POS", Decimal("25.00"), Decimal("220.00")),
    ("Alimentación", "Supermercados", "Wong - Compra de alimentos", "POS", Decimal("35.00"), Decimal("280.00")),
    ("Alimentación", "Restaurantes", "Restaurante Central - Almuerzo", "POS", Decimal("30.00"), Decimal("140.00")),
    ("Alimentación", "Cafetería", "Starbucks - Café y bocaditos", "POS", Decimal("15.00"), Decimal("45.00")),
    ("Transporte", "Taxi", "Uber - Viaje Urbano", "online", Decimal("12.00"), Decimal("50.00")),
    ("Transporte", "Gasolina", "Primax - Combustible G-Premium", "POS", Decimal("50.00"), Decimal("180.00")),
    ("Entretenimiento", "Cine", "Cineplanet - Entradas cine", "online", Decimal("28.00"), Decimal("85.00")),
    ("Servicios", "Electricidad", "Luz del Sur - Recibo de Luz", "online", Decimal("45.00"), Decimal("210.00")),
    ("Servicios", "Agua", "Sedapal - Recibo de Agua", "online", Decimal("25.00"), Decimal("110.00")),
    ("Salud", "Farmacia", "InkaFarma - Farmacia y bienestar", "POS", Decimal("15.00"), Decimal("120.00")),
    ("Tecnología", "Electrohogar", "Falabella - Compra de tienda", "POS", Decimal("60.00"), Decimal("350.00")),
]

TRANSFER_TEMPLATES = [
    ("Transferencias", "Transferencia a terceros", "Transferencia inmediata a tercero", "App Móvil", Decimal("20.00"), Decimal("350.00")),
    ("Transferencias", "Transferencia interbancaria", "Transferencia interbancaria CCI", "Banca por Internet", Decimal("50.00"), Decimal("500.00")),
    ("Transferencias", "Transferencia a terceros", "Envío Plin/Yape", "App Móvil", Decimal("10.00"), Decimal("150.00")),
]

INCOME_TEMPLATES = [
    ("Ingresos", "Abono de haberes", "Abono de nómina quincenal", "Transferencia recibida", Decimal("300.00"), Decimal("2500.00")),
    ("Ingresos", "Transferencia recibida", "Transferencia recibida de tercero", "App Móvil", Decimal("30.00"), Decimal("600.00")),
    ("Ingresos", "Depósito en efectivo", "Depósito en efectivo por ventanilla", "Ventanilla", Decimal("50.00"), Decimal("800.00")),
]


class SimulationEngine:
    """Dynamic background banking activity simulation engine."""

    def __init__(
        self,
        interval_min: Optional[float] = None,
        interval_max: Optional[float] = None,
        broadcaster: Optional[Broadcaster] = None,
    ):
        settings = get_settings()
        self.interval_min: float = (
            float(interval_min)
            if interval_min is not None
            else float(settings.SIMULATION_INTERVAL_MIN)
        )
        self.interval_max: float = (
            float(interval_max)
            if interval_max is not None
            else float(settings.SIMULATION_INTERVAL_MAX)
        )
        self.is_running: bool = False
        self.total_events_emitted: int = 0
        self.broadcaster: Broadcaster = (
            broadcaster if broadcaster is not None else default_broadcaster
        )
        self._task: Optional[asyncio.Task] = None

    @property
    def simulation_active(self) -> bool:
        return self.is_running

    def get_status(self) -> SimulacionStatusResponse:
        return SimulacionStatusResponse(
            simulation_active=self.is_running,
            interval_min=int(self.interval_min),
            interval_max=int(self.interval_max),
            active_sse_subscribers=self.broadcaster.subscriber_count,
            total_events_emitted=self.total_events_emitted,
        )

    async def execute_tick(
        self,
        session: AsyncSession,
        override: Optional[TickOverrideRequest] = None,
    ) -> Movimiento:
        """Executes a single simulation tick.
        
        Serialized under db_write_lock. Generates a realistic banking movement (expense 75%,
        transfer 15%, income 10%) or applies override parameters, updates account balance,
        commits to SQLite DB, broadcasts to SSE subscribers, and increments total_events_emitted.
        """
        async with db_write_lock:
            # 1. Select account
            if override and override.cuenta_id is not None:
                stmt = select(Cuenta).where(Cuenta.id == override.cuenta_id)
                res = await session.execute(stmt)
                cuenta = res.scalar_one_or_none()
                if not cuenta:
                    raise ValueError(f"Cuenta with id {override.cuenta_id} not found")
            else:
                stmt = select(Cuenta)
                res = await session.execute(stmt)
                cuentas = list(res.scalars().all())
                if not cuentas:
                    raise ValueError("No accounts available in the database for simulation")
                cuenta = random.choice(cuentas)

            # 2. Determine transaction parameters
            cat = None
            subcat = None
            desc = None
            canal = None
            monto = None

            if override:
                if override.monto is not None:
                    monto = Decimal(str(override.monto)).quantize(Decimal("0.01"))
                cat = override.categoria
                subcat = override.subcategoria
                desc = override.descripcion
                canal = override.canal

            # Determine archetype distribution: 75% expense, 15% transfer, 10% income
            if monto is None:
                rand_val = random.random()
                if rand_val < 0.75:
                    archetype = "expense"
                elif rand_val < 0.90:
                    archetype = "transfer"
                else:
                    archetype = "income"
            else:
                if monto < 0:
                    archetype = "expense"
                else:
                    archetype = "income"

            # Choose template based on archetype
            if archetype == "expense":
                tpl = random.choice(EXPENSE_TEMPLATES)
                default_cat, default_subcat, default_desc, default_canal, min_amt, max_amt = tpl
                if monto is None:
                    raw_amt = round(random.uniform(float(min_amt), float(max_amt)), 2)
                    monto = -Decimal(str(raw_amt)).quantize(Decimal("0.01"))
            elif archetype == "transfer":
                tpl = random.choice(TRANSFER_TEMPLATES)
                default_cat, default_subcat, default_desc, default_canal, min_amt, max_amt = tpl
                if monto is None:
                    raw_amt = round(random.uniform(float(min_amt), float(max_amt)), 2)
                    monto = -Decimal(str(raw_amt)).quantize(Decimal("0.01"))
            else:  # income
                tpl = random.choice(INCOME_TEMPLATES)
                default_cat, default_subcat, default_desc, default_canal, min_amt, max_amt = tpl
                if monto is None:
                    raw_amt = round(random.uniform(float(min_amt), float(max_amt)), 2)
                    monto = Decimal(str(raw_amt)).quantize(Decimal("0.01"))

            final_cat = cat if cat is not None else default_cat
            final_subcat = subcat if subcat is not None else default_subcat
            final_desc = desc if desc is not None else default_desc
            final_canal = canal if canal is not None else default_canal

            # 3. Look up matching comercio if category matches
            comercio_id = None
            if final_cat not in ("Transferencias", "Ingresos"):
                comercio_stmt = select(Comercio).where(Comercio.categoria == final_cat).limit(1)
                comercio_res = await session.execute(comercio_stmt)
                comercio = comercio_res.scalar_one_or_none()
                if comercio:
                    comercio_id = comercio.id

            # 4. Create and persist Movimiento
            movimiento = Movimiento(
                cuenta_id=cuenta.id,
                fecha_hora=datetime.now(),
                monto=monto,
                moneda=cuenta.moneda,
                descripcion=final_desc,
                comercio_id=comercio_id,
                categoria=final_cat,
                subcategoria=final_subcat,
                canal=final_canal,
                es_recurrente=False,
                estado="procesado",
            )
            session.add(movimiento)

            # Update account balance
            cuenta.saldo = (Decimal(str(cuenta.saldo)) + movimiento.monto).quantize(Decimal("0.01"))

            await session.commit()
            await session.refresh(movimiento)
            await session.refresh(cuenta)

            # 5. Broadcast to SSE subscribers
            payload = MovimientoResponse.model_validate(movimiento).model_dump(mode="json")
            await self.broadcaster.broadcast("movimiento", payload)
            self.total_events_emitted += 1

            return movimiento

    async def start_ticker(
        self, session_factory: async_sessionmaker[AsyncSession] | Any
    ) -> asyncio.Task:
        """Starts background ticker task running while is_running."""
        if self.is_running and self._task and not self._task.done():
            return self._task

        self.is_running = True
        self._task = asyncio.create_task(self._run_loop(session_factory))
        return self._task

    async def stop_ticker(self) -> None:
        """Stops the ticker background task gracefully."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def stop(self) -> None:
        """Synchronously request ticker termination."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run_loop(
        self, session_factory: async_sessionmaker[AsyncSession] | Any
    ) -> None:
        try:
            while self.is_running:
                delay = random.uniform(self.interval_min, self.interval_max)
                await asyncio.sleep(delay)
                if not self.is_running:
                    break
                async with session_factory() as session:
                    await self.execute_tick(session)
        except asyncio.CancelledError:
            pass
        finally:
            self.is_running = False


# Global simulation engine singleton
simulation_engine = SimulationEngine()
