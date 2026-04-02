FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install database package dependencies
COPY database/requirements.txt /tmp/db_requirements.txt
RUN pip install --no-cache-dir -r /tmp/db_requirements.txt

# Install api dependencies
COPY api/requirements.txt /tmp/api_requirements.txt
RUN pip install --no-cache-dir -r /tmp/api_requirements.txt

# Install test dependencies
COPY tests/requirements.txt /tmp/test_requirements.txt
RUN pip install --no-cache-dir -r /tmp/test_requirements.txt

# Install playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy database package directly (no pip install, just like other services)
COPY database/radar_db/ /app/radar_db/

# Copy api source
COPY api/ /app/api/

# Copy tests
COPY tests/ /app/tests/

# Set PYTHONPATH exactly like other services do
ENV PYTHONPATH=/app

WORKDIR /app