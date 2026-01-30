# database/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2 and PostGIS support
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY radar_db/ ./radar_db/
COPY seed_data/ ./seed_data/
COPY alembic.ini .
COPY migrations/ ./migrations/

# Ensure versions directory exists (even if empty on host)
RUN mkdir -p ./migrations/versions

# Set Python path so imports work correctly
ENV PYTHONPATH=/app

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "radar_db.manage", "check"]