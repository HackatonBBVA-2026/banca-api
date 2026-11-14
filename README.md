# banca-api: Simulador Transaccional y Billetera Digital

Simulador bancario transaccional sintético y neutral desarrollado para el **Hackathon BBVA 2026**. Expone una API REST moderna de alto rendimiento y un canal de streaming en tiempo real vía **Server-Sent Events (SSE)**, diseñado para alimentar asistentes conversacionales, motores de recomendación financiera, detección de anomalías y aplicaciones frontend de banca digital.

---

## Índice

1. [Características Principales](#características-principales)
2. [Inicio Rápido / Setup](#inicio-rápido--setup)
3. [Diccionario de Datos](#diccionario-de-datos)
4. [Ground Truth y Casos Borde Sintéticos](#ground-truth-y-casos-borde-sintéticos)
5. [Referencia de la API y Ejemplos cURL](#referencia-de-la-api-y-ejemplos-curl)
6. [Integración de Streaming en Tiempo Real (SSE)](#integración-de-streaming-en-tiempo-real-sse)
7. [Variables de Entorno](#variables-de-entorno)
8. [Pruebas y Verificación](#pruebas-y-verificación)

---

## Características Principales

- **Arquitectura Asíncrona:** Construido sobre FastAPI, SQLAlchemy 2.0 Asyncio y SQLite en modo WAL (*Write-Ahead Logging*) con serialización transaccional mediante cerrojo asíncrono (`db_write_lock`).
- **Población Determinista Inicial:** Generador de datos sintéticos con 180 días de historial financiero coherente y balance matemáticamente exacto (`seed=42`).
- **Simulador Transaccional en Vivo:** Motor en background que genera transacciones financieras realistas de manera continua o bajo demanda manual (`POST /simulacion/tick`).
- **Streaming de Eventos Server-Sent Events (SSE):** Canal de publicación/suscripción desacoplado con colas independientes, amortiguamiento sin pérdidas y latidos periódicos (*heartbeat pings*).
- **CORS Habilitado Totalmente:** Preparado para integración inmediata con SPAs (React, Vue, Svelte, Angular) o agentes de Inteligencia Artificial locales y remotos.

---

## Inicio Rápido / Setup

### Prerrequisitos
- Python 3.10 o superior (o entorno con Nix / `nix-shell`).
- `curl` o navegador web para interactuar con la API.

### Instalación y Ejecución

1. **Bootstrap automatizado mediante el arnés:**
   ```bash
   ./init.sh --bootstrap
   ```
   *Crea el entorno virtual `.venv`, instala dependencias y ejecuta la suite de verificación.*

2. **Ejecutar el servidor de desarrollo:**
   ```bash
   .venv/bin/uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
   ```
   La documentación interactiva OpenAPI (Swagger UI) estará disponible en:
   - **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Auto-Seeding y Regeneración de Datos

- **Auto-población:** Al iniciar la aplicación por primera vez, el ciclo de vida (*lifespan*) detecta si la base de datos está vacía y ejecuta automáticamente el seeder determinista con `SEED_VALUE=42`.
- **Re-seeding manual:** Si deseas reiniciar la base de datos con los datos sintéticos originales en cualquier momento:
  ```bash
  .venv/bin/python -m src.seed --force
  ```

---

## Diccionario de Datos

El modelo relacional está compuesto por 10 tablas interconectadas diseñadas con integridad referencial estricta:

### 1. `clientes`
Información del cliente titular de las cuentas bancarias.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador único autoincremental del cliente. |
| `nombre` | VARCHAR(100) | No | Nombre completo del titular (ej. "Juan Pérez"). |
| `nivel` | VARCHAR(50) | No | Segmento bancario (ej. "Black Tier", "Gold", "Clásico"). |
| `cliente_desde` | DATE | No | Fecha de apertura de la relación bancaria. |
| `ingreso_mensual` | NUMERIC(12, 2) | No | Salario mensual neto declarado (ej. `5000.00`). |
| `dia_pago` | INTEGER | No | Día del mes en que recibe su nómina (ej. `28`). |
| `perfil` | VARCHAR(50) | No | Clasificación del perfil (ej. "persona_dependiente"). |

---

### 2. `cuentas`
Cuentas financieras asociadas a un cliente.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador único de la cuenta. |
| `cliente_id` | INTEGER (FK) | No | Clave foránea referenciando `clientes.id`. |
| `tipo` | VARCHAR(30) | No | Tipo de cuenta ("Ahorro", "Corriente"). |
| `moneda` | VARCHAR(3) | No | Código ISO de la moneda ("PEN", "USD"). |
| `numero_enmascarado` | VARCHAR(30) | No | Número de cuenta visible para usuario (ej. `0011-0123-****-4567`). |
| `cci` | VARCHAR(30) | No | Código de Cuenta Interbancario (20 dígitos). |
| `saldo` | NUMERIC(12, 2) | No | Saldo contable disponible actual. |

---

### 3. `tarjetas`
Tarjetas de débito o crédito vinculadas a las cuentas bancarias.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador de la tarjeta. |
| `cuenta_id` | INTEGER (FK) | No | Clave foránea referenciando `cuentas.id`. |
| `tipo` | VARCHAR(20) | No | "Debito" o "Credito". |
| `ultimos_4_digitos` | VARCHAR(4) | No | Últimos 4 dígitos para visualización segura (ej. `4532`). |
| `vencimiento` | VARCHAR(5) | No | Mes y año de expiración en formato `MM/YY` (ej. `08/29`). |
| `limite` | NUMERIC(12, 2) | No | Línea de crédito aprobada (`0.00` para débito). |
| `fecha_corte` | INTEGER | No | Día del mes de corte de facturación (`0` si débito). |
| `fecha_pago` | INTEGER | No | Día límite de pago de tarjeta (`0` si débito). |

---

### 4. `comercios`
Catálogo de comercios afiliados y plataformas de servicios.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador único del comercio. |
| `nombre_ficticio` | VARCHAR(100) | No | Nombre comercial (ej. "Supermercados Metro", "Netflix"). |
| `categoria` | VARCHAR(50) | No | Categoría principal de gasto ("Alimentación", "Entretenimiento", etc.). |
| `codigo_rubro_mcc` | VARCHAR(4) | No | Merchant Category Code internacional ISO 18245 (ej. `5411`, `4899`). |
| `si_cobra_suscripcion`| BOOLEAN | No | Indica si el comercio suele realizar cobros periódicos recurrentes. |

---

### 5. `pagos_programados`
Servicios domiciliados o programados para débito regular.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador del pago programado. |
| `cuenta_id` | INTEGER (FK) | No | Clave foránea referenciando `cuentas.id`. |
| `servicio` | VARCHAR(100) | No | Nombre del servicio (ej. "Luz del Sur", "Agua Sedapal"). |
| `monto_estimado` | NUMERIC(12, 2) | No | Importe promedio esperado para el recibo. |
| `dia_vencimiento` | INTEGER | No | Día del mes en que vence el servicio. |

---

### 6. `beneficiarios`
Contactos frecuentes registrados para transferencias interbancarias e intra-banco.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador del contacto. |
| `cliente_id` | INTEGER (FK) | No | Clave foránea referenciando `clientes.id`. |
| `alias` | VARCHAR(100) | No | Nombre común o etiqueta (ej. "Mamá", "Carlos Hermano"). |
| `banco` | VARCHAR(50) | No | Entidad bancaria destino ("BCP", "Interbank", "BBVA", etc.). |
| `cci` | VARCHAR(20) | No | Código de Cuenta Interbancario destino (20 dígitos). |

---

### 7. `tipo_cambio`
Registro histórico y cotización de divisas de referencia.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador del registro. |
| `fecha` | DATE | No | Fecha del tipo de cambio (clave única diaria). |
| `compra` | NUMERIC(6, 4) | No | Tipo de cambio compra (ej. `3.7250`). |
| `venta` | NUMERIC(6, 4) | No | Tipo de cambio venta (ej. `3.7550`). |

---

### 8. `eventos_seguridad`
Bitácora de auditoría y ciberseguridad sobre inicios de sesión y accesos.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador del evento de seguridad. |
| `cliente_id` | INTEGER (FK) | No | Clave foránea referenciando `clientes.id`. |
| `tipo` | VARCHAR(50) | No | Tipo de evento (ej. "Login App Móvil", "Intento de acceso IP sospechosa"). |
| `dispositivo` | VARCHAR(100) | No | Agente o modelo de dispositivo (ej. "iPhone 15 Pro", "Linux Firefox"). |
| `ciudad` | VARCHAR(100) | No | Ubicación geográfica estimada (ej. "Lima, Perú", "Moscú, Rusia"). |
| `fecha_hora` | DATETIME | No | Marca temporal precisa UTC del evento. |
| `es_sospechoso` | BOOLEAN | No | Bandera que indica anomalía de seguridad para modelos de fraude. |

---

### 9. `productos_referenciales`
Catálogo de productos bancarios pre-aprobados o sugeridos.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador del producto referencial. |
| `tipo` | VARCHAR(50) | No | Tipo de producto ("Prestamo", "Tarjeta"). |
| `nombre` | VARCHAR(100) | No | Nombre comercial (ej. "Préstamo Personal Simulador"). |
| `tea` | NUMERIC(5, 2) | No | Tasa Efectiva Anual en porcentaje (ej. `14.50`). |
| `tcea` | NUMERIC(5, 2) | No | Tasa de Costo Efectivo Anual en porcentaje (ej. `16.80`). |
| `membresia` | NUMERIC(8, 2) | No | Costo anual de membresía (ej. `350.00`). |

---

### 10. `movimientos`
Libro mayor (*ledger*) de transacciones y movimientos bancarios.

| Campo | Tipo | Nulo | Descripción |
|---|---|---|---|
| `id` | INTEGER (PK) | No | Identificador de la transacción. |
| `cuenta_id` | INTEGER (FK) | No | Clave foránea referenciando `cuentas.id`. |
| `fecha_hora` | DATETIME | No | Fecha y hora de la transacción. |
| `monto` | NUMERIC(12, 2) | No | Importe con signo: positivo para abonos/ingresos, negativo para egresos. |
| `moneda` | VARCHAR(3) | No | Moneda de la transacción ("PEN", "USD"). |
| `descripcion` | VARCHAR(255) | No | Glosa o concepto del movimiento. |
| `comercio_id` | INTEGER (FK) | Sí | Referencia opcional a `comercios.id` (nulo si transferencia particular). |
| `categoria` | VARCHAR(50) | No | Rubro ("Alimentación", "Servicios", "Ingresos", "Tecnología", etc.). |
| `subcategoria` | VARCHAR(50) | No | Sub-clasificación ("Supermercados", "Cafetería", "Streaming", etc.). |
| `canal` | VARCHAR(30) | No | Canal transaccional ("POS", "online", "transferencia", "debito_automatico"). |
| `es_recurrente` | BOOLEAN | No | Indicador de gasto periódico o suscripción. |
| `estado` | VARCHAR(20) | No | Estado contable: "procesado" o "revertido". |

---

## Ground Truth y Casos Borde Sintéticos

El generador determinista (`src/seed.py`) inyecta intencionalmente patrones específicos para evaluar modelos de Machine Learning, agentes conversacionales y detección de fraude financiero:

### 1. Detección de Cobro Duplicado (*Duplicate Charge Detection*)
- **Caso:** Dos transacciones idénticas en comercio, categoría, monto y canal ocurridas con una separación de apenas **20 segundos**.
- **Registro:**
  - Comercio: `Starbucks Coffee`
  - Monto: `-24.50 PEN`
  - Fecha 1: `2026-10-15 14:30:00`
  - Fecha 2: `2026-10-15 14:30:20`
  - Canal: `POS`
  - Estado: `procesado`
- **Utilidad para IA:** Validar que el agente reconozca cargos duplicados accidentales causados por error en terminal de punto de venta.

### 2. Transacción Revertida / Anulada (*Reversed Transaction*)
- **Caso:** Movimiento con estado `"revertido"` cuyo importe **no debe afectar el saldo contable**.
- **Registro:**
  - Comercio: `Supermercados Metro`
  - Monto: `-120.00 PEN`
  - Fecha: `2026-09-12 19:15:00`
  - Descripción: `Supermercados Metro - Compra Anulada`
  - Estado: `revertido`
- **Utilidad para IA:** Evaluar si los motores de cálculo financiero ignoran las transacciones anuladas al computar egresos netos acumulados.

### 3. Gasto Atípico / Anomalía de Importe (*Anomalous Spending*)
- **Caso:** Una compra significativamente superior al promedio habitual de gastos cotidianos (~30 PEN).
- **Registro:**
  - Comercio: `Hiraoka Electrónica`
  - Monto: `-2500.00 PEN`
  - Categoría: `Tecnología`
  - Fecha: `2026-08-20 17:30:00`
  - Descripción: `Hiraoka Electrónica - Laptop Asus Zenbook`
- **Utilidad para IA:** Probar modelos de detección de *outliers* y disparadores de notificaciones proactivas de presupuesto.

### 4. Patrones de Recurrencia y Suscripciones (*Recurring Subscriptions*)
- **Nómina salarial fija:** `+5000.00 PEN` los días 28 de cada mes a las `09:00:00`.
- **Débitos de servicios del hogar:**
  - Día 5: Mantenimiento Edificio (`-250.00 PEN`) y Spotify Premium (`-20.90 PEN`).
  - Día 10: Enel Distribución Recibo Eléctrico (`-135.50 PEN`).
  - Día 12: Netflix Suscripción Estándar (`-44.90 PEN`).
  - Día 15: Sedapal Agua Potable (`-68.20 PEN`).
  - Día 20: Movistar Hogar Fibra Óptica (`-119.90 PEN`).
- **Utilidad para IA:** Validar algoritmos de predicción de flujo de caja y recordatorios de pagos recurrentes.

### 5. Evento de Seguridad Sospechoso (*Suspicious Security Event*)
- **Acceso anómalo:** Intento de acceso desde ubicación geográfica inconsistente (`Moscú, Rusia`) con cliente habitual en `Lima, Perú`.
- **Registro:** `es_sospechoso=True`, dispositivo `Linux Firefox Unknown`.

---

## Referencia de la API y Ejemplos cURL

### 1. Consultar Cuentas y Saldos
```bash
curl -X GET http://localhost:8000/cuentas \
  -H "Accept: application/json"
```

### 2. Consultar Movimientos Filtrados y Paginados
```bash
curl -X GET "http://localhost:8000/cuentas/1/movimientos?tipo=gasto&categoria=Alimentaci%C3%B3n&page=1&page_size=20" \
  -H "Accept: application/json"
```
*Parámetros opcionales:*
- `tipo`: `gasto`, `ingreso` o `transferencia`.
- `categoria`: Nombre exacto de la categoría.
- `fecha_inicio`: Formato ISO `YYYY-MM-DD` o `YYYY-MM-DDTHH:MM:SS`.
- `fecha_fin`: Formato ISO.
- `page`: Número de página (inicio en 1).
- `page_size`: Tamaño de página (1 a 100, default 50).

### 3. Disparar un Tick de Simulación Inmediato
Genera un movimiento instantáneo actualizando el balance y transmitiéndolo a través del stream SSE:
```bash
curl -X POST http://localhost:8000/simulacion/tick \
  -H "Content-Type: application/json" \
  -d '{
    "monto": -45.50,
    "categoria": "Alimentación",
    "subcategoria": "Restaurantes",
    "descripcion": "Almuerzo Ejecutivo",
    "canal": "POS"
  }'
```
*Si se omite el cuerpo del JSON (`{}`), el motor de simulación seleccionará una transacción sintética ponderada al azar.*

### 4. Consultar Estado del Motor de Simulación
```bash
curl -X GET http://localhost:8000/simulacion/status \
  -H "Accept: application/json"
```
**Respuesta:**
```json
{
  "running": true,
  "ticks_executed": 14,
  "last_tick_at": "2026-11-14T21:58:30.123456",
  "active_subscribers": 2
}
```

### 5. Endpoints Adicionales

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/health` | Chequeo de salud del servicio y timestamp UTC. |
| `GET` | `/cliente` | Datos del cliente titular activo. |
| `GET` | `/cuentas/{id}` | Detalle de una cuenta específica por ID. |
| `GET` | `/tarjetas` | Listado de tarjetas de crédito y débito. |
| `GET` | `/comercios` | Catálogo completo de comercios afiliados y MCC. |
| `GET` | `/pagos-programados` | Servicios programados para débito regular. |
| `GET` | `/beneficiarios` | Agenda de beneficiarios para transferencias. |
| `GET` | `/tipo-cambio` | Tipo de cambio compra/venta vigente. |
| `GET` | `/eventos-seguridad` | Bitácora de accesos y eventos de seguridad. |
| `GET` | `/productos-referenciales` | Catálogo de productos y ofertas financieras. |

---

## Integración de Streaming en Tiempo Real (SSE)

La ruta `GET /movimientos/stream` implementa la especificación W3C de **Server-Sent Events** (`text/event-stream`). Transmite en tiempo real cualquier transacción generada por el motor de simulación periódico o ticks manuales, además de un ping de latido (`heartbeat`) cada 15 segundos para mantener vivas las conexiones a través de proxys.

### Escuchar el Stream con cURL
```bash
curl -N http://localhost:8000/movimientos/stream
```

### Integración en Frontend con JavaScript (`EventSource`)

El siguiente fragmento muestra cómo suscribirse desde un navegador o SPA moderna para actualizar la interfaz de usuario en tiempo real:

```javascript
// Conexión al flujo de eventos Server-Sent Events de banca-api
const eventSource = new EventSource("http://localhost:8000/movimientos/stream");

// Escuchar eventos de tipo 'movimiento'
eventSource.addEventListener("movimiento", (event) => {
  try {
    const data = JSON.parse(event.data);
    const movimiento = data.movimiento;
    const nuevoSaldo = data.nuevo_saldo;

    console.log("⚡ Nueva transacción recibida en vivo:", movimiento);
    console.log(`💰 Saldo actualizado de la cuenta ${movimiento.cuenta_id}: S/ ${nuevoSaldo}`);

    // Ejemplo: Añadir la transacción al inicio del feed de la UI
    const container = document.getElementById("transacciones-feed");
    if (container) {
      const item = document.createElement("div");
      item.className = "transaccion-card animacion-fade-in";
      item.innerHTML = `
        <strong>${movimiento.descripcion}</strong>
        <span class="${movimiento.monto < 0 ? 'gasto' : 'ingreso'}">
          ${movimiento.moneda} ${parseFloat(movimiento.monto).toFixed(2)}
        </span>
        <small>${new Date(movimiento.fecha_hora).toLocaleTimeString()}</small>
      `;
      container.prepend(item);
    }
  } catch (err) {
    console.error("Error al procesar payload del evento SSE:", err);
  }
});

// Escuchar latidos de mantenimiento de conexión (opcional)
eventSource.addEventListener("ping", (event) => {
  console.debug("💓 Heartbeat ping recibido del servidor:", event.data);
});

// Manejo de reconexión y errores de red
eventSource.onerror = (error) => {
  console.warn("Conexión SSE interrumpida. EventSource reconectará automáticamente...", error);
};

// Para desconectar cuando el componente se desmonte:
// eventSource.close();
```

---

## Variables de Entorno

La configuración del servicio se gestiona mediante Pydantic Settings (`src/config.py`). Puedes definir estas variables en el entorno o en un archivo `.env`:

| Variable | Tipo | Default | Descripción |
|---|---|---|---|
| `DATABASE_URL` | String | `sqlite+aiosqlite:///./banca.db` | URL de conexión SQLAlchemy asíncrona a la base de datos SQLite. |
| `SEED_VALUE` | Entero | `42` | Semilla determinista utilizada para la generación de datos sintéticos. |
| `SIMULATION_ENABLED` | Booleano | `True` | Habilita o deshabilita el ciclo de fondo de simulación periódica. |
| `SIMULATION_INTERVAL_MIN` | Entero | `10` | Intervalo mínimo en segundos entre transacciones automáticas de simulación. |
| `SIMULATION_INTERVAL_MAX` | Entero | `30` | Intervalo máximo en segundos entre transacciones automáticas de simulación. |

---

## Pruebas y Verificación

El proyecto sigue la disciplina estricta de **Test-Driven Development (TDD)** y utiliza un arnés automatizado de verificación (`init.sh`).

### Ejecutar todas las pruebas con pytest
```bash
.venv/bin/pytest tests -v
```

### Ejecutar la compuerta de verificación del arnés
```bash
# Validar la feature actual F06-documentation
./init.sh --feature F06-documentation

# Validar la integridad de todo el repositorio
./init.sh
```

---

*Desarrollado para el Hackathon BBVA 2026. Diseñado para un desarrollo ágil, transparente y robusto.*
