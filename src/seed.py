import argparse
import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
import random
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import get_settings
from src.database import Base, async_session as default_async_session, engine as default_engine
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

ANCHOR_DATE = datetime(2026, 11, 14, 12, 0, 0)
BASE_INITIAL_PEN_BALANCE = Decimal("1500.00")


async def seed_database(
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Deterministically seeds the database with initial banking data.
    
    If data already exists and force is False, seeding is skipped.
    If force is True, existing data is wiped and rebuilt deterministically.
    """
    settings = get_settings()
    seed_value = settings.SEED_VALUE
    rng = random.Random(seed_value)

    if session_factory is None:
        session_factory = default_async_session
        bind_engine = default_engine
    else:
        bind_engine = getattr(session_factory, "bind", None) or session_factory.kw.get("bind", None)

    if bind_engine is not None:
        async with bind_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        # Check if client already exists
        existing_client = (
            await session.execute(select(Cliente).limit(1))
        ).scalars().first()

        if existing_client is not None and not force:
            return {
                "status": "skipped",
                "message": "Database already contains data and force=False",
            }

        if force:
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(table.delete())
            await session.commit()
            session.expunge_all()

        # 1. Cliente
        cliente = Cliente(
            nombre="Juan Pérez",
            nivel="Black Tier",
            cliente_desde=date(2022, 1, 15),
            ingreso_mensual=Decimal("5000.00"),
            dia_pago=28,
            perfil="persona_dependiente",
        )
        session.add(cliente)
        await session.flush()

        # 2. Cuentas
        cuenta_pen = Cuenta(
            cliente_id=cliente.id,
            tipo="Ahorro",
            moneda="PEN",
            numero_enmascarado="0011-0123-****-4567",
            cci="00110123000123456789",
            saldo=Decimal("0.00"),  # Will calculate exact final saldo from movements
        )
        cuenta_usd = Cuenta(
            cliente_id=cliente.id,
            tipo="Ahorro",
            moneda="USD",
            numero_enmascarado="0011-0123-****-8901",
            cci="00110123000876543210",
            saldo=Decimal("850.00"),
        )
        session.add_all([cuenta_pen, cuenta_usd])
        await session.flush()

        # 3. Tarjetas
        tarjeta_debito = Tarjeta(
            cuenta_id=cuenta_pen.id,
            tipo="Debito",
            ultimos_4_digitos="4532",
            vencimiento="08/29",
            limite=Decimal("0.00"),
            fecha_corte=0,
            fecha_pago=0,
        )
        tarjeta_credito = Tarjeta(
            cuenta_id=cuenta_pen.id,
            tipo="Credito",
            ultimos_4_digitos="9012",
            vencimiento="11/28",
            limite=Decimal("10000.00"),
            fecha_corte=15,
            fecha_pago=5,
        )
        session.add_all([tarjeta_debito, tarjeta_credito])

        # 4. 15 Comercios ficticios
        comercios_def = [
            # Alimentación
            ("Supermercados Metro", "Alimentación", "5411", False),
            ("Wong", "Alimentación", "5411", False),
            ("Starbucks Coffee", "Alimentación", "5814", False),
            ("Restaurante Central", "Alimentación", "5812", False),
            # Transporte
            ("Primax Combustibles", "Transporte", "5541", False),
            ("Uber Trip", "Transporte", "4121", False),
            # Entretenimiento
            ("Netflix", "Entretenimiento", "4899", True),
            ("Spotify", "Entretenimiento", "4899", True),
            ("Cineplanet", "Entretenimiento", "7832", False),
            # Servicios
            ("Sedapal", "Servicios", "4900", False),
            ("Enel Distribución", "Servicios", "4900", False),
            ("Movistar Hogar", "Servicios", "4814", True),
            # Salud
            ("Farmacias Inkafarma", "Salud", "5912", False),
            ("Clínica Delgado", "Salud", "8099", False),
            # Tecnología
            ("Hiraoka Electrónica", "Tecnología", "5732", False),
        ]
        comercios_map: Dict[str, Comercio] = {}
        for nombre, cat, mcc, subs in comercios_def:
            c = Comercio(
                nombre_ficticio=nombre,
                categoria=cat,
                codigo_rubro_mcc=mcc,
                si_cobra_suscripcion=subs,
            )
            session.add(c)
            comercios_map[nombre] = c

        await session.flush()

        # 5. Pagos Programados
        pagos = [
            PagoProgramado(
                cuenta_id=cuenta_pen.id,
                servicio="Luz del Sur (Luz)",
                monto_estimado=Decimal("135.50"),
                dia_vencimiento=10,
            ),
            PagoProgramado(
                cuenta_id=cuenta_pen.id,
                servicio="Sedapal (Agua)",
                monto_estimado=Decimal("68.20"),
                dia_vencimiento=15,
            ),
            PagoProgramado(
                cuenta_id=cuenta_pen.id,
                servicio="Movistar Fibra (Internet)",
                monto_estimado=Decimal("119.90"),
                dia_vencimiento=20,
            ),
            PagoProgramado(
                cuenta_id=cuenta_pen.id,
                servicio="Claro Móvil (Celular)",
                monto_estimado=Decimal("65.00"),
                dia_vencimiento=22,
            ),
            PagoProgramado(
                cuenta_id=cuenta_pen.id,
                servicio="Mantenimiento Edificio",
                monto_estimado=Decimal("250.00"),
                dia_vencimiento=5,
            ),
        ]
        session.add_all(pagos)

        # 6. Beneficiarios
        beneficiarios = [
            Beneficiario(
                cliente_id=cliente.id,
                alias="Mamá",
                banco="BCP",
                cci="00219100987654321012",
            ),
            Beneficiario(
                cliente_id=cliente.id,
                alias="Carlos Hermano",
                banco="Interbank",
                cci="00320000876543210987",
            ),
            Beneficiario(
                cliente_id=cliente.id,
                alias="Propietario Alquiler",
                banco="BBVA",
                cci="00110123000123456789",
            ),
            Beneficiario(
                cliente_id=cliente.id,
                alias="Amigo Finanzas",
                banco="Scotiabank",
                cci="05501000112233445566",
            ),
            Beneficiario(
                cliente_id=cliente.id,
                alias="Dr. Torres Dentista",
                banco="BanBif",
                cci="03801200998877665544",
            ),
        ]
        session.add_all(beneficiarios)

        # 7. Tipo de Cambio
        tipo_cambio = TipoCambio(
            fecha=ANCHOR_DATE.date(),
            compra=Decimal("3.7250"),
            venta=Decimal("3.7550"),
        )
        session.add(tipo_cambio)

        # 8. Eventos de Seguridad
        eventos = [
            EventoSeguridad(
                cliente_id=cliente.id,
                tipo="Login App Móvil",
                dispositivo="iPhone 15 Pro iOS 17",
                ciudad="Lima, Perú",
                fecha_hora=ANCHOR_DATE - timedelta(days=2, hours=4),
                es_sospechoso=False,
            ),
            EventoSeguridad(
                cliente_id=cliente.id,
                tipo="Consulta Web Banking",
                dispositivo="MacBook Pro macOS Sonoma",
                ciudad="Lima, Perú",
                fecha_hora=ANCHOR_DATE - timedelta(days=1, hours=2),
                es_sospechoso=False,
            ),
            EventoSeguridad(
                cliente_id=cliente.id,
                tipo="Intento de acceso IP sospechosa",
                dispositivo="Linux Firefox Unknown",
                ciudad="Moscú, Rusia",
                fecha_hora=ANCHOR_DATE - timedelta(days=5, hours=8),
                es_sospechoso=True,
            ),
        ]
        session.add_all(eventos)

        # 9. Productos Referenciales
        productos = [
            ProductoReferencial(
                tipo="Prestamo",
                nombre="Préstamo Personal Simulador",
                tea=Decimal("14.50"),
                tcea=Decimal("16.80"),
                membresia=Decimal("0.00"),
            ),
            ProductoReferencial(
                tipo="Tarjeta",
                nombre="Tarjeta Black Simulador",
                tea=Decimal("24.50"),
                tcea=Decimal("28.90"),
                membresia=Decimal("350.00"),
            ),
        ]
        session.add_all(productos)

        # 10. Movimientos (~300 en total)
        movimientos_list: List[Movimiento] = []

        # A. Nómina mensual (6 meses: Mayo a Octubre el día 28 a las 09:00:00)
        # 6 nóminas
        for month in range(5, 11):
            movimientos_list.append(
                Movimiento(
                    cuenta_id=cuenta_pen.id,
                    fecha_hora=datetime(2026, month, 28, 9, 0, 0),
                    monto=Decimal("5000.00"),
                    moneda="PEN",
                    descripcion="Abono Haberes / Nómina BBVA",
                    comercio_id=None,
                    categoria="Ingresos",
                    subcategoria="Sueldo",
                    canal="transferencia",
                    es_recurrente=True,
                    estado="procesado",
                )
            )

        # B. Suscripciones y Débitos automáticos mensuales (6 meses: Mayo a Octubre)
        # 6 * 6 = 36 movimientos recurrentes
        for month in range(5, 11):
            movimientos_list.extend(
                [
                    Movimiento(
                        cuenta_id=cuenta_pen.id,
                        fecha_hora=datetime(2026, month, 5, 8, 30, 0),
                        monto=Decimal("-250.00"),
                        moneda="PEN",
                        descripcion="Mantenimiento Edificio - Pago mensual",
                        comercio_id=None,
                        categoria="Servicios",
                        subcategoria="Vivienda",
                        canal="transferencia",
                        es_recurrente=True,
                        estado="procesado",
                    ),
                    Movimiento(
                        cuenta_id=cuenta_pen.id,
                        fecha_hora=datetime(2026, month, 5, 10, 0, 0),
                        monto=Decimal("-20.90"),
                        moneda="PEN",
                        descripcion="Spotify Premium Familiar",
                        comercio_id=comercios_map["Spotify"].id,
                        categoria="Entretenimiento",
                        subcategoria="Streaming",
                        canal="online",
                        es_recurrente=True,
                        estado="procesado",
                    ),
                    Movimiento(
                        cuenta_id=cuenta_pen.id,
                        fecha_hora=datetime(2026, month, 10, 11, 0, 0),
                        monto=Decimal("-135.50"),
                        moneda="PEN",
                        descripcion="Enel Distribución - Recibo Eléctrico",
                        comercio_id=comercios_map["Enel Distribución"].id,
                        categoria="Servicios",
                        subcategoria="Electricidad",
                        canal="debito_automatico",
                        es_recurrente=True,
                        estado="procesado",
                    ),
                    Movimiento(
                        cuenta_id=cuenta_pen.id,
                        fecha_hora=datetime(2026, month, 12, 14, 0, 0),
                        monto=Decimal("-44.90"),
                        moneda="PEN",
                        descripcion="Netflix Suscripción Estándar",
                        comercio_id=comercios_map["Netflix"].id,
                        categoria="Entretenimiento",
                        subcategoria="Streaming",
                        canal="online",
                        es_recurrente=True,
                        estado="procesado",
                    ),
                    Movimiento(
                        cuenta_id=cuenta_pen.id,
                        fecha_hora=datetime(2026, month, 15, 12, 0, 0),
                        monto=Decimal("-68.20"),
                        moneda="PEN",
                        descripcion="Sedapal - Recibo de Agua Potable",
                        comercio_id=comercios_map["Sedapal"].id,
                        categoria="Servicios",
                        subcategoria="Agua",
                        canal="debito_automatico",
                        es_recurrente=True,
                        estado="procesado",
                    ),
                    Movimiento(
                        cuenta_id=cuenta_pen.id,
                        fecha_hora=datetime(2026, month, 20, 16, 0, 0),
                        monto=Decimal("-119.90"),
                        moneda="PEN",
                        descripcion="Movistar Hogar Fibra Óptica",
                        comercio_id=comercios_map["Movistar Hogar"].id,
                        categoria="Servicios",
                        subcategoria="Internet",
                        canal="debito_automatico",
                        es_recurrente=True,
                        estado="procesado",
                    ),
                ]
            )

        # C. Deliberate Case 1: Cobro duplicado (same comercio, same amount, same category, 20s apart)
        dup_starbucks = comercios_map["Starbucks Coffee"]
        movimientos_list.extend(
            [
                Movimiento(
                    cuenta_id=cuenta_pen.id,
                    fecha_hora=datetime(2026, 10, 15, 14, 30, 0),
                    monto=Decimal("-24.50"),
                    moneda="PEN",
                    descripcion="Starbucks Coffee - Consumo Bebidas",
                    comercio_id=dup_starbucks.id,
                    categoria="Alimentación",
                    subcategoria="Cafetería",
                    canal="POS",
                    es_recurrente=False,
                    estado="procesado",
                ),
                Movimiento(
                    cuenta_id=cuenta_pen.id,
                    fecha_hora=datetime(2026, 10, 15, 14, 30, 20),
                    monto=Decimal("-24.50"),
                    moneda="PEN",
                    descripcion="Starbucks Coffee - Consumo Bebidas",
                    comercio_id=dup_starbucks.id,
                    categoria="Alimentación",
                    subcategoria="Cafetería",
                    canal="POS",
                    es_recurrente=False,
                    estado="procesado",
                ),
            ]
        )

        # D. Deliberate Case 2: Movimiento revertido
        metro = comercios_map["Supermercados Metro"]
        movimientos_list.append(
            Movimiento(
                cuenta_id=cuenta_pen.id,
                fecha_hora=datetime(2026, 9, 12, 19, 15, 0),
                monto=Decimal("-120.00"),
                moneda="PEN",
                descripcion="Supermercados Metro - Compra Anulada",
                comercio_id=metro.id,
                categoria="Alimentación",
                subcategoria="Supermercados",
                canal="POS",
                es_recurrente=False,
                estado="revertido",
            )
        )

        # E. Deliberate Case 3: Gasto atípico/anómalo (~2,500.00 PEN)
        hiraoka = comercios_map["Hiraoka Electrónica"]
        movimientos_list.append(
            Movimiento(
                cuenta_id=cuenta_pen.id,
                fecha_hora=datetime(2026, 8, 20, 17, 30, 0),
                monto=Decimal("-2500.00"),
                moneda="PEN",
                descripcion="Hiraoka Electrónica - Laptop Asus Zenbook",
                comercio_id=hiraoka.id,
                categoria="Tecnología",
                subcategoria="Electrohogar",
                canal="POS",
                es_recurrente=False,
                estado="procesado",
            )
        )

        # Count so far: 6 + 36 + 2 + 1 + 1 = 46.
        # We need 300 - 46 = 254 daily movements to complete exactly 300 movements.
        templates = [
            {
                "comercio_nombre": "Supermercados Metro",
                "desc": "Metro - Compra de víveres",
                "categoria": "Alimentación",
                "subcategoria": "Supermercados",
                "min_m": 45,
                "max_m": 220,
                "canal": "POS",
            },
            {
                "comercio_nombre": "Wong",
                "desc": "Wong - Compra de alimentos",
                "categoria": "Alimentación",
                "subcategoria": "Supermercados",
                "min_m": 55,
                "max_m": 260,
                "canal": "POS",
            },
            {
                "comercio_nombre": "Starbucks Coffee",
                "desc": "Starbucks - Café y bocaditos",
                "categoria": "Alimentación",
                "subcategoria": "Cafetería",
                "min_m": 15,
                "max_m": 40,
                "canal": "POS",
            },
            {
                "comercio_nombre": "Restaurante Central",
                "desc": "Restaurante - Almuerzo",
                "categoria": "Alimentación",
                "subcategoria": "Restaurantes",
                "min_m": 35,
                "max_m": 120,
                "canal": "POS",
            },
            {
                "comercio_nombre": "Primax Combustibles",
                "desc": "Primax - Combustible G-Premium",
                "categoria": "Transporte",
                "subcategoria": "Gasolina",
                "min_m": 60,
                "max_m": 180,
                "canal": "POS",
            },
            {
                "comercio_nombre": "Uber Trip",
                "desc": "Uber - Viaje Urbano",
                "categoria": "Transporte",
                "subcategoria": "Taxi",
                "min_m": 12,
                "max_m": 45,
                "canal": "online",
            },
            {
                "comercio_nombre": "Cineplanet",
                "desc": "Cineplanet - Entrada cine",
                "categoria": "Entretenimiento",
                "subcategoria": "Cine",
                "min_m": 28,
                "max_m": 80,
                "canal": "online",
            },
            {
                "comercio_nombre": "Farmacias Inkafarma",
                "desc": "Inkafarma - Farmacia y cuidado personal",
                "categoria": "Salud",
                "subcategoria": "Medicamentos",
                "min_m": 18,
                "max_m": 90,
                "canal": "POS",
            },
            {
                "comercio_nombre": "Clínica Delgado",
                "desc": "Clínica Delgado - Consulta externa",
                "categoria": "Salud",
                "subcategoria": "Atención Médica",
                "min_m": 120,
                "max_m": 280,
                "canal": "POS",
            },
            {
                "comercio_nombre": None,
                "desc": "Retiro Cajero Automático BBVA",
                "categoria": "Efectivo",
                "subcategoria": "Retiro ATM",
                "min_m": 100,
                "max_m": 300,
                "canal": "cajero",
            },
            {
                "comercio_nombre": None,
                "desc": "Transferencia a contacto frecuente",
                "categoria": "Transferencias",
                "subcategoria": "Terceros",
                "min_m": 30,
                "max_m": 150,
                "canal": "transferencia",
            },
        ]

        start_date = ANCHOR_DATE - timedelta(days=180)
        # Avoid the exact interval around our duplicate pair (2026-10-15 14:30:00 - 14:30:20)
        blackout_start = datetime(2026, 10, 15, 14, 29, 0)
        blackout_end = datetime(2026, 10, 15, 14, 31, 0)

        daily_movements_count = 254
        for _ in range(daily_movements_count):
            tpl = rng.choice(templates)
            c_obj = comercios_map[tpl["comercio_nombre"]] if tpl["comercio_nombre"] else None
            comercio_id = c_obj.id if c_obj else None

            # Generate random amount
            int_part = rng.randint(tpl["min_m"], tpl["max_m"])
            cents = rng.randint(0, 99)
            monto = Decimal(f"-{int_part}.{cents:02d}")

            # Generate timestamp
            while True:
                offset_sec = rng.randint(0, 180 * 86400 - 60)
                dt = start_date + timedelta(seconds=offset_sec)
                # Ensure no collision with blackout window
                if not (blackout_start <= dt <= blackout_end):
                    break

            movimientos_list.append(
                Movimiento(
                    cuenta_id=cuenta_pen.id,
                    fecha_hora=dt,
                    monto=monto,
                    moneda="PEN",
                    descripcion=tpl["desc"],
                    comercio_id=comercio_id,
                    categoria=tpl["categoria"],
                    subcategoria=tpl["subcategoria"],
                    canal=tpl["canal"],
                    es_recurrente=False,
                    estado="procesado",
                )
            )

        # Sort all movements chronologically
        movimientos_list.sort(key=lambda m: m.fecha_hora)

        # Compute final PEN balance with accounting integrity:
        # Base initial + sum of all processed movements
        processed_sum = sum(
            m.monto for m in movimientos_list if m.estado == "procesado"
        )
        cuenta_pen.saldo = BASE_INITIAL_PEN_BALANCE + processed_sum

        session.add_all(movimientos_list)
        await session.commit()

        return {
            "status": "seeded",
            "cliente_id": cliente.id,
            "cuentas_count": 2,
            "tarjetas_count": 2,
            "comercios_count": len(comercios_map),
            "pagos_programados_count": len(pagos),
            "beneficiarios_count": len(beneficiarios),
            "eventos_count": len(eventos),
            "productos_count": len(productos),
            "movimientos_count": len(movimientos_list),
            "cuenta_pen_saldo": str(cuenta_pen.saldo),
        }


def main():
    parser = argparse.ArgumentParser(description="Deterministic database seeder for banca-api")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild/reseed the database even if data already exists",
    )
    args = parser.parse_args()

    result = asyncio.run(seed_database(force=args.force))
    print(f"Seed completed: {result}")


if __name__ == "__main__":
    main()
