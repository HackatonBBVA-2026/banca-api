import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.broadcaster import broadcaster
from src.config import get_settings
from src.database import async_session, get_db
from src.models import (
    Beneficiario,
    Cliente,
    Comercio,
    Cuenta,
    EventoSeguridad,
    Movimiento,
    PagoProgramado,
    ProductoReferencial,
    Tarjeta,
    TipoCambio,
)
from src.schemas import (
    BeneficiarioResponse,
    ClienteResponse,
    ComercioResponse,
    CuentaResponse,
    EventoSeguridadResponse,
    HealthResponse,
    MovimientoResponse,
    PaginatedMovimientosResponse,
    PagoProgramadoResponse,
    ProductoReferencialResponse,
    SimulacionStatusResponse,
    TarjetaResponse,
    TickOverrideRequest,
    TipoCambioResponse,
)
from src.seed import seed_database
from src.simulation import simulation_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for database initialization and simulation ticker."""
    settings = get_settings()
    # 1. Startup: auto-seed DB if empty (force=False)
    await seed_database(async_session, force=False)
    # 2. Start simulation ticker if enabled
    if settings.SIMULATION_ENABLED:
        await simulation_engine.start_ticker(async_session)

    yield

    # 3. Shutdown: gracefully stop ticker
    await simulation_engine.stop_ticker()


app = FastAPI(
    title="Banca API BBVA",
    description="Mock Banking API for hackathonbbva with real-time SSE simulation",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health(db: AsyncSession = Depends(get_db)):
    """Health check endpoint checking DB connectivity and simulation status."""
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="ok",
        db=db_status,
        simulation_active=simulation_engine.simulation_active,
    )


@app.get("/cliente", response_model=ClienteResponse, tags=["Clientes"])
async def get_cliente(db: AsyncSession = Depends(get_db)):
    """Get the active client profile."""
    stmt = select(Cliente).limit(1)
    res = await db.execute(stmt)
    cliente = res.scalar_one_or_none()
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado"
        )
    return cliente


@app.get("/cuentas", response_model=List[CuentaResponse], tags=["Cuentas"])
async def get_cuentas(db: AsyncSession = Depends(get_db)):
    """Get all accounts of the active client."""
    stmt = select(Cuenta).order_by(Cuenta.id)
    res = await db.execute(stmt)
    return res.scalars().all()


@app.get("/cuentas/{cuenta_id}", response_model=CuentaResponse, tags=["Cuentas"])
async def get_cuenta(cuenta_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific account by id."""
    cuenta = await db.get(Cuenta, cuenta_id)
    if cuenta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada"
        )
    return cuenta


