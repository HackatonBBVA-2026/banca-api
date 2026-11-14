import asyncio
from datetime import datetime
from decimal import Decimal
import json
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.broadcaster import broadcaster
from src.database import Base, get_db
from src.models import Cliente, Cuenta, Movimiento, TipoCambio
from src.schemas import TickOverrideRequest
from src.seed import seed_database
from src.simulation import simulation_engine


@pytest_asyncio.fixture
async def test_api_db(tmp_path):
    """Creates an isolated test database, runs seed, and provides a session factory."""
    db_file = tmp_path / "test_api.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    test_engine = create_async_engine(test_db_url)

    @event.listens_for(test_engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    session_factory = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )

    # Seed the isolated DB deterministically
    await seed_database(session_factory, force=True)

    yield session_factory, test_engine

    await test_engine.dispose()


@pytest_asyncio.fixture
async def client(test_api_db):
    """FastAPI AsyncClient configured with test DB dependency override."""
    # Import app inside fixture or module
    from src.main import app

    session_factory, _ = test_api_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    broadcaster.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()
    broadcaster.clear()


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"
    assert isinstance(data["simulation_active"], bool)


@pytest.mark.asyncio
async def test_cors_headers(client):
    response = await client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in ["*", "http://localhost:3000"]


@pytest.mark.asyncio
async def test_get_cliente_success(client):
    response = await client.get("/cliente")
    assert response.status_code == 200
    data = response.json()
    assert data["nombre"] == "Juan Pérez"
    assert data["nivel"] == "Black Tier"
    assert "ingreso_mensual" in data


@pytest.mark.asyncio
async def test_get_cliente_not_found(test_api_db):
    from src.main import app
    session_factory, _ = test_api_db

    # Delete all data cleanly
    async with session_factory() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        res = await ac.get("/cliente")
        assert res.status_code == 404
        assert res.json()["detail"] == "Cliente no encontrado"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_cuentas(client):
    response = await client.get("/cuentas")
    assert response.status_code == 200
    cuentas = response.json()
    assert isinstance(cuentas, list)
    assert len(cuentas) == 2  # PEN and USD accounts from seed
    monedas = {c["moneda"] for c in cuentas}
    assert "PEN" in monedas
    assert "USD" in monedas


@pytest.mark.asyncio
async def test_get_cuenta_by_id(client):
    response = await client.get("/cuentas/1")
    assert response.status_code == 200
    cuenta = response.json()
    assert cuenta["id"] == 1
    assert "saldo" in cuenta
    assert "numero_enmascarado" in cuenta


@pytest.mark.asyncio
async def test_get_cuenta_not_found(client):
    response = await client.get("/cuentas/9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Cuenta no encontrada"


@pytest.mark.asyncio
async def test_get_cuentas_movimientos_pagination(client):
    # Default page=1, page_size=20
    response = await client.get("/cuentas/1/movimientos")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data

    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) <= 20
    assert data["total"] > 20
    assert data["total_pages"] >= 2

    # Custom page_size=5, page=2
    response2 = await client.get("/cuentas/1/movimientos?page=2&page_size=5")
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["page"] == 2
    assert data2["page_size"] == 5
    assert len(data2["items"]) == 5
    assert data2["items"] != data["items"][:5]


@pytest.mark.asyncio
async def test_get_cuentas_movimientos_filtering_tipo(client):
    # Filter tipo=ingreso (positive monto)
    res_ingreso = await client.get("/cuentas/1/movimientos?tipo=ingreso")
    assert res_ingreso.status_code == 200
    data_ingreso = res_ingreso.json()
    assert len(data_ingreso["items"]) > 0
    for mov in data_ingreso["items"]:
        assert Decimal(str(mov["monto"])) > 0

    # Filter tipo=gasto (negative monto)
    res_gasto = await client.get("/cuentas/1/movimientos?tipo=gasto")
    assert res_gasto.status_code == 200
    data_gasto = res_gasto.json()
    assert len(data_gasto["items"]) > 0
    for mov in data_gasto["items"]:
        assert Decimal(str(mov["monto"])) < 0


