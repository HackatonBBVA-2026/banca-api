# Multi-stage or single-stage optimized python-slim container for Dokploy/Coolify/Docker
FROM python:3.11-slim

# Install curl for container healthcheck and minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set python runtime environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    DATABASE_URL=sqlite+aiosqlite:////app/data/banca.db

WORKDIR /app

# Install dependencies first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create persistent data directory with permissions for SQLite WAL files
RUN mkdir -p /app/data && chmod 777 /app/data

# Copy application source code
COPY . /app

# Expose HTTP API port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default startup command
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
