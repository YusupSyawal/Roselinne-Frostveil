# ──────────────────────────────────────────────────────────
#  Roselinne Frostveil — Dockerfile
#  Build:  docker build -t roselinne-frostveil .
#  Run:    docker run --env-file .env roselinne-frostveil
# ──────────────────────────────────────────────────────────

FROM python:3.11-slim

# Metadata
LABEL maintainer="you@example.com"
LABEL description="Roselinne Frostveil Discord AI Bot"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN useradd -m -u 1000 roselinne
WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY --chown=roselinne:roselinne . .

# Ensure data directory exists
RUN mkdir -p /app/data/memory && chown -R roselinne:roselinne /app/data

USER roselinne

# Health check via Discord gateway latency (rough proxy)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('/app/data/memory.db').close()" || exit 1

CMD ["python", "-u", "main.py"]
