"""Tests for the TrackMatcher service."""

import json

import pytest

from iracing_setup_downloader.track_matcher import (
    TrackData,
    TrackMatcher,
    TrackMatchResult,
)


@pytest.fixture
def sample_tracks_data():
    """Sample tracks data for testing."""
    return {
        "type": "tracks",
        "data": [
            {
                "track_id": 1,
                "track_name": "Road America",
                "track_dirpath": "roadamerica\\full",
                "config_name": "Full Course",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 2,
                "track_name": "Spa-Francorchamps - Grand Prix Pits",
                "track_dirpath": "spa\\gp",
                "config_name": "Grand Prix Pits",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 3,
                "track_name": "Spa-Francorchamps - Endurance",
                "track_dirpath": "spa\\endurance",
                "config_name": "Endurance",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 4,
                "track_name": "Daytona International Speedway - Oval",
                "track_dirpath": "daytonaint\\oval",
                "config_name": "Oval",
                "category": "oval",
                "retired": False,
                "is_oval": True,
                "is_dirt": False,
            },
            {
                "track_id": 5,
                "track_name": "Daytona International Speedway - Road Course",
                "track_dirpath": "daytonaint\\road",
                "config_name": "Road Course",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 6,
                "track_name": "[Retired] Lime Rock Park - 2008",
                "track_dirpath": "limerock\\full",
                "config_name": "[Retired] Full Course",
                "category": "road",
                "retired": True,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 7,
                "track_name": "Lime Rock Park",
                "track_dirpath": "limerockpark\\full",
                "config_name": "Full Course",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 8,
                "track_name": "Watkins Glen International - Boot",
                "track_dirpath": "watkinsglen\\boot",
                "config_name": "Boot",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 9,
                "track_name": "Watkins Glen International - Cup",
                "track_dirpath": "watkinsglen\\cup",
                "config_name": "Cup",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 10,
                "track_name": "Charlotte Motor Speedway - Oval",
                "track_dirpath": "charlotte\\oval",
                "config_name": "Oval",
                "category": "oval",
                "retired": False,
                "is_oval": True,
                "is_dirt": False,
            },
            {
                "track_id": 11,
                "track_name": "Charlotte Motor Speedway - Roval",
                "track_dirpath": "charlotte\\roval",
                "config_name": "Roval",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
        ],
    }


@pytest.fixture
def tracks_json_file(sample_tracks_data, tmp_path):
    """Create a temporary tracks.json file."""
    tracks_file = tmp_path / "tracks.json"
    with open(tracks_file, "w") as f:
        json.dump(sample_tracks_data, f)
    return tracks_file


@pytest.fixture
def track_matcher(tracks_json_file):
    """Create a TrackMatcher with sample data."""
    matcher = TrackMatcher(tracks_data_path=tracks_json_file)
    matcher.load()
    return matcher


class TestTrackData:
    """Tests for TrackData model."""

    def test_create_track_data(self):
        """Test creating a TrackData instance."""
        track = TrackData(
            track_id=1,
            track_name="Road America",
            track_dirpath="roadamerica\\full",
            config_name="Full Course",
            category="road",
            retired=False,
            is_oval=False,
            is_dirt=False,
        )

        assert track.track_id == 1
        assert track.track_name == "Road America"
        assert track.track_dirpath == "roadamerica\\full"
        assert track.config_name == "Full Course"
        assert track.retired is False

    def test_track_data_defaults(self):
        """Test TrackData default values."""
        track = TrackData(
            track_id=1,
            track_name="Test Track",
            track_dirpath="test\\path",
        )

        assert track.config_name == ""
        assert track.category == ""
        assert track.retired is False
        assert track.is_oval is False
        assert track.is_dirt is False


class TestTrackMatchResult:
    """Tests for TrackMatchResult model."""

    def test_create_match_result(self):
        """Test creating a TrackMatchResult instance."""
        result = TrackMatchResult(
            track_dirpath="spa\\gp",
            confidence=0.95,
            ambiguous=False,
            matched_track_name="Spa-Francorchamps - Grand Prix Pits",
            matched_config="Grand Prix Pits",
        )

        assert result.track_dirpath == "spa\\gp"
        assert result.confidence == 0.95
        assert result.ambiguous is False

    def test_match_result_defaults(self):
        """Test TrackMatchResult default values."""
        result = TrackMatchResult()

        assert result.track_dirpath is None
        assert result.confidence == 0.0
        assert result.ambiguous is False
        assert result.matched_track_name is None
        assert result.matched_config is None


class TestTrackMatcher:
    """Tests for TrackMatcher class."""

    def test_init_with_custom_path(self, tracks_json_file):
        """Test initialization with custom data path."""
        matcher = TrackMatcher(tracks_data_path=tracks_json_file)

        assert matcher._tracks_data_path == tracks_json_file
        assert matcher._loaded is False

    def test_init_without_custom_path(self):
        """Test initialization without custom path (uses bundled data)."""
        matcher = TrackMatcher()

        assert matcher._tracks_data_path is None
        assert matcher._loaded is False

    def test_load_tracks(self, track_matcher):
        """Test loading tracks data."""
        assert track_matcher._loaded is True
        assert len(track_matcher._tracks) == 11

    def test_load_only_once(self, track_matcher):
        """Test that load() is idempotent."""
        initial_count = len(track_matcher._tracks)
        track_matcher.load()  # Call again

        assert len(track_matcher._tracks) == initial_count

    def test_load_file_not_found(self, tmp_path):
        """Test loading with non-existent file."""
        matcher = TrackMatcher(tracks_data_path=tmp_path / "nonexistent.json")

        with pytest.raises(FileNotFoundError):
            matcher.load()

    def test_load_direct_list_format(self, tmp_path):
        """Test loading tracks in direct list format (no wrapper)."""
        tracks_file = tmp_path / "tracks.json"
        tracks_data = [
            {
                "track_id": 1,
                "track_name": "Test Track",
                "track_dirpath": "test\\path",
            }
        ]
        with open(tracks_file, "w") as f:
            json.dump(tracks_data, f)

        matcher = TrackMatcher(tracks_data_path=tracks_file)
        matcher.load()

        assert len(matcher._tracks) == 1


class TestTrackMatcherMatching:
    """Tests for track matching functionality."""

    def test_exact_match(self, track_matcher):
        """Test exact track name matching."""
        result = track_matcher.match("Road America")

        assert result.track_dirpath == "roadamerica\\full"
        assert result.confidence == 1.0
        assert result.ambiguous is False
        assert "Road America" in result.matched_track_name

    def test_exact_match_with_different_case(self, track_matcher):
        """Test exact match is case-insensitive."""
        result = track_matcher.match("ROAD AMERICA")

        assert result.track_dirpath == "roadamerica\\full"
        assert result.confidence == 1.0

    def test_partial_match_spa(self, track_matcher):
        """Test partial match for Spa returns a valid config."""
        result = track_matcher.match("Spa-Francorchamps")

        assert result.track_dirpath is not None
        assert "spa\\" in result.track_dirpath
        assert result.confidence >= 0.8

    def test_partial_match_spa_short(self, track_matcher):
        """Test partial match for 'Spa' returns a valid config."""
        result = track_matcher.match("Spa")

        assert result.track_dirpath is not None
        assert "spa\\" in result.track_dirpath
        # Lower confidence for shorter/fuzzier match
        assert result.confidence >= 0.6

    def test_category_disambiguation_gt3_daytona(self, track_matcher):
        """Test GT3 category prefers road config at Daytona."""
        result = track_matcher.match(
            "Daytona International Speedway", category_hint="GT3"
        )

        assert result.track_dirpath == "daytonaint\\road"
        assert result.ambiguous is False

    def test_category_disambiguation_nascar_daytona(self, track_matcher):
        """Test NASCAR category prefers oval config at Daytona."""
        result = track_matcher.match(
            "Daytona International Speedway", category_hint="NASCAR"
        )

        assert result.track_dirpath == "daytonaint\\oval"

    def test_category_disambiguation_charlotte(self, track_matcher):
        """Test category disambiguation at Charlotte."""
        # NASCAR should prefer oval
        nascar_result = track_matcher.match(
            "Charlotte Motor Speedway", category_hint="NASCAR"
        )
        assert nascar_result.track_dirpath == "charlotte\\oval"

        # IMSA should prefer roval
        imsa_result = track_matcher.match(
            "Charlotte Motor Speedway", category_hint="IMSA"
        )
        assert imsa_result.track_dirpath == "charlotte\\roval"

    def test_prefers_non_retired_tracks(self, track_matcher):
        """Test that non-retired tracks are preferred over retired ones."""
        result = track_matcher.match("Lime Rock Park")

        # Should match the non-retired version
        assert result.track_dirpath == "limerockpark\\full"
        assert "[Retired]" not in result.matched_track_name

    def test_no_match_returns_empty_result(self, track_matcher):
        """Test that unmatched tracks return empty result."""
        result = track_matcher.match("Nonexistent Track XYZ123")

        assert result.track_dirpath is None
        assert result.confidence == 0.0

    def test_empty_track_name_returns_empty_result(self, track_matcher):
        """Test that empty track name returns empty result."""
        result = track_matcher.match("")

        assert result.track_dirpath is None

    def test_match_without_load_returns_empty(self, tracks_json_file):
        """Test that matching without loading returns empty result."""
        matcher = TrackMatcher(tracks_data_path=tracks_json_file)
        # Don't call load()

        result = matcher.match("Road America")

        assert result.track_dirpath is None

    def test_fuzzy_match_watkins_glen(self, track_matcher):
        """Test fuzzy matching for Watkins Glen variations."""
        result = track_matcher.match("Watkins Glen")

        assert result.track_dirpath is not None
        assert "watkinsglen\\" in result.track_dirpath
        assert result.confidence >= 0.6

    def test_fuzzy_match_with_typo(self, track_matcher):
        """Test fuzzy matching handles minor typos."""
        result = track_matcher.match("Road Amrica")  # Missing 'e'

        assert result.track_dirpath is not None
        assert "roadamerica" in result.track_dirpath
        assert result.confidence >= 0.6


class TestTrackMatcherNormalization:
    """Tests for track name normalization."""

    def test_normalize_removes_special_chars(self, track_matcher):
        """Test normalization removes special characters."""
        normalized = track_matcher._normalize_name("Spa-Francorchamps!")

        assert "-" not in normalized
        assert "!" not in normalized
        assert "spa" in normalized

    def test_normalize_handles_retired_prefix(self, track_matcher):
        """Test normalization removes [Retired] prefix."""
        normalized = track_matcher._normalize_name("[Retired] Lime Rock Park - 2008")

        assert "[retired]" not in normalized
        assert "lime rock" in normalized

    def test_normalize_converts_to_lowercase(self, track_matcher):
        """Test normalization converts to lowercase."""
        normalized = track_matcher._normalize_name("ROAD AMERICA")

        assert normalized == "road america"

    def test_normalize_collapses_whitespace(self, track_matcher):
        """Test normalization collapses multiple spaces."""
        normalized = track_matcher._normalize_name("Road   America    Test")

        assert "  " not in normalized
        assert normalized == "road america test"

    def test_extract_base_name(self, track_matcher):
        """Test base name extraction from full track names."""
        base = track_matcher._extract_base_name("Spa-Francorchamps - Grand Prix Pits")

        assert base == "Spa-Francorchamps"

    def test_extract_base_name_no_config(self, track_matcher):
        """Test base name extraction when no config suffix."""
        base = track_matcher._extract_base_name("Road America")

        assert base == "Road America"

    def test_extract_base_name_retired(self, track_matcher):
        """Test base name extraction removes [Retired] prefix."""
        base = track_matcher._extract_base_name("[Retired] Lime Rock Park - 2008")

        assert base == "Lime Rock Park"


class TestTrackMatcherCategoryDetection:
    """Tests for category preference detection."""

    def test_should_prefer_oval_nascar(self, track_matcher):
        """Test NASCAR categories prefer oval."""
        assert track_matcher._should_prefer_oval("NASCAR") is True
        assert track_matcher._should_prefer_oval("NASCAR Cup") is True
        assert track_matcher._should_prefer_oval("Xfinity") is True
        assert track_matcher._should_prefer_oval("Truck") is True

    def test_should_prefer_oval_gt_categories(self, track_matcher):
        """Test GT categories prefer road."""
        assert track_matcher._should_prefer_oval("GT3") is False
        assert track_matcher._should_prefer_oval("GT4") is False
        assert track_matcher._should_prefer_oval("GTE") is False
        assert track_matcher._should_prefer_oval("IMSA") is False

    def test_should_prefer_oval_no_hint(self, track_matcher):
        """Test default preference when no category hint."""
        assert track_matcher._should_prefer_oval(None) is False
        assert track_matcher._should_prefer_oval("") is False

    def test_should_prefer_oval_case_insensitive(self, track_matcher):
        """Test category detection is case-insensitive."""
        assert track_matcher._should_prefer_oval("nascar") is True
        assert track_matcher._should_prefer_oval("gt3") is False


class TestTrackMatcherIntegration:
    """Integration tests for TrackMatcher with bundled data."""

    def test_load_bundled_data(self):
        """Test loading the bundled tracks.json data."""
        matcher = TrackMatcher()

        # This should not raise if package data is properly configured
        try:
            matcher.load()
            assert matcher._loaded is True
            assert len(matcher._tracks) > 0
        except FileNotFoundError:
            pytest.skip("Bundled tracks.json not available in test environment")

    def test_real_track_matching(self):
        """Test matching against real bundled data."""
        matcher = TrackMatcher()

        try:
            matcher.load()
        except FileNotFoundError:
            pytest.skip("Bundled tracks.json not available in test environment")

        # Test some common tracks
        result = matcher.match("Spa-Francorchamps")
        assert result.track_dirpath is not None
        assert "spa" in result.track_dirpath.lower()
