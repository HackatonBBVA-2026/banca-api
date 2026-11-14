# Especificación Técnica y Plan de Implementación: `banca-api`

## 1. Visión y Alcance
`banca-api` es una API REST y de streaming de eventos (SSE) que simula el núcleo bancario y transaccional de una billetera digital / cuenta bancaria personal. Proporciona datos sintéticos realistas tanto estáticos (historial de 6 meses) como dinámicos (en tiempo real) para alimentar modelos analíticos y aplicaciones cliente sin datos reales ni credenciales.

### Restricciones Clave:
- **Neutralidad de Marca**: Nombres y comercios ficticios; sin marcas oficiales.
- **Portabilidad Inmediata**: La base de datos SQLite se inicializa y puebla automáticamente en el arranque si no existe, o mediante `python -m src.seed`.
- **Integridad Financiera**: Tipos monetarios en `DECIMAL(12, 2)` con `decimal.Decimal` en Python (cero floats).
- **Concurrencia Segura**: SQLite configurado en modo WAL con `busy_timeout=5000` y serialización de escrituras con `asyncio.Lock`.
- **Transmisión en Vivo**: Canal Server-Sent Events (SSE) con patrón Fan-Out Pub/Sub, desuscripción automática al desconectarse y latidos (*heartbeat pings*).

---

## 2. Arquitectura del Sistema

```
                         +-----------------------------+
                         |   Background Ticker Task    |
                         |  (asyncio loop aleatorio)   |
                         +--------------+--------------+
                                        |
                                        v
+-----------------------+       +---------------+       +-------------------------+
|   POST /sim/tick      | ----> |  Transaction  | ----> |   PubSub Broadcaster    |
| (Disparo manual/test) |       | Service (WAL) |       |  (Registry of Queues)   |
+-----------------------+       +-------+-------+       +------------+------------+
                                        |                            |
                                        v                            v
                                 +--------------+       +-------------------------+
                                 |  SQLite DB   |       | GET /movimientos/stream |
                                 |  (WAL Mode)  |       |  (SSE Multi-subscriber) |
                                 +------+-------+       +-------------------------+
                                        |
                                        v
                                 +--------------+
                                 | Endpoints    |
                                 | HTTP REST    |
                                 +--------------+
```

### Componentes:
1. **Stack Tecnológico**: Python 3.10+, FastAPI, SQLAlchemy 2.0 (asyncio con `sqlite+aiosqlite`), Pydantic v2, pytest.
2. **Capa de Base de Datos**: SQLite local (`banca.db`) con PRAGMAs obligatorios:
   ```sql
   PRAGMA journal_mode=WAL;
   PRAGMA synchronous=NORMAL;
   PRAGMA busy_timeout=5000;
   PRAGMA foreign_keys=ON;
   ```
3. **Transaction Service**: Modela las operaciones. Solo transacciones con `estado == 'procesado'` mutan `cuentas.saldo`. Protegido por un `asyncio.Lock` de aplicación para escrituras.
4. **Deterministic Seeder**: Crea cliente, cuentas (PEN y USD), tarjetas, beneficiarios, pagos programados y ~300 movimientos distribuidos en 180 días con semilla determinista (`SEED_VALUE=42`), anclada a una fecha base estática o la fecha actual normalizada.
5. **Fan-Out Broadcaster**: Registro en memoria `set[asyncio.Queue]`. Cada conexión SSE suscribe una cola acotada (`maxsize=100`) y se desuscribe limpiamente en un bloque `finally`.
6. **Background Ticker**: Bucle periódico asíncrono con intervalo aleatorio (ej. 10 a 30s) configurable por entorno (`SIMULATION_ENABLED=True`, `SIMULATION_INTERVAL_MIN=10`, `SIMULATION_INTERVAL_MAX=30`).

---

## 3. Modelo de Datos Relacional y Esquemas

Todas las llaves primarias son `INTEGER PRIMARY KEY AUTOINCREMENT`. Valores monetarios son `Numeric(12, 2)` / `Decimal`.

