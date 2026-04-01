# indexer/Dockerfile
FROM python:3.11-alpine

WORKDIR /app

# Install system dependencies for rasterio and PostgreSQL
RUN apk add --no-cache \
    postgresql-client \
    gdal-dev \
    build-base \
    && pip install --upgrade pip setuptools wheel

COPY indexer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy database package (shared dependency)
COPY database/radar_db/ ./radar_db/

# Copy indexer code
COPY indexer/indexer/ ./indexer/

ENV PYTHONPATH=/app

CMD ["python", "-m", "indexer.main"]