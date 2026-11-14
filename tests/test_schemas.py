import math
from datetime import date, datetime
from decimal import Decimal
import pytest
from pydantic import ValidationError

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
    MovimientoResponse,
    PaginatedMovimientosResponse,
    PagoProgramadoResponse,
    ProductoReferencialResponse,
    SimulacionStatusResponse,
    TarjetaResponse,
    TickOverrideRequest,
    TipoCambioResponse,
)


def test_cliente_response_from_orm_and_dict():
    # From dict
    data = {
        "id": 1,
        "nombre": "Ana Pérez",
        "nivel": "Black Tier",
        "cliente_desde": date(2020, 1, 15),
        "ingreso_mensual": Decimal("5000.00"),
        "dia_pago": 28,
        "perfil": "Ahorrador Moderado",
    }
    schema = ClienteResponse.model_validate(data)
    assert schema.id == 1
    assert schema.nombre == "Ana Pérez"
    assert schema.ingreso_mensual == Decimal("5000.00")

    # From ORM instance
    orm = Cliente(**data)
    schema_orm = ClienteResponse.model_validate(orm)
    assert schema_orm.id == 1
    assert schema_orm.nombre == "Ana Pérez"
    assert schema_orm.cliente_desde == date(2020, 1, 15)


def test_cuenta_response_from_orm():
    orm = Cuenta(
        id=1,
        cliente_id=10,
        tipo="ahorro",
        moneda="PEN",
        numero_enmascarado="**** **** **** 1234",
        cci="00219400000000000001",
        saldo=Decimal("3500.50"),
    )
    schema = CuentaResponse.model_validate(orm)
    assert schema.id == 1
    assert schema.cliente_id == 10
    assert schema.moneda == "PEN"
    assert schema.saldo == Decimal("3500.50")


def test_tarjeta_response_from_orm():
    orm = Tarjeta(
        id=1,
        cuenta_id=2,
        tipo="debito",
        ultimos_4_digitos="4567",
        vencimiento="12/28",
        limite=Decimal("2000.00"),
        fecha_corte=15,
        fecha_pago=5,
    )
    schema = TarjetaResponse.model_validate(orm)
    assert schema.ultimos_4_digitos == "4567"
    assert schema.limite == Decimal("2000.00")
    assert schema.fecha_corte == 15


def test_comercio_response_from_orm():
    orm = Comercio(
        id=1,
        nombre_ficticio="Bodega Don Pepe",
        categoria="Alimentación",
        codigo_rubro_mcc="5411",
        si_cobra_suscripcion=False,
    )
    schema = ComercioResponse.model_validate(orm)
    assert schema.nombre_ficticio == "Bodega Don Pepe"
    assert schema.si_cobra_suscripcion is False


def test_pago_programado_response_from_orm():
    orm = PagoProgramado(
        id=1,
        cuenta_id=1,
        servicio="Luz del Sur",
        monto_estimado=Decimal("120.00"),
        dia_vencimiento=20,
    )
    schema = PagoProgramadoResponse.model_validate(orm)
    assert schema.servicio == "Luz del Sur"
    assert schema.monto_estimado == Decimal("120.00")


def test_beneficiario_response_from_orm():
    orm = Beneficiario(
        id=1,
        cliente_id=1,
        alias="Hermano",
        banco="Banco de Crédito",
        cci="00219400000000000099",
    )
    schema = BeneficiarioResponse.model_validate(orm)
    assert schema.alias == "Hermano"
    assert schema.banco == "Banco de Crédito"


def test_tipo_cambio_response_from_orm():
    orm = TipoCambio(
        id=1,
        fecha=date(2026, 11, 14),
        compra=Decimal("3.7250"),
        venta=Decimal("3.7550"),
    )
    schema = TipoCambioResponse.model_validate(orm)
    assert schema.compra == Decimal("3.7250")
    assert schema.venta == Decimal("3.7550")


