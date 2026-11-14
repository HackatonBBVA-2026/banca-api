from datetime import date, datetime
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.database import Base
from src.models import (
    Cliente,
    Cuenta,
    Tarjeta,
    Comercio,
    PagoProgramado,
    Beneficiario,
    TipoCambio,
    EventoSeguridad,
    ProductoReferencial,
    Movimiento,
)
from src.seed import seed_database, ANCHOR_DATE, BASE_INITIAL_PEN_BALANCE


@pytest_asyncio.fixture
async def test_db_session_factory(tmp_path):
    db_file = tmp_path / "test_seed_banca.db"
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
    yield session_factory, test_engine
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_seed_database_entities_and_counts(test_db_session_factory):
    session_factory, _ = test_db_session_factory

    result = await seed_database(session_factory=session_factory, force=False)
    assert result["status"] == "seeded"

    async with session_factory() as session:
        # 1. Cliente
        clientes = (await session.execute(select(Cliente))).scalars().all()
        assert len(clientes) == 1
        cliente = clientes[0]
        assert cliente.nombre == "Juan Pérez"
        assert cliente.nivel == "Black Tier"
        assert cliente.perfil == "persona_dependiente"
        assert cliente.ingreso_mensual == Decimal("5000.00")
        assert cliente.dia_pago == 28

        # 2. Cuentas
        cuentas = (await session.execute(select(Cuenta))).scalars().all()
        assert len(cuentas) == 2
        cuenta_pen = next(c for c in cuentas if c.moneda == "PEN")
        cuenta_usd = next(c for c in cuentas if c.moneda == "USD")
        assert cuenta_pen.tipo == "Ahorro"
        assert cuenta_usd.tipo == "Ahorro"
        assert cuenta_usd.saldo == Decimal("850.00")

        # 3. Tarjetas
        tarjetas = (await session.execute(select(Tarjeta))).scalars().all()
        assert len(tarjetas) == 2
        debito = next(t for t in tarjetas if t.tipo == "Debito")
        credito = next(t for t in tarjetas if t.tipo == "Credito")
        assert debito.cuenta_id == cuenta_pen.id
        assert credito.cuenta_id == cuenta_pen.id
        assert credito.limite == Decimal("10000.00")

        # 4. Comercios
        comercios = (await session.execute(select(Comercio))).scalars().all()
        assert len(comercios) == 15
        categories = {c.categoria for c in comercios}
        assert "Alimentación" in categories
        assert "Transporte" in categories
        assert "Servicios" in categories
        assert "Entretenimiento" in categories
        assert "Salud" in categories
        assert any(c.si_cobra_suscripcion for c in comercios)
        assert any(not c.si_cobra_suscripcion for c in comercios)

        # 5. Pagos Programados
        pagos = (await session.execute(select(PagoProgramado))).scalars().all()
        assert len(pagos) == 5
        servicios_esperados = {"Luz", "Agua", "Internet", "Celular", "Mantenimiento"}
        servicios_obtenidos = {p.servicio.lower() for p in pagos}
        for s in ["luz", "agua", "internet", "celular", "mantenimiento"]:
            assert any(s in serv for serv in servicios_obtenidos)

        # 6. Beneficiarios
        beneficiarios = (await session.execute(select(Beneficiario))).scalars().all()
        assert len(beneficiarios) == 5
        for b in beneficiarios:
            assert b.cliente_id == cliente.id
            assert len(b.cci) == 20

        # 7. Tipo de Cambio
        tipo_cambio = (await session.execute(select(TipoCambio))).scalars().first()
        assert tipo_cambio is not None
        assert tipo_cambio.fecha == ANCHOR_DATE.date()
        assert tipo_cambio.compra == Decimal("3.7250")
        assert tipo_cambio.venta == Decimal("3.7550")

        # 8. Eventos de Seguridad
        eventos = (await session.execute(select(EventoSeguridad))).scalars().all()
        assert len(eventos) >= 3
        sospechosos = [e for e in eventos if e.es_sospechoso]
        assert len(sospechosos) == 1
        assert "Moscú" in sospechosos[0].ciudad or "Rusia" in sospechosos[0].ciudad

        # 9. Productos Referenciales
        productos = (await session.execute(select(ProductoReferencial))).scalars().all()
        assert len(productos) == 2
        prestamo = next(p for p in productos if p.tipo == "Prestamo")
        tarjeta_ref = next(p for p in productos if p.tipo == "Tarjeta")
        assert prestamo.tea == Decimal("14.50")
        assert tarjeta_ref.tcea == Decimal("28.90")