@app.get(
    "/cuentas/{cuenta_id}/movimientos",
    response_model=PaginatedMovimientosResponse,
    tags=["Movimientos"],
)
async def get_cuenta_movimientos(
    cuenta_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    tipo: Optional[str] = Query(None, description="Filter: 'ingreso' or 'gasto'"),
    categoria: Optional[str] = Query(None, description="Category filter"),
    desde: Optional[datetime] = Query(None, description="Start datetime filter"),
    hasta: Optional[datetime] = Query(None, description="End datetime filter"),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated movements for an account with optional filters."""
    # Ensure account exists
    cuenta = await db.get(Cuenta, cuenta_id)
    if cuenta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada"
        )

    filters = [Movimiento.cuenta_id == cuenta_id]

    if tipo is not None:
        if tipo == "ingreso":
            filters.append(Movimiento.monto > 0)
        elif tipo == "gasto":
            filters.append(Movimiento.monto < 0)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parámetro 'tipo' debe ser 'ingreso' o 'gasto'",
            )

    if categoria:
        filters.append(Movimiento.categoria == categoria)

    if desde is not None:
        filters.append(Movimiento.fecha_hora >= desde)

    if hasta is not None:
        filters.append(Movimiento.fecha_hora <= hasta)

    # Count total matching items
    count_stmt = select(func.count(Movimiento.id)).where(*filters)
    total_res = await db.execute(count_stmt)
    total = total_res.scalar_one()

    # Query items with pagination and ordering
    offset = (page - 1) * page_size
    stmt = (
        select(Movimiento)
        .where(*filters)
        .order_by(Movimiento.fecha_hora.desc(), Movimiento.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    items_res = await db.execute(stmt)
    items = items_res.scalars().all()

    return PaginatedMovimientosResponse(
        items=[MovimientoResponse.model_validate(m) for m in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/tarjetas", response_model=List[TarjetaResponse], tags=["Tarjetas"])
async def get_tarjetas(db: AsyncSession = Depends(get_db)):
    """Get all cards."""
    stmt = select(Tarjeta).order_by(Tarjeta.id)
    res = await db.execute(stmt)
    return res.scalars().all()


@app.get("/comercios", response_model=List[ComercioResponse], tags=["Comercios"])
async def get_comercios(db: AsyncSession = Depends(get_db)):
    """Get all registered merchants."""
    stmt = select(Comercio).order_by(Comercio.id)
    res = await db.execute(stmt)
    return res.scalars().all()


@app.get(
    "/pagos-programados",
    response_model=List[PagoProgramadoResponse],
    tags=["Pagos Programados"],
)
async def get_pagos_programados(db: AsyncSession = Depends(get_db)):
    """Get all scheduled utility payments."""
    stmt = select(PagoProgramado).order_by(PagoProgramado.id)
    res = await db.execute(stmt)
    return res.scalars().all()


@app.get(
    "/beneficiarios",
    response_model=List[BeneficiarioResponse],
    tags=["Beneficiarios"],
)
async def get_beneficiarios(db: AsyncSession = Depends(get_db)):
    """Get frequent beneficiaries."""
    stmt = select(Beneficiario).order_by(Beneficiario.id)
    res = await db.execute(stmt)
    return res.scalars().all()


@app.get("/tipo-cambio", response_model=TipoCambioResponse, tags=["Tipo de Cambio"])
async def get_tipo_cambio(db: AsyncSession = Depends(get_db)):
    """Get most recent exchange rate."""
    stmt = select(TipoCambio).order_by(TipoCambio.fecha.desc()).limit(1)
    res = await db.execute(stmt)
    tc = res.scalar_one_or_none()
    if tc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tipo de cambio no encontrado",
        )
    return tc


@app.get(
    "/eventos-seguridad",
    response_model=List[EventoSeguridadResponse],
    tags=["Seguridad"],
)
async def get_eventos_seguridad(db: AsyncSession = Depends(get_db)):
    """Get security audit events."""
    stmt = select(EventoSeguridad).order_by(EventoSeguridad.fecha_hora.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


@app.get(
    "/productos-referenciales",
    response_model=List[ProductoReferencialResponse],
    tags=["Productos Referenciales"],
)
async def get_productos_referenciales(db: AsyncSession = Depends(get_db)):
    """Get reference loan/card rates and products."""
    stmt = select(ProductoReferencial).order_by(ProductoReferencial.id)
    res = await db.execute(stmt)
    return res.scalars().all()


@app.get("/movimientos/stream", tags=["Simulación & Stream"])
async def stream_movimientos(
    limit: Optional[int] = Query(
        None, description="Optional maximum number of events to stream before closing"
    ),
    ping_timeout: float = Query(
        15.0, description="Heartbeat ping timeout in seconds"
    ),
):
    """SSE endpoint streaming live banking movements in real-time."""
    async def event_generator():
        queue = await broadcaster.subscribe()
        count = 0
        try:
            while limit is None or count < limit:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=ping_timeout)
                    yield event_data
                    count += 1
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    count += 1
        except asyncio.CancelledError:
            pass
        finally:
            await broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post(
    "/simulacion/tick",
    response_model=MovimientoResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Simulación & Stream"],
)
async def trigger_simulacion_tick(
    override: Optional[TickOverrideRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Triggers an instantaneous simulated movement with optional override parameters."""
    try:
        movimiento = await simulation_engine.execute_tick(db, override)
        return movimiento
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.get(
    "/simulacion/status",
    response_model=SimulacionStatusResponse,
    tags=["Simulación & Stream"],
)
async def get_simulacion_status():
    """Get simulation status and metrics."""
    return simulation_engine.get_status()
