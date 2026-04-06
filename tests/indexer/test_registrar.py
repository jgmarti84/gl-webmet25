from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from indexer.registrar import COGRegistrar
from radar_db.models import RadarCOG, COGStatus


# ---------------------------------------------------------------------------
# Happy path — valid filtered file
# ---------------------------------------------------------------------------

def test_register_valid_file_returns_integer_id(test_db_session, valid_tif_file, fake_tif_dir):
    """register_file() with a valid COG must return a non-None integer id."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    result = registrar.register_file(valid_tif_file)
    assert result is not None
    assert isinstance(result, int)


def test_register_valid_file_creates_db_record(test_db_session, valid_tif_file, fake_tif_dir):
    """register_file() must create exactly one RadarCOG record in the database."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    assert record is not None


def test_register_valid_file_correct_radar_code(test_db_session, valid_tif_file, fake_tif_dir):
    """Registered RadarCOG must have radar_code == 'RMA1'."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    assert record.radar_code == "RMA1"


def test_register_valid_file_correct_file_path(test_db_session, valid_tif_file, fake_tif_dir):
    """Registered RadarCOG must store a relative file_path (not absolute)."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    expected_rel_path = str(valid_tif_file.relative_to(fake_tif_dir))
    assert record.file_path == expected_rel_path
    # Must not be an absolute path
    assert not record.file_path.startswith("/")


def test_register_valid_file_correct_observation_time(test_db_session, valid_tif_file, fake_tif_dir):
    """Registered RadarCOG must have observation_time parsed from filename."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    # RMA1_20260401T205000Z_ZDR_00.tif → 2026-04-01 20:50:00 UTC
    assert record.observation_time.year == 2026
    assert record.observation_time.month == 4
    assert record.observation_time.day == 1
    assert record.observation_time.hour == 20
    assert record.observation_time.minute == 50
    assert record.observation_time.second == 0


def test_register_valid_file_status_is_available(test_db_session, valid_tif_file, fake_tif_dir):
    """Registered RadarCOG must have status == AVAILABLE."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    assert record.status == COGStatus.AVAILABLE


def test_register_valid_file_polarimetric_var_is_zdr(test_db_session, valid_tif_file, fake_tif_dir):
    """Registered RadarCOG must store polarimetric_var == 'ZDR'."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    assert record.polarimetric_var == "ZDR"


# ---------------------------------------------------------------------------
# Happy path — raw/non-filtered file (o suffix)
# ---------------------------------------------------------------------------

def test_register_raw_file_returns_integer_id(test_db_session, valid_raw_tif_file, fake_tif_dir):
    """register_file() with a raw (ZDRo) COG must return a non-None integer id."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    result = registrar.register_file(valid_raw_tif_file)
    assert result is not None
    assert isinstance(result, int)


def test_register_raw_file_polarimetric_var_has_o_suffix(test_db_session, valid_raw_tif_file, fake_tif_dir):
    """Registered RadarCOG for raw file must store polarimetric_var ending in 'o'."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_raw_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    assert record.polarimetric_var.endswith("o"), (
        f"Expected polarimetric_var to end with 'o', got '{record.polarimetric_var}'"
    )


def test_register_raw_file_polarimetric_var_is_zdro(test_db_session, valid_raw_tif_file, fake_tif_dir):
    """Registered RadarCOG for raw file must store polarimetric_var == 'ZDRo'."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_raw_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    assert record.polarimetric_var == "ZDRo"


# ---------------------------------------------------------------------------
# Duplicate file handling
# ---------------------------------------------------------------------------

def test_register_same_file_twice_returns_none_second_time(test_db_session, valid_tif_file, fake_tif_dir):
    """register_file() called twice on the same file must return None the second time."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))

    first = registrar.register_file(valid_tif_file)
    assert first is not None

    second = registrar.register_file(valid_tif_file)
    assert second is None


def test_register_same_file_twice_creates_only_one_record(test_db_session, valid_tif_file, fake_tif_dir):
    """Registering the same file twice must not create duplicate RadarCOG records."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))

    registrar.register_file(valid_tif_file)
    registrar.register_file(valid_tif_file)

    rel_path = str(valid_tif_file.relative_to(fake_tif_dir))
    count = test_db_session.query(RadarCOG).filter_by(file_path=rel_path).count()
    assert count == 1


