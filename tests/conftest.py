"""Pytest configuration and fixtures."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_setup_data():
    """Sample setup data for testing."""
    return {
        "id": "test-setup-1",
        "filename": "test_setup.sto",
        "car": "ferrari488gt3evo",
        "track": "spa",
        "provider": "gofast",
    }


@pytest.fixture
def sample_setup_record_data():
    """Sample setup record data for testing."""
    return {
        "id": 12345,
        "download_name": "IR - V1 - Ferrari 488 GT3 Evo - Spa-Francorchamps",
        "download_url": "https://example.com/setup.sto",
        "creation_date": datetime(2024, 1, 15, 10, 30, 0),
        "updated_date": datetime(2024, 1, 20, 14, 45, 0),
        "ver": "26 S1 W8",
        "setup_ver": "1.2.3",
        "changelog": "Updated brake bias",
        "cat": "GT3",
        "series": "IMSA",
    }


# CDA-specific fixtures


@pytest.fixture
def cda_credentials():
    """CDA authentication credentials for testing."""
    return {
        "session_id": "test-session-id-12345",
        "csrf_token": "test-csrf-token-xyz789",
    }


@pytest.fixture
def cda_catalog_response():
    """Sample CDA catalog API response for testing."""
    return {
        "code": 200,
        "data": {
            "porsche-911-gt3-r-992": {
                "watkins-glen-international": {
                    "25S4 IMSA Racing Series": [
                        {
                            "series": 160,
                            "seriesName": "25S4 IMSA Racing Series",
                            "bundle": 630,
                            "week": 1,
                            "laptime": "Dry: 1:49.884",
                        }
                    ]
                },
                "road-america": {
                    "25S4 IMSA Racing Series": [
                        {
                            "series": 160,
                            "seriesName": "25S4 IMSA Racing Series",
                            "bundle": 630,
                            "week": 2,
                            "laptime": "Dry: 2:05.123",
                        }
                    ]
                },
            },
            "ferrari-296-gt3": {
                "spa-francorchamps": {
                    "25S4 GT3 Sprint Series": [
                        {
                            "series": 161,
                            "seriesName": "25S4 GT3 Sprint Series",
                            "bundle": 631,
                            "week": 3,
                            "laptime": None,
                        }
                    ]
                },
            },
        },
    }


@pytest.fixture
def cda_setup_info_data():
    """Sample CDASetupInfo data for testing."""
    return {
        "series_id": 160,
        "series_name": "25S4 IMSA Racing Series",
        "bundle_id": 630,
        "week_number": 1,
        "car_slug": "porsche-911-gt3-r-992",
        "track_slug": "watkins-glen-international",
        "track_name": "Watkins Glen International",
        "laptime": "Dry: 1:49.884",
    }


@pytest.fixture
def cda_setup_record_data():
    """Sample CDA SetupRecord data for testing."""
    return {
        "id": 123456789,
        "download_name": "CDA - Porsche 911 Gt3 R 992 - Watkins Glen International",
        "download_url": "https://delta.coachdaveacademy.com/iracing/install/160/630/1/setups/zip",
        "creation_date": datetime(2024, 1, 15, 10, 30, 0),
        "updated_date": datetime(2024, 1, 15, 10, 30, 0),
        "ver": "25S4 W1",
        "setup_ver": "1.0",
        "changelog": "",
        "cat": "IMSA",
        "series": "IMSA",
    }
