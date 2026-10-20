"""Tests for the NC cube filename parser.

The cube filename is the only source of metadata the indexer has — it never
opens the file — so these cases pin the contract with radarlib's writer.
"""

from datetime import datetime, timezone

import pytest

from indexer.parser import NCCubeFilenameParser, ParsedNCCubeInfo


@pytest.mark.parametrize("filename, expected", [
    (
        "RMA1_0315_01_20260401T205000Z_NCCUBE.nc",
        ParsedNCCubeInfo(
            radar_code="RMA1",
            strategy="0315",
            vol_nr="01",
            observation_time=datetime(2026, 4, 1, 20, 50, 0, tzinfo=timezone.utc),
        ),
    ),
    (
        "RMA5_0315_01_20261013T140818Z_NCCUBE.nc",
        ParsedNCCubeInfo(
            radar_code="RMA5",
            strategy="0315",
            vol_nr="01",
            observation_time=datetime(2026, 10, 13, 14, 8, 18, tzinfo=timezone.utc),
        ),
    ),
    (
        "AR8_1000_02_20260401T205000Z_NCCUBE.nc",
        ParsedNCCubeInfo(
            radar_code="AR8",
            strategy="1000",
            vol_nr="02",
            observation_time=datetime(2026, 4, 1, 20, 50, 0, tzinfo=timezone.utc),
        ),
    ),
])
def test_valid_filenames(filename, expected):
    assert NCCubeFilenameParser().parse(filename) == expected


def test_accepts_full_path():
    """The watcher passes absolute paths, not bare names."""
    result = NCCubeFilenameParser().parse(
        "/nccube/RMA1/2026/04/01/RMA1_0315_01_20260401T205000Z_NCCUBE.nc"
    )
    assert result.radar_code == "RMA1"


def test_observation_time_is_timezone_aware():
    """A naive datetime here would compare wrongly against DB timestamps."""
    result = NCCubeFilenameParser().parse("RMA1_0315_01_20260401T205000Z_NCCUBE.nc")
    assert result.observation_time.tzinfo is not None


def test_keeps_second_precision():
    """Volumes are ~9 min apart but unaligned; rounding would collide."""
    result = NCCubeFilenameParser().parse("RMA5_0315_01_20261013T140818Z_NCCUBE.nc")
    assert result.observation_time.second == 18


@pytest.mark.parametrize("filename", [
    "RMA1_0315_01_20260401T205000Z_TOPS_CORES.geojson",  # different artifact
    "RMA1_0315_01_20260401T205000Z_DBZH.tif",            # a COG
    "RMA1_0315_01_20260401T205000Z_NCCUBE.nc.tmp",       # half-written
    "RMA1_0315_01_20260401205000_NCCUBE.nc",             # missing T/Z
    "RMA1_315_01_20260401T205000Z_NCCUBE.nc",            # 3-digit strategy
    "RMA1_0315_1_20260401T205000Z_NCCUBE.nc",            # 1-digit volume
    "RMA1_0315_01_NCCUBE.nc",                            # no timestamp
    "NCCUBE.nc",
    "",
])
def test_invalid_filenames_raise(filename):
    with pytest.raises(ValueError):
        NCCubeFilenameParser().parse(filename)


def test_error_message_names_the_expected_pattern():
    """The watcher logs this; it should say what was expected."""
    with pytest.raises(ValueError, match="NCCUBE"):
        NCCubeFilenameParser().parse("nonsense.nc")