### 3.1. Núcleo: `movimientos`
- `id`: INTEGER PK.
- `cuenta_id`: INTEGER FK -> `cuentas.id`.
- `fecha_hora`: DATETIME ISO 8601.
- `monto`: DECIMAL(12, 2) (Positivo: ingreso, Negativo: gasto).
- `moneda`: VARCHAR(3) (`PEN`, `USD`).
- `descripcion`: VARCHAR(255).
- `comercio_id`: INTEGER FK Nullable -> `comercios.id`.
- `categoria`: VARCHAR(50) (ej. `Alimentación`, `Servicios`, `Transporte`, `Entretenimiento`, `Ingresos`, `Transferencias`).
- `subcategoria`: VARCHAR(50) (ej. `Supermercados`, `Luz`, `Taxi`, `Streaming`, `Sueldo`).
- `canal`: VARCHAR(30) (`POS`, `QR`, `transferencia`, `debito_automatico`, `cajero`).
- `es_recurrente`: BOOLEAN.
- `estado`: VARCHAR(20) (`procesado`, `pendiente`, `revertido`).

### 3.2. Tablas de Soporte
- **`clientes`**: `id`, `nombre`, `nivel` (ej. "Black Tier"), `cliente_desde` (DATE), `ingreso_mensual` (DECIMAL(12, 2)), `dia_pago` (INTEGER), `perfil` (VARCHAR).
- **`cuentas`**: `id`, `cliente_id` (FK), `tipo` (`ahorro`/`corriente`), `moneda` (`PEN`/`USD`), `numero_enmascarado` (VARCHAR), `cci` (VARCHAR), `saldo` (DECIMAL(12, 2)).
- **`tarjetas`**: `id`, `cuenta_id` (FK), `tipo` (`debito`/`credito`), `ultimos_4_digitos` (VARCHAR(4)), `vencimiento` (VARCHAR(5)), `limite` (DECIMAL(12, 2)), `fecha_corte` (INTEGER), `fecha_pago` (INTEGER).
- **`comercios`**: `id`, `nombre_ficticio` (VARCHAR), `categoria` (VARCHAR), `codigo_rubro_mcc` (VARCHAR(4)), `si_cobra_suscripcion` (BOOLEAN).
- **`pagos_programados`**: `id`, `cuenta_id` (FK), `servicio` (VARCHAR), `monto_estimado` (DECIMAL(12, 2)), `dia_vencimiento` (INTEGER).
- **`beneficiarios`**: `id`, `cliente_id` (FK), `alias` (VARCHAR), `banco` (VARCHAR), `cci` (VARCHAR(20)).
- **`tipo_cambio`**: `id` INTEGER PK, `fecha` (DATE UNIQUE), `compra` (DECIMAL(6, 4)), `venta` (DECIMAL(6, 4)).
- **`eventos_seguridad`**: `id`, `cliente_id` (FK), `tipo` (VARCHAR), `dispositivo` (VARCHAR), `ciudad` (VARCHAR), `fecha_hora` (DATETIME), `es_sospechoso` (BOOLEAN).
- **`productos_referenciales`**: `id`, `tipo` (`prestamo_personal`, `tarjeta_credito`), `nombre` (VARCHAR), `tea` (DECIMAL(5, 2)), `tcea` (DECIMAL(5, 2)), `membresia` (DECIMAL(8, 2)).

---

## 4. API Endpoints y Contratos

### 4.1. Catálogos y Soporte (HTTP GET)
- `GET /health` -> `{"status": "ok", "db": "connected", "simulation_active": bool}`
- `GET /cliente` -> `ClienteResponse` (devuelve el cliente simulado actual, por defecto id=1).
- `GET /cuentas` -> `list[CuentaResponse]`
- `GET /cuentas/{id}/movimientos` -> Paginado con filtros:
  - Query params: `page: int = 1`, `page_size: int = 20`, `tipo: str | None = None` (`ingreso`/`gasto`), `categoria: str | None = None`, `desde: datetime | None = None`, `hasta: datetime | None = None`.
  - Retorna: `PaginatedMovimientosResponse(items: list[MovimientoResponse], total: int, page: int, page_size: int)`.
- `GET /tarjetas` -> `list[TarjetaResponse]`
- `GET /comercios` -> `list[ComercioResponse]`
- `GET /pagos-programados` -> `list[PagoProgramadoResponse]`
- `GET /beneficiarios` -> `list[BeneficiarioResponse]`
- `GET /tipo-cambio` -> `TipoCambioResponse`
- `GET /eventos-seguridad` -> `list[EventoSeguridadResponse]`
- `GET /productos-referenciales` -> `list[ProductoReferencialResponse]`

