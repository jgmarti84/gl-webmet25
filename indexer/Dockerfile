# indexer/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install GDAL and dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

COPY indexer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy database package (shared dependency)
COPY database/radar_db/ ./radar_db/

# Copy indexer code
COPY indexer/indexer/ ./indexer/

ENV PYTHONPATH=/app

CMD ["python", "-m", "indexer.main"]