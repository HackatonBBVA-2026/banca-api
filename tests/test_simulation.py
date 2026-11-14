import asyncio
from datetime import datetime
from decimal import Decimal
import json
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.database import Base
from src.models import Cliente, Cuenta, Movimiento
from src.schemas import TickOverrideRequest
from src.simulation import SimulationEngine, simulation_engine
from src.broadcaster import Broadcaster


@pytest_asyncio.fixture
async def test_sim_db(tmp_path):
    db_file = tmp_path / "test_sim.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    test_engine = create_async_engine(test_db_url)

    from sqlalchemy import event

    @event.listens_for(test_engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    # Seed minimal client and account
    async with session_factory() as session:
        cliente = Cliente(
            nombre="Juan Perez",
            nivel="VIP",
            cliente_desde=datetime.now().date(),
            ingreso_mensual=Decimal("5000.00"),
            dia_pago=15,
            perfil="ahorrador",
        )
        session.add(cliente)
        await session.flush()

        cuenta = Cuenta(
            cliente_id=cliente.id,
            tipo="ahorros",
            moneda="PEN",
            numero_enmascarado="****1234",
            cci="00219400000000123456",
            saldo=Decimal("2000.00"),
        )
        session.add(cuenta)
        await session.commit()

    yield session_factory, test_engine
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_simulation_engine_initialization():
    engine = SimulationEngine()
    assert engine.is_running is False
    assert engine.total_events_emitted == 0
    assert engine.interval_min == 10
    assert engine.interval_max == 30
    assert isinstance(simulation_engine, SimulationEngine)


@pytest.mark.asyncio
async def test_execute_tick_default_random(test_sim_db):
    session_factory, _ = test_sim_db
    custom_broadcaster = Broadcaster()
    engine = SimulationEngine(broadcaster=custom_broadcaster)

    async with session_factory() as session:
        stmt = select(Cuenta).where(Cuenta.id == 1)
        res = await session.execute(stmt)
        cuenta = res.scalar_one()
        initial_saldo = cuenta.saldo

        mov = await engine.execute_tick(session)

        assert isinstance(mov, Movimiento)
        assert mov.id is not None
        assert isinstance(mov.monto, Decimal)
        assert mov.cuenta_id == 1
        assert engine.total_events_emitted == 1

        # Check account balance is updated in DB
        res_after = await session.execute(select(Cuenta).where(Cuenta.id == 1))
        cuenta_after = res_after.scalar_one()
        assert cuenta_after.saldo == initial_saldo + mov.monto


@pytest.mark.asyncio
async def test_execute_tick_with_override_inputs(test_sim_db):
    session_factory, _ = test_sim_db
    custom_broadcaster = Broadcaster()
    engine = SimulationEngine(broadcaster=custom_broadcaster)

    override = TickOverrideRequest(
        cuenta_id=1,
        monto=Decimal("-45.50"),
        categoria="Alimentación",
        subcategoria="Restaurantes",
        descripcion="Cena Gourmet",
        canal="POS",
    )

    async with session_factory() as session:
        res = await session.execute(select(Cuenta).where(Cuenta.id == 1))
        initial_saldo = res.scalar_one().saldo

        mov = await engine.execute_tick(session, override=override)

        assert mov.monto == Decimal("-45.50")
        assert mov.categoria == "Alimentación"
        assert mov.subcategoria == "Restaurantes"
        assert mov.descripcion == "Cena Gourmet"
        assert mov.canal == "POS"

        res_after = await session.execute(select(Cuenta).where(Cuenta.id == 1))
        cuenta_after = res_after.scalar_one()
        assert cuenta_after.saldo == initial_saldo + Decimal("-45.50")


@pytest.mark.asyncio
async def test_execute_tick_broadcasts_sse_event(test_sim_db):
    session_factory, _ = test_sim_db
    custom_broadcaster = Broadcaster()
    engine = SimulationEngine(broadcaster=custom_broadcaster)

    # Subscribe to broadcaster
    queue = await custom_broadcaster.subscribe()

    override = TickOverrideRequest(
        cuenta_id=1,
        monto=Decimal("120.00"),
        categoria="Ingresos",
        subcategoria="Transferencia",
        descripcion="Transferencia recibida",
    )

    async with session_factory() as session:
        mov = await engine.execute_tick(session, override=override)

        # Subscriber must have received the SSE event
        msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert msg.startswith("event: movimiento\ndata: ")
        assert msg.endswith("\n\n")

        # Extract data payload JSON
        data_json_str = msg.split("data: ", 1)[1].rstrip("\n")
        data = json.loads(data_json_str)

        assert data["id"] == mov.id
        assert data["cuenta_id"] == 1
        assert Decimal(str(data["monto"])) == Decimal("120.00")
        assert data["categoria"] == "Ingresos"


@pytest.mark.asyncio
async def test_ticker_start_and_stop_lifecycle(test_sim_db):
    session_factory, _ = test_sim_db
    custom_broadcaster = Broadcaster()
    # Fast ticker for test (0.02s - 0.05s)
    engine = SimulationEngine(
        interval_min=1,
        interval_max=2,
        broadcaster=custom_broadcaster,
    )
    # Lower intervals for testing fast execution
    engine.interval_min = 0.02
    engine.interval_max = 0.05

    task = await engine.start_ticker(session_factory)
    assert engine.is_running is True
    assert not task.done()

    # Wait for ticks to execute
    await asyncio.sleep(0.25)

    await engine.stop_ticker()
    assert engine.is_running is False
    assert engine.total_events_emitted >= 2


@pytest.mark.asyncio
async def test_execute_tick_account_not_found(test_sim_db):
    session_factory, _ = test_sim_db
    engine = SimulationEngine()
    override = TickOverrideRequest(cuenta_id=99999, monto=Decimal("-10.00"))

    async with session_factory() as session:
        with pytest.raises(ValueError, match="Cuenta with id 99999 not found"):
            await engine.execute_tick(session, override=override)


@pytest.mark.asyncio
async def test_execute_tick_empty_database(tmp_path):
    db_file = tmp_path / "empty_test.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    engine_db = create_async_engine(test_db_url)
    async with engine_db.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine_db, expire_on_commit=False, class_=AsyncSession
    )

    engine = SimulationEngine()
    async with session_factory() as session:
        with pytest.raises(ValueError, match="No accounts available"):
            await engine.execute_tick(session)
    await engine_db.dispose()