# ---------------------------------------------------------------------------
# Invalid file handling
# ---------------------------------------------------------------------------

def test_register_invalid_filename_returns_none(test_db_session, invalid_tif_file, fake_tif_dir):
    """register_file() with an invalid filename must return None."""
    # invalid_tif_file is named random_file.tif — fails the parser
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    result = registrar.register_file(invalid_tif_file)
    assert result is None


def test_register_invalid_filename_creates_no_db_record(test_db_session, invalid_tif_file, fake_tif_dir):
    """register_file() with an invalid filename must not create any RadarCOG record."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    registrar.register_file(invalid_tif_file)

    count = test_db_session.query(RadarCOG).filter_by(
        file_name=invalid_tif_file.name
    ).count()
    assert count == 0


# ---------------------------------------------------------------------------
# Transaction rollback on failure
# ---------------------------------------------------------------------------

def test_register_file_rolls_back_on_db_error(
    test_db_session, valid_tif_file, fake_tif_dir, monkeypatch
):
    """If session.flush() raises, register_file() must return None
    and the session must remain usable after the failure.
    """
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))

    # Force flush to raise so we can verify rollback behaviour
    original_flush = test_db_session.flush

    def raise_on_flush(*args, **kwargs):
        raise SQLAlchemyError("Simulated DB failure")

    monkeypatch.setattr(test_db_session, "flush", raise_on_flush)

    result = registrar.register_file(valid_tif_file)

    # Must return None, not raise
    assert result is None

    # Restore flush so we can query the database again
    monkeypatch.setattr(test_db_session, "flush", original_flush)

    # Session must still be usable after the failure.
    # Re-open a savepoint since registrar called rollback() internally.
    test_db_session.begin_nested()

    rel_path = str(valid_tif_file.relative_to(fake_tif_dir))
    count = test_db_session.query(RadarCOG).filter_by(file_path=rel_path).count()
    assert count == 0


# ---------------------------------------------------------------------------
# COG metadata extraction (rasterio fields)
# ---------------------------------------------------------------------------

def test_register_valid_file_extracts_crs(test_db_session, valid_tif_file, fake_tif_dir):
    """Registered RadarCOG must have a non-None crs extracted from the GeoTIFF."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    assert record.crs is not None
    assert "4326" in record.crs  # conftest creates GeoTIFFs in EPSG:4326


def test_register_valid_file_extracts_width_and_height(test_db_session, valid_tif_file, fake_tif_dir):
    """Registered RadarCOG must have width and height set from the GeoTIFF."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    # conftest creates a 10x10 GeoTIFF
    assert record.width == 10
    assert record.height == 10


def test_register_valid_file_extracts_cog_cmap(test_db_session, valid_tif_file, fake_tif_dir):
    """Registered RadarCOG must have cog_cmap extracted from GeoTIFF radarlib tags."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    # conftest sets radarlib_cmap="viridis" in the fake TIF tags
    assert record.cog_cmap == "viridis"


def test_register_valid_file_stores_file_size(test_db_session, valid_tif_file, fake_tif_dir):
    """Registered RadarCOG must store a positive file_size_bytes."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    cog_id = registrar.register_file(valid_tif_file)
    assert cog_id is not None

    record = test_db_session.query(RadarCOG).filter_by(id=cog_id).first()
    assert record.file_size_bytes is not None
    assert record.file_size_bytes > 0


# ---------------------------------------------------------------------------
# Corrupt file handling (valid filename, corrupt content) — Risk #4
# ---------------------------------------------------------------------------

def test_register_corrupt_tif_returns_none(test_db_session, corrupt_tif_file, fake_tif_dir):
    """register_file() with a valid filename but corrupt content must return None."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    result = registrar.register_file(corrupt_tif_file)
    assert result is None


def test_register_corrupt_tif_creates_no_db_record(test_db_session, corrupt_tif_file, fake_tif_dir):
    """register_file() with corrupt content must not create any RadarCOG record."""
    registrar = COGRegistrar(test_db_session, base_path=str(fake_tif_dir))
    registrar.register_file(corrupt_tif_file)

    rel_path = str(corrupt_tif_file.relative_to(fake_tif_dir))
    count = test_db_session.query(RadarCOG).filter_by(file_path=rel_path).count()
    assert count == 0