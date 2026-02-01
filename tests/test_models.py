"""Tests for the models module."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from iracing_setup_downloader.models import Setup, SetupRecord


class TestSetup:
    """Tests for the Setup model."""

    def test_setup_creation(self, sample_setup_data):
        """Test creating a Setup instance."""
        setup = Setup(**sample_setup_data)

        assert setup.id == "test-setup-1"
        assert setup.filename == "test_setup.sto"
        assert setup.car == "ferrari488gt3evo"
        assert setup.track == "spa"
        assert setup.provider == "gofast"

    def test_setup_str_representation(self, sample_setup_data):
        """Test the string representation of a Setup."""
        setup = Setup(**sample_setup_data)

        assert str(setup) == "ferrari488gt3evo/spa/test_setup.sto"

    def test_setup_with_timestamps(self, sample_setup_data):
        """Test creating a Setup with timestamps."""
        now = datetime.now()
        sample_setup_data["created_at"] = now
        sample_setup_data["updated_at"] = now

        setup = Setup(**sample_setup_data)

        assert setup.created_at == now
        assert setup.updated_at == now

    def test_setup_with_metadata(self, sample_setup_data):
        """Test creating a Setup with metadata."""
        sample_setup_data["metadata"] = {"season": "2024S1", "week": 5}

        setup = Setup(**sample_setup_data)

        assert setup.metadata["season"] == "2024S1"
        assert setup.metadata["week"] == 5


class TestSetupRecord:
    """Tests for the SetupRecord model."""

    def test_setup_record_creation(self, sample_setup_record_data):
        """Test creating a SetupRecord instance."""
        record = SetupRecord(**sample_setup_record_data)

        assert record.id == 12345
        assert (
            record.download_name == "IR - V1 - Ferrari 488 GT3 Evo - Spa-Francorchamps"
        )
        assert record.download_url == "https://example.com/setup.sto"
        assert isinstance(record.creation_date, datetime)
        assert isinstance(record.updated_date, datetime)
        assert record.ver == "26 S1 W8"
        assert record.setup_ver == "1.2.3"
        assert record.changelog == "Updated brake bias"
        assert record.cat == "GT3"
        assert record.series == "IMSA"

    def test_car_property_standard_format(self, sample_setup_record_data):
        """Test car property extraction with standard format."""
        record = SetupRecord(**sample_setup_record_data)

        assert record.car == "Ferrari 488 GT3 Evo"

    def test_car_property_different_version(self, sample_setup_record_data):
        """Test car property extraction with different version number."""
        sample_setup_record_data["download_name"] = (
            "IR - V2 - Porsche 911 GT3 R - Watkins Glen"
        )
        record = SetupRecord(**sample_setup_record_data)

        assert record.car == "Porsche 911 GT3 R"

    def test_car_property_multi_word_car_name(self, sample_setup_record_data):
        """Test car property extraction with multi-word car name."""
        sample_setup_record_data["download_name"] = (
            "IR - V1 - Audi R8 LMS GT3 Evo II - Nürburgring"
        )
        record = SetupRecord(**sample_setup_record_data)

        assert record.car == "Audi R8 LMS GT3 Evo II"

    def test_car_property_edge_case_extra_spaces(self, sample_setup_record_data):
        """Test car property extraction with extra whitespace."""
        sample_setup_record_data["download_name"] = (
            "IR  -  V1  -  BMW M4 GT3  -  Road Atlanta"
        )
        record = SetupRecord(**sample_setup_record_data)

        assert record.car == "BMW M4 GT3"

    def test_car_property_invalid_format(self, sample_setup_record_data):
        """Test car property with invalid format returns empty string."""
        sample_setup_record_data["download_name"] = "Invalid Format"
        record = SetupRecord(**sample_setup_record_data)

        assert record.car == ""

    def test_car_property_fallback_parsing(self, sample_setup_record_data):
        """Test car property fallback parsing with non-standard format."""
        sample_setup_record_data["download_name"] = "IR - V1 - McLaren 720S GT3 - Track"
        record = SetupRecord(**sample_setup_record_data)

        assert record.car == "McLaren 720S GT3"

    def test_car_property_fallback_no_regex_match(self, sample_setup_record_data):
        """Test car property fallback when regex doesn't match but has enough parts."""
        # Regex won't match because there's no version number (V\d+)
        sample_setup_record_data["download_name"] = "IR-XX-BMW M4 GT3-Daytona"
        record = SetupRecord(**sample_setup_record_data)

        # Should fall back to simple parsing: parts[2]
        assert record.car == "BMW M4 GT3"

    def test_track_property_standard_format(self, sample_setup_record_data):
        """Test track property extraction with standard format."""
        record = SetupRecord(**sample_setup_record_data)

        assert record.track == "Spa-Francorchamps"

    def test_track_property_multi_word_track(self, sample_setup_record_data):
        """Test track property extraction with multi-word track name."""
        sample_setup_record_data["download_name"] = (
            "IR - V1 - Ferrari 488 GT3 Evo - Road America"
        )
        record = SetupRecord(**sample_setup_record_data)

        assert record.track == "Road America"

    def test_track_property_hyphenated_track(self, sample_setup_record_data):
        """Test track property extraction with hyphenated track name."""
        sample_setup_record_data["download_name"] = (
            "IR - V1 - Ferrari 488 GT3 Evo - Circuit de Barcelona-Catalunya"
        )
        record = SetupRecord(**sample_setup_record_data)

        assert record.track == "Circuit de Barcelona-Catalunya"

    def test_track_property_edge_case_extra_spaces(self, sample_setup_record_data):
        """Test track property extraction with extra whitespace."""
        sample_setup_record_data["download_name"] = (
            "IR  -  V1  -  BMW M4 GT3  -  Road Atlanta"
        )
        record = SetupRecord(**sample_setup_record_data)

        assert record.track == "Road Atlanta"

    def test_track_property_invalid_format(self, sample_setup_record_data):
        """Test track property with invalid format returns empty string."""
        sample_setup_record_data["download_name"] = "Invalid Format"
        record = SetupRecord(**sample_setup_record_data)

        assert record.track == ""

    def test_track_property_fallback_no_regex_match(self, sample_setup_record_data):
        """Test track property fallback when regex doesn't match but has enough parts."""
        # Regex won't match because there's no version number (V\d+)
        sample_setup_record_data["download_name"] = "IR-XX-BMW M4 GT3-Daytona-Extra"
        record = SetupRecord(**sample_setup_record_data)

        # Should fall back to simple parsing: parts[3:]
        assert record.track == "Daytona-Extra"

    def test_season_property(self, sample_setup_record_data):
        """Test season property removes spaces from ver."""
        record = SetupRecord(**sample_setup_record_data)

        assert record.season == "26S1W8"

    def test_season_property_different_format(self, sample_setup_record_data):
        """Test season property with different ver format."""
        sample_setup_record_data["ver"] = "2024 S2 W12"
        record = SetupRecord(**sample_setup_record_data)

        assert record.season == "2024S2W12"

    def test_season_property_no_spaces(self, sample_setup_record_data):
        """Test season property when ver has no spaces."""
        sample_setup_record_data["ver"] = "26S1W8"
        record = SetupRecord(**sample_setup_record_data)

        assert record.season == "26S1W8"

    def test_get_output_filename(self, sample_setup_record_data):
        """Test output filename generation."""
        record = SetupRecord(**sample_setup_record_data)

        filename = record.get_output_filename()

        assert filename == "GoFast_IMSA_26S1W8_Spa-Francorchamps_12345.sto"

    def test_get_output_filename_with_spaces_in_track(self, sample_setup_record_data):
        """Test output filename generation with spaces in track name."""
        sample_setup_record_data["download_name"] = (
            "IR - V1 - Ferrari 488 GT3 Evo - Road America"
        )
        record = SetupRecord(**sample_setup_record_data)

        filename = record.get_output_filename()

        assert filename == "GoFast_IMSA_26S1W8_RoadAmerica_12345.sto"

    def test_get_output_filename_with_special_chars(self, sample_setup_record_data):
        """Test output filename generation with special characters in track."""
        sample_setup_record_data["download_name"] = (
            "IR - V1 - Ferrari 488 GT3 Evo - Circuit de Barcelona-Catalunya"
        )
        record = SetupRecord(**sample_setup_record_data)

        filename = record.get_output_filename()

        assert filename == "GoFast_IMSA_26S1W8_CircuitdeBarcelona-Catalunya_12345.sto"

    def test_get_output_directory(self, sample_setup_record_data):
        """Test output directory generation."""
        record = SetupRecord(**sample_setup_record_data)

        directory = record.get_output_directory()

        assert directory == "Ferrari 488 GT3 Evo/Spa-Francorchamps/"

    def test_get_output_directory_with_spaces(self, sample_setup_record_data):
        """Test output directory generation preserves spaces."""
        sample_setup_record_data["download_name"] = (
            "IR - V1 - Audi R8 LMS GT3 - Road America"
        )
        record = SetupRecord(**sample_setup_record_data)

        directory = record.get_output_directory()

        assert directory == "Audi R8 LMS GT3/Road America/"

    def test_validation_empty_download_name(self, sample_setup_record_data):
        """Test validation fails with empty download_name."""
        sample_setup_record_data["download_name"] = ""

        with pytest.raises(ValidationError) as exc_info:
            SetupRecord(**sample_setup_record_data)

        assert "download_name cannot be empty" in str(exc_info.value)

    def test_validation_whitespace_only_download_name(self, sample_setup_record_data):
        """Test validation fails with whitespace-only download_name."""
        sample_setup_record_data["download_name"] = "   "

        with pytest.raises(ValidationError) as exc_info:
            SetupRecord(**sample_setup_record_data)

        assert "download_name cannot be empty" in str(exc_info.value)

    def test_validation_missing_required_fields(self):
        """Test validation fails with missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            SetupRecord(id=1)

        error_dict = exc_info.value.errors()
        missing_fields = {error["loc"][0] for error in error_dict}

        assert "download_name" in missing_fields
        assert "download_url" in missing_fields
        assert "creation_date" in missing_fields
        assert "updated_date" in missing_fields
        assert "ver" in missing_fields
        assert "setup_ver" in missing_fields
        assert "changelog" in missing_fields
        assert "cat" in missing_fields
        assert "series" in missing_fields

    def test_different_id_types(self, sample_setup_record_data):
        """Test that ID must be an integer."""
        sample_setup_record_data["id"] = "12345"  # String ID
        record = SetupRecord(**sample_setup_record_data)

        # Pydantic will coerce the string to int
        assert record.id == 12345
        assert isinstance(record.id, int)

    def test_invalid_id_type(self, sample_setup_record_data):
        """Test that invalid ID types raise validation error."""
        sample_setup_record_data["id"] = "not-a-number"

        with pytest.raises(ValidationError) as exc_info:
            SetupRecord(**sample_setup_record_data)

        assert any("id" in str(error["loc"]) for error in exc_info.value.errors())
