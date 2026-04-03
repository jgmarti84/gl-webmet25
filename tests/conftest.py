# tests/conftest.py
import os
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ============================================================================
# TEST DATABASE
# ============================================================================

def get_test_db_url() -> str:
    """Build test database URL from environment variables."""
    host = os.getenv("TEST_DB_HOST", "radar_db_test")
    port = os.getenv("TEST_DB_PORT", "5432")
    name = os.getenv("TEST_DB_NAME", "radar_test_db")
    user = os.getenv("TEST_DB_USER", "radar")
    password = os.getenv("TEST_DB_PASSWORD", "radarpass")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


@pytest.fixture(scope="session")
def test_db_engine():
    """Create a SQLAlchemy engine connected to the test database.
    Session scoped: created once for the entire test run.
    """
    engine = create_engine(get_test_db_url())
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_db_engine):
    """Provide a clean database session for each test.
    Function scoped: each test gets a fresh session.
    All changes are rolled back after each test so the
    test database stays clean between tests.
    """
    connection = test_db_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    
    # Only rollback if the transaction is still active.
    # Some code (e.g., COGRegistrar) calls session.rollback() internally,
    # which deassociates the transaction. We must check before rolling back
    # to avoid SQLAlchemy warnings about invalid transactions.
    if transaction.is_active:
        transaction.rollback()
    
    connection.close()


# ============================================================================
# FAKE TIFF FILES
# ============================================================================

def create_fake_tif(path: Path) -> Path:
    """Create a minimal valid GeoTIFF file at the given path.
    Uses random data with EPSG:4326 CRS matching our Output Contract.
    """
    data = np.random.randint(0, 255, (1, 10, 10), dtype=np.uint8)
    transform = from_bounds(
        west=-65.0, south=-35.0,
        east=-60.0, north=-30.0,
        width=10, height=10
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        'w',
        driver='GTiff',
        height=10,
        width=10,
        count=1,
        dtype=np.uint8,
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as dst:
        dst.write(data)
        dst.update_tags(
            radarlib_cmap="viridis",
            vmin="0",
            vmax="255"
        )
    return path


@pytest.fixture(scope="session")
def fake_tif_dir(tmp_path_factory):
    """Create a temporary directory that acts as ROOT_RADAR_PRODUCTS_PATH.
    Session scoped: created once and reused across all tests.
    This is the base_path you pass to COGRegistrar.
    """
    return tmp_path_factory.mktemp("product_output")


@pytest.fixture(scope="function")
def valid_tif_file(fake_tif_dir) -> Path:
    """Create a valid filtered GeoTIFF matching the Output Contract.
    Filename: RMA1_20260401T205000Z_ZDR_00.tif
    Folder:   <fake_tif_dir>/RMA1/2026/04/01/
    """
    path = fake_tif_dir / "RMA1" / "2026" / "04" / "01" / \
           "RMA1_20260401T205000Z_ZDR_00.tif"
    return create_fake_tif(path)


@pytest.fixture(scope="function")
def valid_raw_tif_file(fake_tif_dir) -> Path:
    """Create a valid raw/non-filtered GeoTIFF matching the Output Contract.
    Filename: RMA1_20260401T205000Z_ZDRo_00.tif
    Folder:   <fake_tif_dir>/RMA1/2026/04/01/
    """
    path = fake_tif_dir / "RMA1" / "2026" / "04" / "01" / \
           "RMA1_20260401T205000Z_ZDRo_00.tif"
    return create_fake_tif(path)


@pytest.fixture(scope="function")
def invalid_tif_file(fake_tif_dir) -> Path:
    """Create a file with an invalid filename (does not match Output Contract).
    Used to test that the registrar correctly rejects invalid filenames.
    """
    path = fake_tif_dir / "random_file.tif"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a real tif file")
    return path


@pytest.fixture(scope="function")
def corrupt_tif_file(fake_tif_dir) -> Path:
    """Create a file with a VALID filename but CORRUPT content.
    Used to test that the registrar handles rasterio read failures gracefully.
    Filename matches Output Contract but bytes are garbage.
    """
    path = fake_tif_dir / "RMA1" / "2026" / "04" / "01" / \
           "RMA1_20260401T205000Z_DBZH_00.tif"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a real tif file")
    return path