# =============================================================================
# AI Gateway - Multi-stage Dockerfile
# =============================================================================
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python build tool
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements first for better caching
COPY requirements.txt .

# Pre-install dependencies (creates wheel cache)
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# =============================================================================
# Stage 2: Runtime
FROM python:3.11-slim AS runtime

# Security: Run as non-root user
RUN groupadd --gid 1000 appgroup && useradd --uid 1000 --gid 1000 --shell /bin/bash appuser

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built wheels from builder
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir --find-links=/wheels /wheels/*.whl

# Install playwright chromium (if needed)
RUN pip install --no-cache-dir playwright \
    && playwright install --with-deps chromium \
    && playwright install-deps chromium \
    || true

# Copy application
COPY --chown=appuser:appgroup app/ ./app/

# Create data directory
RUN mkdir -p /app/data && chown appuser:appgroup /app/data

# Switch to non-root user
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