def test_evento_seguridad_response_from_orm():
    dt = datetime(2026, 11, 14, 10, 30, 0)
    orm = EventoSeguridad(
        id=1,
        cliente_id=1,
        tipo="login",
        dispositivo="iPhone 15",
        ciudad="Lima",
        fecha_hora=dt,
        es_sospechoso=False,
    )
    schema = EventoSeguridadResponse.model_validate(orm)
    assert schema.tipo == "login"
    assert schema.ciudad == "Lima"
    assert schema.es_sospechoso is False


def test_producto_referencial_response_from_orm():
    orm = ProductoReferencial(
        id=1,
        tipo="tarjeta_credito",
        nombre="Tarjeta Oro",
        tea=Decimal("29.90"),
        tcea=Decimal("35.50"),
        membresia=Decimal("150.00"),
    )
    schema = ProductoReferencialResponse.model_validate(orm)
    assert schema.nombre == "Tarjeta Oro"
    assert schema.tea == Decimal("29.90")


def test_movimiento_response_from_orm():
    dt = datetime(2026, 11, 14, 15, 0, 0)
    orm = Movimiento(
        id=1,
        cuenta_id=1,
        fecha_hora=dt,
        monto=Decimal("-45.20"),
        moneda="PEN",
        descripcion="Supermercado Central",
        comercio_id=2,
        categoria="Alimentación",
        subcategoria="Supermercados",
        canal="POS",
        es_recurrente=False,
        estado="procesado",
    )
    schema = MovimientoResponse.model_validate(orm)
    assert schema.id == 1
    assert schema.monto == Decimal("-45.20")
    assert schema.comercio_id == 2
    assert schema.estado == "procesado"


def test_paginated_movimientos_calculation():
    dt = datetime(2026, 11, 14, 15, 0, 0)
    mov = MovimientoResponse(
        id=1,
        cuenta_id=1,
        fecha_hora=dt,
        monto=Decimal("-20.00"),
        moneda="PEN",
        descripcion="Cafetería",
        categoria="Alimentación",
        subcategoria="Café",
        canal="POS",
        es_recurrente=False,
        estado="procesado",
    )

    # total_pages calculation when total=25, page_size=10 -> 3
    paginated = PaginatedMovimientosResponse(
        items=[mov],
        total=25,
        page=1,
        page_size=10,
    )
    assert paginated.total_pages == 3

    # total=0 -> total_pages=0
    paginated_zero = PaginatedMovimientosResponse(
        items=[],
        total=0,
        page=1,
        page_size=20,
    )
    assert paginated_zero.total_pages == 0

    # total=20, page_size=20 -> total_pages=1
    paginated_exact = PaginatedMovimientosResponse(
        items=[],
        total=20,
        page=1,
        page_size=20,
    )
    assert paginated_exact.total_pages == 1

    # explicit total_pages override
    paginated_custom = PaginatedMovimientosResponse(
        items=[],
        total=100,
        page=1,
        page_size=10,
        total_pages=12,
    )
    assert paginated_custom.total_pages == 12


def test_tick_override_request_defaults_and_validation():
    # Empty request has all defaults set to None
    req = TickOverrideRequest()
    assert req.cuenta_id is None
    assert req.monto is None
    assert req.categoria is None
    assert req.subcategoria is None
    assert req.descripcion is None
    assert req.canal is None

    # Partial populated request
    req2 = TickOverrideRequest(
        cuenta_id=1,
        monto=Decimal("-55.50"),
        categoria="Transporte",
        canal="POS",
    )
    assert req2.cuenta_id == 1
    assert req2.monto == Decimal("-55.50")
    assert req2.categoria == "Transporte"
    assert req2.subcategoria is None
    assert req2.canal == "POS"

    # Invalid Decimal raises ValidationError
    with pytest.raises(ValidationError):
        TickOverrideRequest(monto="not-a-number")


def test_simulacion_status_response():
    status = SimulacionStatusResponse(
        simulation_active=True,
        interval_min=10,
        interval_max=30,
        active_sse_subscribers=2,
        total_events_emitted=42,
    )
    assert status.simulation_active is True
    assert status.interval_min == 10
    assert status.interval_max == 30
    assert status.active_sse_subscribers == 2
    assert status.total_events_emitted == 42
