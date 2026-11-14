# Progreso de Implementación: `banca-api`

## Estado de Features
- [x] `F01-models-db`: Database connection layer with SQLite WAL mode and SQLAlchemy 2.0 async models
- [x] `F02-schemas`: Pydantic v2 schemas for all entities and filters
- [ ] `F03-seeder`: Deterministic synthetic data generator (seed=42)
- [ ] `F04-broadcaster-simulation`: SSE fan-out broadcaster & dynamic simulation
- [ ] `F05-api-endpoints`: FastAPI REST & SSE endpoints
- [ ] `F06-documentation`: README documentation and integration examples

## Bitácora
- 2026-11-14: Scaffolding inicial, arnés configurado, entorno `.venv` y dependencias instaladas.
- 2026-11-14: Implementado F01-models-db (Settings, SQLite WAL engine con PRAGMAs, async_sessionmaker, db_write_lock, modelos relacionales y suite de tests pasando al 100%).
- 2026-11-14: Implementado F02-schemas con TDD estricto (schemas Pydantic v2 para todas las entidades con `from_attributes=True`, cálculo de `total_pages` para paginación, `TickOverrideRequest`, `SimulacionStatusResponse`, `HealthResponse`, y suite de 13 pruebas unitarias pasando al 100%).