@pytest.mark.asyncio
async def test_simulation_engine_get_status():
    b = Broadcaster()
    await b.subscribe()
    engine = SimulationEngine(interval_min=5, interval_max=15, broadcaster=b)
    engine.total_events_emitted = 42

    status = engine.get_status()
    assert status.simulation_active is False
    assert status.interval_min == 5
    assert status.interval_max == 15
    assert status.active_sse_subscribers == 1
    assert status.total_events_emitted == 42


@pytest.mark.asyncio
async def test_concurrent_ticks_serial_integrity(test_sim_db):
    session_factory, _ = test_sim_db
    custom_broadcaster = Broadcaster()
    engine = SimulationEngine(broadcaster=custom_broadcaster)

    # Run 5 concurrent ticks with deterministic amounts
    async def run_tick(amount: Decimal):
        async with session_factory() as s:
            await engine.execute_tick(
                s,
                override=TickOverrideRequest(
                    cuenta_id=1,
                    monto=amount,
                    categoria="Test",
                    subcategoria="SerialLock",
                    descripcion="Concurrent Lock Test",
                    canal="API",
                ),
            )

    async with session_factory() as session:
        res = await session.execute(select(Cuenta).where(Cuenta.id == 1))
        initial_balance = res.scalar_one().saldo

    tasks = [
        run_tick(Decimal("-10.00")),
        run_tick(Decimal("-20.00")),
        run_tick(Decimal("50.00")),
        run_tick(Decimal("-5.00")),
        run_tick(Decimal("15.00")),
    ]
    await asyncio.gather(*tasks)

    async with session_factory() as session:
        res = await session.execute(select(Cuenta).where(Cuenta.id == 1))
        final_balance = res.scalar_one().saldo
        expected_balance = initial_balance + Decimal("30.00")
        assert final_balance == expected_balance
        assert engine.total_events_emitted == 5
