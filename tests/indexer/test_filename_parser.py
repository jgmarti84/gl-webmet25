import pytest
from indexer.parser import COGFilenameParser
from indexer.parser import ParsedCOGInfo
from datetime import datetime

# Test cases for valid filenames
@pytest.mark.parametrize("filename, expected", [
    (
        "RMA1_20260401T205000Z_ZDR_00.tif", 
        ParsedCOGInfo(
            radar_code="RMA1", 
            product_key="ZDR", 
            observation_time=datetime(2026, 4, 1, 20, 50, 0), 
            elevation_angle=0.0, 
            is_valid=True, 
            error=None
        )
    ),
    (
        "RMA2_20260401T205000Z_COLMAXo_00.tif",
        ParsedCOGInfo(
            radar_code="RMA2", 
            product_key="COLMAXo", 
            observation_time=datetime(2026, 4, 1, 20, 50, 0), 
            elevation_angle=0.0, 
            is_valid=True, 
            error=None
        )    
    ),
])
def test_valid_filenames(filename, expected):
    parser = COGFilenameParser()
    result = parser.parse(filename)
    assert result == expected

# Test cases for invalid filenames
@pytest.mark.parametrize("filename", [
    "RMA1_20260401T205000Z_ZDR.tif",  # Missing elevation
    "RMA1_20260401T205000Z_ZDR_XX.tif",  # Invalid elevation
    "RMA1_20260401T205000Z_.tif",  # Missing field
    "RMA1_20260401T205000Z_ZDR_00.png",  # Deprecated extension
    "RMA1_20260401T205000Z_ZDR_00",  # Missing extension
])
def test_invalid_filenames(filename):
    parser = COGFilenameParser()
    result = parser.parse(filename)
    assert result.error is not None