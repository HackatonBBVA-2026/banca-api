from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    nivel: Mapped[str] = mapped_column(String(50), nullable=False)
    cliente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    ingreso_mensual: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    dia_pago: Mapped[int] = mapped_column(Integer, nullable=False)
    perfil: Mapped[str] = mapped_column(String(50), nullable=False)

    cuentas: Mapped[List["Cuenta"]] = relationship(
        "Cuenta", back_populates="cliente", cascade="all, delete-orphan"
    )
    beneficiarios: Mapped[List["Beneficiario"]] = relationship(
        "Beneficiario", back_populates="cliente", cascade="all, delete-orphan"
    )
    eventos_seguridad: Mapped[List["EventoSeguridad"]] = relationship(
        "EventoSeguridad", back_populates="cliente", cascade="all, delete-orphan"
    )


class Cuenta(Base):
    __tablename__ = "cuentas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False)
    numero_enmascarado: Mapped[str] = mapped_column(String(30), nullable=False)
    cci: Mapped[str] = mapped_column(String(30), nullable=False)
    saldo: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="cuentas")
    tarjetas: Mapped[List["Tarjeta"]] = relationship(
        "Tarjeta", back_populates="cuenta", cascade="all, delete-orphan"
    )
    pagos_programados: Mapped[List["PagoProgramado"]] = relationship(
        "PagoProgramado", back_populates="cuenta", cascade="all, delete-orphan"
    )
    movimientos: Mapped[List["Movimiento"]] = relationship(
        "Movimiento", back_populates="cuenta", cascade="all, delete-orphan"
    )


class Tarjeta(Base):
    __tablename__ = "tarjetas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cuenta_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cuentas.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    ultimos_4_digitos: Mapped[str] = mapped_column(String(4), nullable=False)
    vencimiento: Mapped[str] = mapped_column(String(5), nullable=False)
    limite: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha_corte: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_pago: Mapped[int] = mapped_column(Integer, nullable=False)

    cuenta: Mapped["Cuenta"] = relationship("Cuenta", back_populates="tarjetas")


class Comercio(Base):
    __tablename__ = "comercios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre_ficticio: Mapped[str] = mapped_column(String(100), nullable=False)
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    codigo_rubro_mcc: Mapped[str] = mapped_column(String(4), nullable=False)
    si_cobra_suscripcion: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    movimientos: Mapped[List["Movimiento"]] = relationship(
        "Movimiento", back_populates="comercio"
    )


class PagoProgramado(Base):
    __tablename__ = "pagos_programados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cuenta_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cuentas.id"), nullable=False
    )
    servicio: Mapped[str] = mapped_column(String(100), nullable=False)
    monto_estimado: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    dia_vencimiento: Mapped[int] = mapped_column(Integer, nullable=False)

    cuenta: Mapped["Cuenta"] = relationship(
        "Cuenta", back_populates="pagos_programados"
    )


class Beneficiario(Base):
    __tablename__ = "beneficiarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    banco: Mapped[str] = mapped_column(String(50), nullable=False)
    cci: Mapped[str] = mapped_column(String(20), nullable=False)

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="beneficiarios")


class TipoCambio(Base):
    __tablename__ = "tipo_cambio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    compra: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    venta: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)


class EventoSeguridad(Base):
    __tablename__ = "eventos_seguridad"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    dispositivo: Mapped[str] = mapped_column(String(100), nullable=False)
    ciudad: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    es_sospechoso: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    cliente: Mapped["Cliente"] = relationship(
        "Cliente", back_populates="eventos_seguridad"
    )


class ProductoReferencial(Base):
    __tablename__ = "productos_referenciales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    tea: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    tcea: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    membresia: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)


class Movimiento(Base):
    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cuenta_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cuentas.id"), nullable=False
    )
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    comercio_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("comercios.id"), nullable=True
    )
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    subcategoria: Mapped[str] = mapped_column(String(50), nullable=False)
    canal: Mapped[str] = mapped_column(String(30), nullable=False)
    es_recurrente: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default="procesado", nullable=False
    )

    cuenta: Mapped["Cuenta"] = relationship("Cuenta", back_populates="movimientos")
    comercio: Mapped[Optional["Comercio"]] = relationship(
        "Comercio", back_populates="movimientos"
    )