@pytest.mark.asyncio
async def test_seed_movements_integrity_and_edge_cases(test_db_session_factory):
    session_factory, _ = test_db_session_factory
    await seed_database(session_factory=session_factory, force=False)

    async with session_factory() as session:
        cuenta_pen = (
            await session.execute(select(Cuenta).where(Cuenta.moneda == "PEN"))
        ).scalar_one()

        movimientos = (
            await session.execute(
                select(Movimiento)
                .where(Movimiento.cuenta_id == cuenta_pen.id)
                .order_by(Movimiento.fecha_hora)
            )
        ).scalars().all()

        # ~300 movements
        assert 290 <= len(movimientos) <= 310

        # 1. Nómina mensual (+5000.00 en día 28)
        nominas = [
            m for m in movimientos
            if m.monto == Decimal("5000.00") and m.fecha_hora.day == 28 and "Nómina" in m.descripcion
        ]
        assert len(nominas) >= 5

        # 2. Balance accounting integrity
        base_initial = BASE_INITIAL_PEN_BALANCE
        processed_sum = sum(
            m.monto for m in movimientos if m.estado == "procesado"
        )
        assert cuenta_pen.saldo == base_initial + processed_sum

        # 3. Deliberate Case 1: Cobro duplicado (same comercio, same amount, same category, 20s difference)
        duplicate_pairs = []
        for i in range(len(movimientos) - 1):
            m1 = movimientos[i]
            m2 = movimientos[i + 1]
            if (
                m1.comercio_id is not None
                and m1.comercio_id == m2.comercio_id
                and m1.monto == m2.monto
                and m1.categoria == m2.categoria
                and abs((m2.fecha_hora - m1.fecha_hora).total_seconds()) == 20
            ):
                duplicate_pairs.append((m1, m2))
        assert len(duplicate_pairs) >= 1, "Deliberate duplicate charge pair must exist"

        # 4. Deliberate Case 2: Movimiento revertido
        revertidos = [m for m in movimientos if m.estado == "revertido"]
        assert len(revertidos) >= 1, "Deliberate reversed movement must exist"
        for rev in revertidos:
            assert rev.monto < 0

        # 5. Deliberate Case 3: Gasto atípico (~2,500.00 PEN)
        atipicos = [m for m in movimientos if m.monto == Decimal("-2500.00")]
        assert len(atipicos) == 1, "Deliberate anomalous purchase must exist"

        # 6. Recurrentes
        recurrentes = [m for m in movimientos if m.es_recurrente]
        assert len(recurrentes) >= 20


@pytest.mark.asyncio
async def test_seed_database_idempotency_and_force(test_db_session_factory):
    session_factory, _ = test_db_session_factory

    # First run
    res1 = await seed_database(session_factory=session_factory, force=False)
    assert res1["status"] == "seeded"

    async with session_factory() as session:
        client_count_1 = await session.scalar(select(func.count(Cliente.id)))
        account_count_1 = await session.scalar(select(func.count(Cuenta.id)))
        mov_count_1 = await session.scalar(select(func.count(Movimiento.id)))

    # Second run with force=False -> skipped
    res2 = await seed_database(session_factory=session_factory, force=False)
    assert res2["status"] == "skipped"

    async with session_factory() as session:
        client_count_2 = await session.scalar(select(func.count(Cliente.id)))
        account_count_2 = await session.scalar(select(func.count(Cuenta.id)))
        mov_count_2 = await session.scalar(select(func.count(Movimiento.id)))

    assert client_count_1 == client_count_2
    assert account_count_1 == account_count_2
    assert mov_count_1 == mov_count_2

    # Third run with force=True -> reseeded cleanly
    res3 = await seed_database(session_factory=session_factory, force=True)
    assert res3["status"] == "seeded"

    async with session_factory() as session:
        client_count_3 = await session.scalar(select(func.count(Cliente.id)))
        account_count_3 = await session.scalar(select(func.count(Cuenta.id)))
        mov_count_3 = await session.scalar(select(func.count(Movimiento.id)))

    assert client_count_1 == client_count_3
    assert account_count_1 == account_count_3
    assert mov_count_1 == mov_count_3


def test_seed_cli_execution(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    db_path = tmp_path / "cli_seed.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    res = subprocess.run(
        [sys.executable, "-m", "src.seed", "--force"],
        cwd="/home/rylai/Documents/hackathonbbva/banca-api",
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert "Seed completed: {'status': 'seeded'" in res.stdout
    assert res.returncode == 0

