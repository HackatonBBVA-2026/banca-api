import asyncio
from datetime import date, datetime
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.config import Settings, get_settings
from src.database import Base, engine, get_db, db_write_lock
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


def test_config_defaults():
    settings = Settings()
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./banca.db"
    assert settings.SEED_VALUE == 42
    assert settings.SIMULATION_ENABLED is True
    assert settings.SIMULATION_INTERVAL_MIN == 10
    assert settings.SIMULATION_INTERVAL_MAX == 30


def test_db_write_lock():
    assert isinstance(db_write_lock, asyncio.Lock)


@pytest.mark.asyncio
async def test_get_db_generator():
    gen = get_db()
    session = await anext(gen)
    assert isinstance(session, AsyncSession)
    await gen.aclose()


@pytest_asyncio.fixture
async def test_db_session(tmp_path):
    db_file = tmp_path / "test_banca.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    test_engine = create_async_engine(test_db_url)

    # Apply SQLite PRAGMAs via connect event
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

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session, test_engine

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_pragmas_and_wal(test_db_session):
    session, test_engine = test_db_session
    async with test_engine.connect() as conn:
        res_wal = await conn.execute(text("PRAGMA journal_mode"))
        assert res_wal.scalar().lower() == "wal"

        res_fk = await conn.execute(text("PRAGMA foreign_keys"))
        assert res_fk.scalar() == 1

        res_busy = await conn.execute(text("PRAGMA busy_timeout"))
        assert res_busy.scalar() == 5000

        res_sync = await conn.execute(text("PRAGMA synchronous"))
        assert res_sync.scalar() == 1  # NORMAL is 1 in SQLite


@pytest.mark.asyncio
async def test_all_tables_created(test_db_session):
    _, test_engine = test_db_session
    expected_tables = {
        "clientes",
        "cuentas",
        "tarjetas",
        "comercios",
        "pagos_programados",
        "beneficiarios",
        "tipo_cambio",
        "eventos_seguridad",
        "productos_referenciales",
        "movimientos",
    }
    assert expected_tables.issubset(set(Base.metadata.tables.keys()))


@pytest.mark.asyncio
async def test_insert_and_relations(test_db_session):
    session, _ = test_db_session

    # 1. Cliente
    cliente = Cliente(
        nombre="Carlos Test",
        nivel="Black Tier",
        cliente_desde=date(2023, 1, 15),
        ingreso_mensual=Decimal("7500.50"),
        dia_pago=28,
        perfil="profesional_independiente",
    )
    session.add(cliente)
    await session.commit()
    await session.refresh(cliente)
    assert cliente.id is not None
    assert cliente.ingreso_mensual == Decimal("7500.50")

    # 2. Cuenta
    cuenta = Cuenta(
        cliente_id=cliente.id,
        tipo="ahorro",
        moneda="PEN",
        numero_enmascarado="****1234",
        cci="00219400000000001234",
        saldo=Decimal("3500.00"),
    )
    session.add(cuenta)
    await session.commit()
    await session.refresh(cuenta)
    assert cuenta.id is not None
    assert cuenta.saldo == Decimal("3500.00")

    # 3. Tarjeta
    tarjeta = Tarjeta(
        cuenta_id=cuenta.id,
        tipo="debito",
        ultimos_4_digitos="1234",
        vencimiento="05/28",
        limite=Decimal("5000.00"),
        fecha_corte=15,
        fecha_pago=5,
    )
    session.add(tarjeta)

    # 4. Comercio
    comercio = Comercio(
        nombre_ficticio="Supermercado Metro Norte",
        categoria="Alimentación",
        codigo_rubro_mcc="5411",
        si_cobra_suscripcion=False,
    )
    session.add(comercio)
    await session.commit()
    await session.refresh(comercio)

    # 5. PagoProgramado
    pago = PagoProgramado(
        cuenta_id=cuenta.id,
        servicio="Luz del Sur",
        monto_estimado=Decimal("120.50"),
        dia_vencimiento=20,
    )
    session.add(pago)

    # 6. Beneficiario
    beneficiario = Beneficiario(
        cliente_id=cliente.id,
        alias="Hermana",
        banco="Banco de Crédito",
        cci="00219100000000009999",
    )
    session.add(beneficiario)

    # 7. TipoCambio
    tc = TipoCambio(
        fecha=date(2026, 11, 14),
        compra=Decimal("3.7500"),
        venta=Decimal("3.7850"),
    )
    session.add(tc)

    # 8. EventoSeguridad
    evento = EventoSeguridad(
        cliente_id=cliente.id,
        tipo="login",
        dispositivo="iPhone 15",
        ciudad="Lima",
        fecha_hora=datetime(2026, 11, 14, 10, 30, 0),
        es_sospechoso=False,
    )
    session.add(evento)

    # 9. ProductoReferencial
    producto = ProductoReferencial(
        tipo="tarjeta_credito",
        nombre="Tarjeta Oro",
        tea=Decimal("35.50"),
        tcea=Decimal("42.10"),
        membresia=Decimal("150.00"),
    )
    session.add(producto)

    # 10. Movimiento
    movimiento = Movimiento(
        cuenta_id=cuenta.id,
        fecha_hora=datetime(2026, 11, 14, 12, 0, 0),
        monto=Decimal("-45.20"),
        moneda="PEN",
        descripcion="Compra almuerzo",
        comercio_id=comercio.id,
        categoria="Alimentación",
        subcategoria="Restaurantes",
        canal="POS",
        es_recurrente=False,
        estado="procesado",
    )
    session.add(movimiento)
    await session.commit()
    await session.refresh(movimiento)

    assert movimiento.id is not None
    assert movimiento.monto == Decimal("-45.20")
    assert movimiento.comercio_id == comercio.id


@pytest.mark.asyncio
async def test_foreign_key_enforcement(test_db_session):
    session, _ = test_db_session
    # Non-existent cliente_id 999999
    bad_cuenta = Cuenta(
        cliente_id=999999,
        tipo="ahorro",
        moneda="PEN",
        numero_enmascarado="****9999",
        cci="00299999999999999999",
        saldo=Decimal("100.00"),
    )
    session.add(bad_cuenta)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
