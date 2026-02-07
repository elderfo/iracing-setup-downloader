"""Pytest configuration and fixtures."""

import tempfile
from datetime import UTC, datetime
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


# Track Titan-specific fixtures


@pytest.fixture
def tt_credentials():
    """Track Titan authentication credentials for testing."""
    return {
        "access_token": "test-cognito-jwt-token-12345",
        "user_id": "896a9f9d-ee3e-40eb-b9b6-2279c8db7302",
    }


@pytest.fixture
def tt_setups_response():
    """Sample Track Titan setups API response for testing."""
    return {
        "success": True,
        "status": 200,
        "data": {
            "setups": [
                {
                    "id": "f28c1355-b9a6-4a6b-8fc7-02afed6fd47d",
                    "title": "Global Mazda MX-5 Cup (PCC) Mount Panorama Circuit",
                    "cardImage": {
                        "_type": "image",
                        "asset": {"_ref": "image-abc-png", "_type": "reference"},
                    },
                    "price": {
                        "currency": "USD",
                        "displayPrice": "4.99",
                        "price_in_minor_units": 499,
                    },
                    "setupCombos": [
                        {
                            "game": {"gameId": "iRacing", "name": "iRacing"},
                            "track": {
                                "name": "Mount Panorama Circuit",
                                "trackId": "bathurst",
                            },
                            "_updatedAt": "2026-02-02T02:43:09Z",
                            "car": {
                                "name": "Global Mazda MX-5 Cup",
                                "carId": "mx-5_cup",
                                "carShorthand": "mx5 mx52016",
                            },
                        }
                    ],
                    "description": [],
                    "telemetry": {"userId": "abc", "sessionId": "xyz"},
                    "lastUpdatedAt": 1770000194000,
                    "period": {
                        "week": "8",
                        "endDate": "2026-02-10T01:00:00.000Z",
                        "year": 2026,
                        "name": "iRacing Season 1 Week 8 2026",
                        "season": "1",
                        "_id": "period-1",
                        "startDate": "2026-02-01T00:45:53.130Z",
                    },
                    "config": [
                        {
                            "gameId": "iRacing",
                            "trackId": "bathurst",
                            "carId": "mx-5_cup",
                            "carShorthand": "mx5 mx52016",
                        }
                    ],
                    "hotlapLink": None,
                    "trackGuideLink": None,
                    "hasWetSetup": True,
                    "hymoDriver": {"driverName": "William Chadwick"},
                    "hymoSeries": {"seriesName": "Production Car Challenge"},
                    "isBundle": False,
                    "isActive": True,
                },
                {
                    "id": "c38dff77-6b78-415a-bfa1-65894d0d1ffd",
                    "title": "Indycar Dallara IR18 Mid-Ohio",
                    "cardImage": None,
                    "price": {
                        "currency": "USD",
                        "displayPrice": "4.99",
                        "price_in_minor_units": 499,
                    },
                    "setupCombos": [
                        {
                            "game": {"gameId": "iRacing", "name": "iRacing"},
                            "track": {
                                "name": "Mid-Ohio Sports Car Course - Full Course",
                                "trackId": "mid-ohio",
                            },
                            "_updatedAt": "2026-02-02T02:43:09Z",
                            "car": {
                                "name": "Indycar Dallara IR18",
                                "carId": "dallara-ir18",
                                "carShorthand": "dallarair18",
                            },
                        }
                    ],
                    "description": [],
                    "telemetry": None,
                    "lastUpdatedAt": 1770000194000,
                    "period": {
                        "week": "8",
                        "endDate": "2026-02-10T01:00:00.000Z",
                        "year": 2026,
                        "name": "iRacing Season 1 Week 8 2026",
                        "season": "1",
                        "_id": "period-1",
                        "startDate": "2026-02-01T00:45:53.130Z",
                    },
                    "config": [
                        {
                            "gameId": "iRacing",
                            "trackId": "mid-ohio",
                            "carId": "dallara-ir18",
                            "carShorthand": "dallarair18",
                        }
                    ],
                    "hotlapLink": None,
                    "trackGuideLink": None,
                    "hasWetSetup": False,
                    "hymoDriver": {"driverName": "Test Driver"},
                    "hymoSeries": {"seriesName": "INDYCAR Series"},
                    "isBundle": False,
                    "isActive": True,
                },
            ]
        },
    }


@pytest.fixture
def tt_setup_info_data():
    """Sample TracKTitanSetupInfo data for testing."""
    return {
        "setup_uuid": "f28c1355-b9a6-4a6b-8fc7-02afed6fd47d",
        "car_id": "mx-5_cup",
        "track_id": "bathurst",
        "car_name": "Global Mazda MX-5 Cup",
        "track_name": "Mount Panorama Circuit",
        "car_shorthand": "mx5 mx52016",
        "series_name": "Production Car Challenge",
        "driver_name": "William Chadwick",
        "season": "1",
        "week": "8",
        "year": 2026,
        "has_wet_setup": True,
        "is_bundle": False,
    }


@pytest.fixture
def tt_setup_record_data():
    """Sample Track Titan SetupRecord data for testing."""
    return {
        "id": 123456789,
        "download_name": "IR - V1 - Global Mazda MX-5 Cup - Mount Panorama Circuit",
        "download_url": "https://services.tracktitan.io/api/v1/user/896a9f9d-ee3e-40eb-b9b6-2279c8db7302/setup/f28c1355-b9a6-4a6b-8fc7-02afed6fd47d/download",
        "creation_date": datetime(2026, 2, 2, 2, 43, 9, tzinfo=UTC),
        "updated_date": datetime(2026, 2, 2, 2, 43, 9, tzinfo=UTC),
        "ver": "26S1 W8",
        "setup_ver": "1.0",
        "changelog": "",
        "cat": "PCC",
        "series": "PCC",
    }