### 4.2. Streaming en Vivo (SSE)
- `GET /movimientos/stream`:
  - Retorna `StreamingResponse(media_type="text/event-stream")`.
  - Estructura de eventos:
    ```
    event: movimiento
    data: {"id": 305, "cuenta_id": 1, "monto": -18.50, "descripcion": "Cafetería Central", ...}

    : ping
    ```
  - Emite `: ping\n\n` cada 15 segundos para mantener viva la conexión.
  - Al desconectarse el cliente, la cola se elimina de la lista de difusión.

### 4.3. Simulación y Control
- `POST /simulacion/tick` (Status 201 Created):
  - Request body opcional: `TickOverrideRequest(cuenta_id: int | None = None, monto: Decimal | None = None, categoria: str | None = None, descripcion: str | None = None)`.
  - Si viene vacío, genera un movimiento aleatorio realista (gasto en comercio, transferencia o ingreso).
  - Inserta el movimiento, actualiza el saldo de la cuenta atómicamente y lo emite a los suscriptores SSE.
  - Retorna `MovimientoResponse`.
- `GET /simulacion/status`: Retorna estado de la simulación en segundo plano, número de suscriptores SSE activos y conteo total de transacciones emitidas.

---

## 5. Datos Sintéticos: Composición y Casos Límite
- **Semilla Base**: `SEED_VALUE=42`.
- **Cuentas Iniciales**:
  - Cuenta 1: Ahorro Soles (`PEN`), saldo inicial ~3,500.00 PEN.
  - Cuenta 2: Ahorro Dólares (`USD`), saldo inicial ~500.00 USD.
- **Historial (180 días, ~300 movimientos)**:
  - Abono de nómina mensual en día 28 (+5,000.00 PEN).
  - Gastos recurrentes (luz, agua, internet, plataformas de streaming con `es_recurrente=True`).
  - Gastos cotidianos variables (alimentación, transporte, farmacia).
  - **Casos límite inyectados para analítica/evaluación**:
    1. **Cobro duplicado**: Mismo comercio, monto y minuto con segundos de diferencia.
    2. **Movimiento revertido**: Un cobro cancelado con `estado='revertido'` y saldo restituido.
    3. **Anomalía de gasto**: Un consumo atípico puntual de importe alto.

---

## 6. Plan de Implementación por Fases (TDD)

- **Fase 1: Scaffolding y Repositorio**
  - Inicializar git y configurar remoto `git remote add origin https://github.com/HackatonBBVA-2026/banca-api.git`.
  - Instalar dependencias (`fastapi`, `uvicorn`, `sqlalchemy`, `aiosqlite`, `pydantic-settings`, `pytest`, `pytest-asyncio`, `httpx`).
  - Crear script `./init.sh` y configuración base `src/config.py`.

- **Fase 2: Capa de Base de Datos y Modelos**
  - Implementar `src/database.py` con WAL mode, `asyncio.Lock` para escrituras y session factory.
  - Implementar `src/models.py` con todos los modelos relacionales (declarative base, tipos `Numeric(12, 2)`).
  - Tests en `tests/test_database.py`.

- **Fase 3: Esquemas Pydantic**
  - Implementar `src/schemas.py` con validación estricta, serialización de `Decimal` a float/string y modelos de paginación.

- **Fase 4: Generador Determinista (Seed)**
  - Implementar `src/seed.py` determinista con semilla fija.
  - Tests en `tests/test_seed.py` (verificando que saldo = balance histórico y verificando presencia de casos límite).

- **Fase 5: Motor de Transmisión (SSE Broadcaster) y Simulación**
  - Implementar `src/broadcaster.py` con registro Pub/Sub, desuscripción segura y pings periódicos.
  - Implementar `src/simulation.py` con ticker aleatorio y generador de eventos para `tick`.
  - Tests en `tests/test_simulation.py` y `tests/test_broadcaster.py`.

- **Fase 6: Endpoints FastAPI y Servidor Web**
  - Implementar `src/main.py` con endpoints REST, lifespan con auto-seed, y ruta SSE `/movimientos/stream`.
  - Tests de integración en `tests/test_api.py`.

- **Fase 7: Verificación Integral y Documentación**
  - Ejecutar `./init.sh` y suite completa de pruebas con `pytest`.
  - Documentar API en `README.md` con ejemplos de consumo (cURL, JavaScript SSE EventSource) para el resto del equipo.
