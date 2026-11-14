import math
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ClienteResponse(BaseSchema):
    id: int
    nombre: str
    nivel: str
    cliente_desde: date
    ingreso_mensual: Decimal
    dia_pago: int
    perfil: str


class CuentaResponse(BaseSchema):
    id: int
    cliente_id: int
    tipo: str
    moneda: str
    numero_enmascarado: str
    cci: str
    saldo: Decimal


class TarjetaResponse(BaseSchema):
    id: int
    cuenta_id: int
    tipo: str
    ultimos_4_digitos: str
    vencimiento: str
    limite: Decimal
    fecha_corte: int
    fecha_pago: int


class ComercioResponse(BaseSchema):
    id: int
    nombre_ficticio: str
    categoria: str
    codigo_rubro_mcc: str
    si_cobra_suscripcion: bool


class PagoProgramadoResponse(BaseSchema):
    id: int
    cuenta_id: int
    servicio: str
    monto_estimado: Decimal
    dia_vencimiento: int


class BeneficiarioResponse(BaseSchema):
    id: int
    cliente_id: int
    alias: str
    banco: str
    cci: str


class TipoCambioResponse(BaseSchema):
    id: int
    fecha: date
    compra: Decimal
    venta: Decimal


class EventoSeguridadResponse(BaseSchema):
    id: int
    cliente_id: int
    tipo: str
    dispositivo: str
    ciudad: str
    fecha_hora: datetime
    es_sospechoso: bool


class ProductoReferencialResponse(BaseSchema):
    id: int
    tipo: str
    nombre: str
    tea: Decimal
    tcea: Decimal
    membresia: Decimal


class MovimientoResponse(BaseSchema):
    id: int
    cuenta_id: int
    fecha_hora: datetime
    monto: Decimal
    moneda: str
    descripcion: str
    comercio_id: Optional[int] = None
    categoria: str
    subcategoria: str
    canal: str
    es_recurrente: bool = False
    estado: str = "procesado"


class PaginatedMovimientosResponse(BaseSchema):
    items: List[MovimientoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int = 0

    @model_validator(mode="after")
    def compute_total_pages(self) -> "PaginatedMovimientosResponse":
        if self.total_pages <= 0:
            if self.page_size > 0 and self.total > 0:
                self.total_pages = math.ceil(self.total / self.page_size)
            else:
                self.total_pages = 0
        return self


class TickOverrideRequest(BaseSchema):
    cuenta_id: Optional[int] = None
    monto: Optional[Decimal] = None
    categoria: Optional[str] = None
    subcategoria: Optional[str] = None
    descripcion: Optional[str] = None
    canal: Optional[str] = None


class SimulacionStatusResponse(BaseSchema):
    simulation_active: bool
    interval_min: int
    interval_max: int
    active_sse_subscribers: int
    total_events_emitted: int


class HealthResponse(BaseSchema):
    status: str
    db: str
    simulation_active: bool
