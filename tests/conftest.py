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
