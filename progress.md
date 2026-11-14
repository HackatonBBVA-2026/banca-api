# Progreso de Implementación: `banca-api`

## Estado de Features
- [x] `F01-models-db`: Database connection layer with SQLite WAL mode and SQLAlchemy 2.0 async models
- [x] `F02-schemas`: Pydantic v2 schemas for all entities and filters
- [x] `F03-seeder`: Deterministic synthetic data generator (seed=42)
- [ ] `F04-broadcaster-simulation`: SSE fan-out broadcaster & dynamic simulation
- [ ] `F05-api-endpoints`: FastAPI REST & SSE endpoints
- [ ] `F06-documentation`: README documentation and integration examples

## Bitácora
- 2026-11-14: Scaffolding inicial, arnés configurado, entorno `.venv` y dependencias instaladas.
- 2026-11-14: Implementado F01-models-db (Settings, SQLite WAL engine con PRAGMAs, async_sessionmaker, db_write_lock, modelos relacionales y suite de tests pasando al 100%).
- 2026-11-14: Implementado F02-schemas con TDD estricto (schemas Pydantic v2 para todas las entidades con `from_attributes=True`, cálculo de `total_pages` para paginación, `TickOverrideRequest`, `SimulacionStatusResponse`, `HealthResponse`, y suite de 13 pruebas unitarias pasando al 100%).
- 2026-11-14: Implementado F03-seeder con TDD estricto (`src/seed.py` determinista con SEED_VALUE=42, fecha anchor 2026-11-14, 1 cliente Black Tier, 2 cuentas PEN/USD, 2 tarjetas, 15 comercios, 5 pagos programados, 5 beneficiarios, tipo de cambio, eventos de seguridad con 1 sospechoso foráneo, 2 productos referenciales, 300 movimientos a lo largo de 180 días con nómina mensual, débito recurrente, cobro duplicado consecutivo a 20s, transacción revertida, compra atípica de 2,500 PEN, integridad matemática exacta de saldo PEN en una sola transacción bulk, idempotencia con force=False y reseed con force=True, soporte CLI `python -m src.seed`). Suite de 24 tests pasando al 100%.