@pytest.mark.asyncio
async def test_get_cuentas_movimientos_filtering_categoria(client):
    res = await client.get("/cuentas/1/movimientos?categoria=Alimentación")
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) > 0
    for mov in data["items"]:
        assert mov["categoria"] == "Alimentación"


@pytest.mark.asyncio
async def test_get_cuentas_movimientos_filtering_dates(client):
    desde = "2026-10-01T00:00:00"
    hasta = "2026-11-01T23:59:59"
    res = await client.get(f"/cuentas/1/movimientos?desde={desde}&hasta={hasta}")
    assert res.status_code == 200
    data = res.json()
    for mov in data["items"]:
        dt = datetime.fromisoformat(mov["fecha_hora"])
        assert datetime.fromisoformat(desde) <= dt <= datetime.fromisoformat(hasta)


@pytest.mark.asyncio
async def test_get_cuentas_movimientos_account_not_found(client):
    res = await client.get("/cuentas/9999/movimientos")
    assert res.status_code == 404
    assert res.json()["detail"] == "Cuenta no encontrada"


@pytest.mark.asyncio
async def test_get_tarjetas(client):
    response = await client.get("/tarjetas")
    assert response.status_code == 200
    cards = response.json()
    assert isinstance(cards, list)
    assert len(cards) >= 1
    assert "ultimos_4_digitos" in cards[0]


@pytest.mark.asyncio
async def test_get_comercios(client):
    response = await client.get("/comercios")
    assert response.status_code == 200
    comercios = response.json()
    assert isinstance(comercios, list)
    assert len(comercios) >= 5
    assert "nombre_ficticio" in comercios[0]


@pytest.mark.asyncio
async def test_get_pagos_programados(client):
    response = await client.get("/pagos-programados")
    assert response.status_code == 200
    pagos = response.json()
    assert isinstance(pagos, list)
    assert len(pagos) >= 1
    assert "servicio" in pagos[0]


@pytest.mark.asyncio
async def test_get_beneficiarios(client):
    response = await client.get("/beneficiarios")
    assert response.status_code == 200
    beneficiarios = response.json()
    assert isinstance(beneficiarios, list)
    assert len(beneficiarios) >= 1
    assert "alias" in beneficiarios[0]


@pytest.mark.asyncio
async def test_get_tipo_cambio_latest(client):
    response = await client.get("/tipo-cambio")
    assert response.status_code == 200
    tc = response.json()
    assert "compra" in tc
    assert "venta" in tc
    assert "fecha" in tc


@pytest.mark.asyncio
async def test_get_tipo_cambio_not_found(test_api_db):
    from src.main import app
    session_factory, _ = test_api_db

    async with session_factory() as session:
        await session.execute(TipoCambio.__table__.delete())
        await session.commit()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        res = await ac.get("/tipo-cambio")
        assert res.status_code == 404
        assert res.json()["detail"] == "Tipo de cambio no encontrado"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_eventos_seguridad(client):
    response = await client.get("/eventos-seguridad")
    assert response.status_code == 200
    eventos = response.json()
    assert isinstance(eventos, list)
    assert len(eventos) >= 1
    assert "tipo" in eventos[0]
    assert "es_sospechoso" in eventos[0]


@pytest.mark.asyncio
async def test_get_productos_referenciales(client):
    response = await client.get("/productos-referenciales")
    assert response.status_code == 200
    prods = response.json()
    assert isinstance(prods, list)
    assert len(prods) >= 1
    assert "tea" in prods[0]


@pytest.mark.asyncio
async def test_post_simulacion_tick_without_override(client, test_api_db):
    session_factory, _ = test_api_db
    # Get previous balance of cuenta 1
    async with session_factory() as session:
        c1 = await session.get(Cuenta, 1)
        prev_saldo = c1.saldo

    response = await client.post("/simulacion/tick", json=None)
    assert response.status_code == 201
    mov = response.json()
    assert mov["id"] > 0
    assert "monto" in mov
    assert "categoria" in mov

    # Verify balance was updated
    async with session_factory() as session:
        c1_updated = await session.get(Cuenta, mov["cuenta_id"])
        assert c1_updated.saldo != prev_saldo or mov["cuenta_id"] != 1


