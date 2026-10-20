FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/utilities/*

# Install database package dependencies
COPY database/requirements.txt /tmp/db_requirements.txt
RUN pip install --no-cache-dir -r /tmp/db_requirements.txt

# Install api dependencies
# Note: includes rasterio and numpy needed for fake tif generation
COPY api/requirements.txt /tmp/api_requirements.txt
RUN pip install --no-cache-dir -r /tmp/api_requirements.txt

# Install indexer dependencies
COPY indexer/requirements.txt /tmp/indexer_requirements.txt
RUN pip install --no-cache-dir -r /tmp/indexer_requirements.txt

# Install test dependencies
COPY tests/requirements.txt /tmp/test_requirements.txt
RUN pip install --no-cache-dir -r /tmp/test_requirements.txt

# Install playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy database package
COPY database/radar_db/ /app/radar_db/

# Copy api source
COPY api/ /app/api/

# Copy indexer source
COPY indexer/indexer/ /app/indexer/

# Copy tracking sidecar source.
# Only the parts that do not need gl-tracker are testable here — volume
# resolution, config mapping, schemas. The driver and GeoJSON serialisation
# need gl-tracker on the path and are exercised in the tracking image itself.
COPY tracking/tracking_api/ /app/tracking_api/

# Copy tests
COPY tests/ /app/tests/

ENV PYTHONPATH=/app

WORKDIR /app