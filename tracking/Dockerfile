# tracking/Dockerfile
#
# On-demand storm tracking sidecar.
#
#   nccubes table + NC cube files  ->  gl-tracker  ->  GeoJSON
#
# gl-tracker is consumed READ-ONLY, as a library. It is cloned at a pinned ref
# rather than pip-installed because it currently ships no packaging metadata
# (no pyproject.toml / setup.py). When it gains some, the clone below becomes a
# one-line `pip install git+...`.
#
# This image deliberately does NOT carry radarlib's gridding stack
# (arm-pyart, pyproj, xarray, matplotlib, ...). Gridding now happens in
# radarlib's product daemon; the sidecar only reads the cubes it produced.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# System libraries with no pip equivalent:
#   libgdal-dev                osgeo bindings — tathu's core dependency
#   libgeos-dev                shapely
#   libspatialindex-dev        rtree, used by tathu.tracking.system
#   libsqlite3-mod-spatialite  tathu.io.spatialite is imported at module scope
#                              by gl-tracker's pipeline.py. We never construct
#                              its Outputter, but the import must not fail.
#   git                        to fetch gl-tracker
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      git \
      libpq-dev \
      gdal-bin \
      libgdal-dev \
      libgeos-dev \
      libspatialindex-dev \
      libsqlite3-mod-spatialite \
      proj-bin \
    && rm -rf /var/lib/apt/lists/*

ENV CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal

# Python GDAL bindings must match the system GDAL version exactly
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir "GDAL==$(gdal-config --version)"

# TATHU is not on PyPI. Upstream installs it with --no-deps on top of a conda
# env; we do the same and supply only the subset gl-tracker's import path
# actually reaches.
RUN pip install --no-cache-dir --no-deps git+https://github.com/uba/tathu.git \
 && pip install --no-cache-dir \
      numpy \
      scipy \
      scikit-image \
      opencv-python-headless \
      affine \
      pathos \
      rasterstats \
      rtree \
      shapely \
      netCDF4

WORKDIR /app

COPY tracking/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# gl-tracker, read-only, at a pinned ref.
ARG GL_TRACKER_REPO=https://github.com/jgmarti84/gl-tracker.git
ARG GL_TRACKER_REF=main
RUN git clone --depth 1 --branch "${GL_TRACKER_REF}" "${GL_TRACKER_REPO}" /opt/gl-tracker \
 && rm -rf /opt/gl-tracker/.git

# Shared DB package, same pattern as api/ and indexer/
COPY database/radar_db/ ./radar_db/

# Sidecar code. Service code lives inside the tracking_api package on purpose:
# gl-tracker's modules are flat top-level names, so a top-level module here
# sharing one of those names would shadow it depending on sys.path order.
#
# The rule is therefore: no module directly in /app may be named any of
#   config  estado  filtro_convectivo  gate  grilla  h0_wrf  operativo  pipeline
#
# smoke_driver sits at the top level deliberately — it is a standalone script,
# not importable service code, and its name collides with nothing.
COPY tracking/tracking_api/ ./tracking_api/
COPY tracking/smoke_driver.py ./smoke_driver.py

ENV PYTHONPATH=/app:/opt/gl-tracker

EXPOSE 8001

CMD ["uvicorn", "tracking_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