@pytest.mark.asyncio
async def test_post_simulacion_tick_with_override(client, test_api_db):
    override_data = {
        "cuenta_id": 1,
        "monto": "123.45",
        "categoria": "TestCategoria",
        "subcategoria": "TestSub",
        "descripcion": "Override test transaction",
        "canal": "App Móvil",
    }
    response = await client.post("/simulacion/tick", json=override_data)
    assert response.status_code == 201
    mov = response.json()
    assert mov["cuenta_id"] == 1
    assert Decimal(str(mov["monto"])) == Decimal("123.45")
    assert mov["categoria"] == "TestCategoria"
    assert mov["subcategoria"] == "TestSub"
    assert mov["descripcion"] == "Override test transaction"
    assert mov["canal"] == "App Móvil"


@pytest.mark.asyncio
async def test_post_simulacion_tick_invalid_account(client):
    override_data = {
        "cuenta_id": 99999,
        "monto": "10.00",
    }
    response = await client.post("/simulacion/tick", json=override_data)
    assert response.status_code in [400, 404]


@pytest.mark.asyncio
async def test_get_simulacion_status(client):
    response = await client.get("/simulacion/status")
    assert response.status_code == 200
    status = response.json()
    assert "simulation_active" in status
    assert "interval_min" in status
    assert "interval_max" in status
    assert "active_sse_subscribers" in status
    assert "total_events_emitted" in status


@pytest.mark.asyncio
async def test_movimientos_sse_stream(test_api_db):
    from src.main import app

    session_factory, _ = test_api_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    broadcaster.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # Check subscriber count before
        assert broadcaster.subscriber_count == 0

        # Background task triggers a tick once subscriber registers
        async def trigger_delayed_tick():
            while broadcaster.subscriber_count == 0:
                await asyncio.sleep(0.01)
            async with session_factory() as session:
                override = TickOverrideRequest(
                    cuenta_id=1,
                    monto=Decimal("77.77"),
                    descripcion="SSE Test Event",
                )
                await simulation_engine.execute_tick(session, override)

        tick_task = asyncio.create_task(trigger_delayed_tick())

        res = await ac.get("/movimientos/stream?limit=1")
        await tick_task

        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        assert "event: movimiento" in res.text
        assert "SSE Test Event" in res.text

        # After stream ends, subscriber count must be 0
        assert broadcaster.subscriber_count == 0

    app.dependency_overrides.clear()
    broadcaster.clear()


@pytest.mark.asyncio
async def test_movimientos_sse_stream_heartbeat_ping():
    from src.main import app

    broadcaster.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # Request with small ping_timeout and limit=1 to receive the ping heartbeat frame
        res = await ac.get("/movimientos/stream?limit=1&ping_timeout=0.05")
        assert res.status_code == 200
        assert ": ping\n\n" in res.text
        assert broadcaster.subscriber_count == 0

    broadcaster.clear()


@pytest.mark.asyncio
async def test_lifespan_lifecycle(monkeypatch):
    from src.main import app, lifespan
    import src.main as main_module

    # Mock start_ticker and stop_ticker to verify lifespan triggers them
    started = []
    stopped = []

    async def mock_start(session_factory):
        started.append(session_factory)

    async def mock_stop():
        stopped.append(True)

    monkeypatch.setattr(simulation_engine, "start_ticker", mock_start)
    monkeypatch.setattr(simulation_engine, "stop_ticker", mock_stop)

    # Also mock seed_database so it doesn't seed real DB
    seeded = []
    async def mock_seed(session_factory, force=False):
        seeded.append(force)

    monkeypatch.setattr(main_module, "seed_database", mock_seed)

    async with lifespan(app):
        assert len(seeded) == 1
        assert len(started) == 1

    assert len(stopped) == 1

