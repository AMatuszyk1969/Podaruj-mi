FROM python:3.11-slim

# System dependencies (libmagic for file type validation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Poetry
RUN pip install poetry==1.8.4 --no-cache-dir

# Copy dependency files first (layer caching)
COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev, no venv – we're in a container)
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

# Copy application source
COPY . .

# Create non-root user for security
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Migracje, potem serwer. $PORT wstrzykiwany przez platformę (Render), lokalnie 8000.
# --proxy-headers/--forwarded-allow-ips: poprawne https w linkach maili i URL-ach avatarów za proxy.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
