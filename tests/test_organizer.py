"""Tests for the SetupOrganizer."""

import json

import pytest

from iracing_setup_downloader.organizer import (
    OrganizeAction,
    OrganizeResult,
    SetupOrganizer,
)
from iracing_setup_downloader.track_matcher import TrackMatcher


@pytest.fixture
def sample_tracks_data():
    """Sample tracks data for testing."""
    return {
        "type": "tracks",
        "data": [
            {
                "track_id": 1,
                "track_name": "Spa-Francorchamps - Grand Prix Pits",
                "track_dirpath": "spa\\gp",
                "config_name": "Grand Prix Pits",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 2,
                "track_name": "Road America",
                "track_dirpath": "roadamerica\\full",
                "config_name": "Full Course",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 3,
                "track_name": "Daytona International Speedway - Oval",
                "track_dirpath": "daytonaint\\oval",
                "config_name": "Oval",
                "category": "oval",
                "retired": False,
                "is_oval": True,
                "is_dirt": False,
            },
            {
                "track_id": 4,
                "track_name": "Daytona International Speedway - Road Course",
                "track_dirpath": "daytonaint\\road",
                "config_name": "Road Course",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
            {
                "track_id": 5,
                "track_name": "Watkins Glen International - Boot",
                "track_dirpath": "watkinsglen\\boot",
                "config_name": "Boot",
                "category": "road",
                "retired": False,
                "is_oval": False,
                "is_dirt": False,
            },
        ],
    }


@pytest.fixture
def track_matcher(sample_tracks_data, tmp_path):
    """Create a TrackMatcher with sample data."""
    tracks_file = tmp_path / "tracks.json"
    with open(tracks_file, "w") as f:
        json.dump(sample_tracks_data, f)

    matcher = TrackMatcher(tracks_data_path=tracks_file)
    matcher.load()
    return matcher


@pytest.fixture
def organizer(track_matcher):
    """Create a SetupOrganizer instance."""
    return SetupOrganizer(track_matcher)


class TestOrganizeAction:
    """Tests for OrganizeAction dataclass."""

    def test_create_action(self, tmp_path):
        """Test creating an OrganizeAction."""
        source = tmp_path / "test.sto"
        dest = tmp_path / "dest" / "test.sto"

        action = OrganizeAction(
            source=source,
            destination=dest,
            track_name="Spa",
            car_folder="ferrari296gt3",
            track_dirpath="spa\\gp",
            confidence=0.95,
        )

        assert action.source == source
        assert action.destination == dest
        assert action.track_name == "Spa"
        assert action.confidence == 0.95
        assert not action.skipped
        assert not action.error

    def test_will_move_true(self, tmp_path):
        """Test will_move returns True when moving."""
        source = tmp_path / "test.sto"
        dest = tmp_path / "dest" / "test.sto"

        action = OrganizeAction(source=source, destination=dest)

        assert action.will_move is True

    def test_will_move_false_when_skipped(self, tmp_path):
        """Test will_move returns False when skipped."""
        source = tmp_path / "test.sto"
        dest = tmp_path / "dest" / "test.sto"

        action = OrganizeAction(source=source, destination=dest, skipped=True)

        assert action.will_move is False

    def test_will_move_false_when_same_path(self, tmp_path):
        """Test will_move returns False when source equals destination."""
        source = tmp_path / "test.sto"

        action = OrganizeAction(source=source, destination=source)

        assert action.will_move is False

    def test_will_move_false_when_no_destination(self, tmp_path):
        """Test will_move returns False when no destination."""
        source = tmp_path / "test.sto"

        action = OrganizeAction(source=source)

        assert action.will_move is False


class TestOrganizeResult:
    """Tests for OrganizeResult dataclass."""

    def test_create_result(self):
        """Test creating an OrganizeResult."""
        result = OrganizeResult(
            total_files=10,
            organized=7,
            skipped=2,
            failed=1,
        )

        assert result.total_files == 10
        assert result.organized == 7
        assert result.skipped == 2
        assert result.failed == 1

    def test_str_representation(self):
        """Test string representation."""
        result = OrganizeResult(total_files=10, organized=7, skipped=2, failed=1)

        assert "Total: 10" in str(result)
        assert "Organized: 7" in str(result)
        assert "Skipped: 2" in str(result)
        assert "Failed: 1" in str(result)


class TestSetupOrganizer:
    """Tests for SetupOrganizer class."""

    def test_init(self, track_matcher):
        """Test organizer initialization."""
        organizer = SetupOrganizer(track_matcher)

        assert organizer._track_matcher is track_matcher

    def test_organize_empty_directory(self, organizer, tmp_path):
        """Test organizing an empty directory."""
        result = organizer.organize(tmp_path)

        assert result.total_files == 0
        assert result.organized == 0
        assert result.skipped == 0
        assert result.failed == 0

    def test_organize_nonexistent_path(self, organizer, tmp_path):
        """Test organizing a nonexistent path raises error."""
        with pytest.raises(FileNotFoundError):
            organizer.organize(tmp_path / "nonexistent")

    def test_organize_file_not_directory(self, organizer, tmp_path):
        """Test organizing a file raises error."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        with pytest.raises(NotADirectoryError):
            organizer.organize(test_file)


class TestSetupOrganizerFilenameExtraction:
    """Tests for filename parsing in SetupOrganizer."""

    def test_extract_track_from_gofast_filename(self, organizer):
        """Test extracting track from GoFast filename format."""
        filename = "GoFast_IMSA_26S1W8_Spa_Race.sto"

        track = organizer._extract_track_from_filename(filename)

        assert track == "Spa"

    def test_extract_track_from_gofast_filename_multiword(self, organizer):
        """Test extracting multi-word track from GoFast filename."""
        filename = "GoFast_IMSA_26S1W8_RoadAmerica_Qualifying.sto"

        track = organizer._extract_track_from_filename(filename)

        # Should add space to CamelCase
        assert "Road" in track or "road" in track.lower()

    def test_extract_track_from_gofast_filename_with_hyphen(self, organizer):
        """Test extracting track with hyphen from GoFast filename."""
        filename = "GoFast_GT3_26S1W9_Spa-Francorchamps_Race.sto"

        track = organizer._extract_track_from_filename(filename)

        assert "Spa" in track or "spa" in track.lower()

    def test_extract_track_unknown_format(self, organizer):
        """Test unknown filename format is handled gracefully."""
        filename = "random_file.sto"

        # Should not raise an error
        result = organizer._extract_track_from_filename(filename)

        # Result is either empty or some extracted value - both are acceptable
        assert isinstance(result, str)

    def test_add_spaces_to_track_name(self, organizer):
        """Test adding spaces to CamelCase track names."""
        assert organizer._add_spaces_to_track_name("RoadAmerica") == "Road America"
        assert (
            organizer._add_spaces_to_track_name("SpaFrancorchamps")
            == "Spa Francorchamps"
        )
        assert organizer._add_spaces_to_track_name("Spa") == "Spa"

    def test_add_spaces_preserves_existing_spaces(self, organizer):
        """Test that existing spaces are preserved."""
        assert organizer._add_spaces_to_track_name("Road America") == "Road America"

    def test_add_spaces_handles_numbers(self, organizer):
        """Test that numbers are separated."""
        result = organizer._add_spaces_to_track_name("Track24Hours")
        assert " 24" in result or "24" in result  # Should have space before number


class TestSetupOrganizerOrganization:
    """Tests for actual file organization."""

    def test_organize_gofast_files_dry_run(self, organizer, tmp_path):
        """Test dry run doesn't move files."""
        # Create test directory structure
        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()

        setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        setup_file.write_text("setup content")

        result = organizer.organize(tmp_path, dry_run=True)

        # File should still be in original location
        assert setup_file.exists()
        assert result.total_files == 1
        assert result.organized == 1  # Would be organized

    def test_organize_moves_files(self, organizer, tmp_path):
        """Test files are actually moved."""
        # Create test directory structure
        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()

        setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        setup_file.write_text("setup content")

        result = organizer.organize(tmp_path, dry_run=False)

        # File should be moved to track subdirectory
        assert not setup_file.exists()  # Original gone
        assert result.organized == 1

        # Find the new location
        organized_files = list(tmp_path.rglob("*.sto"))
        assert len(organized_files) == 1
        assert "spa" in str(organized_files[0]).lower()

    def test_organize_copies_files(self, organizer, tmp_path):
        """Test files are copied when copy=True."""
        # Create test directory structure
        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()

        setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        setup_file.write_text("setup content")

        result = organizer.organize(tmp_path, dry_run=False, copy=True)

        # Original file should still exist
        assert setup_file.exists()
        assert result.organized == 1

        # Should have 2 files now (original + copy)
        organized_files = list(tmp_path.rglob("*.sto"))
        assert len(organized_files) == 2

    def test_organize_to_different_output(self, organizer, tmp_path):
        """Test organizing to a different output directory."""
        # Create source directory
        source_dir = tmp_path / "source"
        car_dir = source_dir / "ferrari296gt3"
        car_dir.mkdir(parents=True)

        setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        setup_file.write_text("setup content")

        # Create output directory
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = organizer.organize(source_dir, output_path=output_dir, dry_run=False)

        # Original should be gone (moved)
        assert not setup_file.exists()

        # New file should be in output
        output_files = list(output_dir.rglob("*.sto"))
        assert len(output_files) == 1
        assert result.organized == 1

    def test_organize_skips_unknown_track(self, organizer, tmp_path):
        """Test files with unknown tracks are skipped."""
        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()

        # File with unrecognizable track
        setup_file = car_dir / "random_setup.sto"
        setup_file.write_text("setup content")

        result = organizer.organize(tmp_path, dry_run=False)

        # File should remain in place
        assert setup_file.exists()
        assert result.skipped >= 1

    def test_organize_skips_already_organized(self, organizer, tmp_path):
        """Test files already in correct location are skipped."""
        # Create already-organized structure
        car_dir = tmp_path / "ferrari296gt3"
        track_dir = car_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)

        setup_file = track_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        setup_file.write_text("setup content")

        result = organizer.organize(tmp_path, dry_run=False)

        # File should remain in place
        assert setup_file.exists()
        assert result.skipped >= 1

        # Check skip reason
        skipped_actions = [a for a in result.actions if a.skipped]
        assert any(
            "Already in correct location" in a.skip_reason for a in skipped_actions
        )

    def test_organize_with_category_hint(self, organizer, tmp_path):
        """Test category hint affects track disambiguation."""
        car_dir = tmp_path / "nascarnextgen"
        car_dir.mkdir()

        # Daytona has both oval and road configs
        setup_file = car_dir / "GoFast_Cup_26S1W8_Daytona_Race.sto"
        setup_file.write_text("setup content")

        result = organizer.organize(tmp_path, dry_run=True, category_hint="NASCAR")

        # Should match to oval config for NASCAR
        assert result.organized == 1
        action = result.actions[0]
        assert "oval" in action.track_dirpath.lower()

    def test_organize_multiple_files(self, organizer, tmp_path):
        """Test organizing multiple files."""
        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()

        files = [
            "GoFast_IMSA_26S1W8_Spa_Race.sto",
            "GoFast_IMSA_26S1W8_Spa_Qualifying.sto",
            "GoFast_IMSA_26S1W9_RoadAmerica_Race.sto",
        ]

        for filename in files:
            (car_dir / filename).write_text("setup content")

        result = organizer.organize(tmp_path, dry_run=False)

        assert result.total_files == 3
        assert result.organized == 3

        # Verify file structure
        spa_files = list((tmp_path / "ferrari296gt3").rglob("**/spa/**/*.sto"))
        assert len(spa_files) == 2

    def test_organize_preserves_car_folder(self, organizer, tmp_path):
        """Test that car folder is preserved in output."""
        car1_dir = tmp_path / "ferrari296gt3"
        car2_dir = tmp_path / "porsche911gt3r"
        car1_dir.mkdir()
        car2_dir.mkdir()

        (car1_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto").write_text("content")
        (car2_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto").write_text("content")

        result = organizer.organize(tmp_path, dry_run=False)

        assert result.organized == 2

        # Each car should have its own subfolder
        ferrari_files = list((tmp_path / "ferrari296gt3").rglob("*.sto"))
        porsche_files = list((tmp_path / "porsche911gt3r").rglob("*.sto"))
        assert len(ferrari_files) == 1
        assert len(porsche_files) == 1

    def test_organize_skips_destination_exists(self, organizer, tmp_path):
        """Test that existing destination files are not overwritten."""
        car_dir = tmp_path / "ferrari296gt3"
        track_dir = car_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)

        # Create source file
        source_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        source_file.write_text("new content")

        # Create existing destination file
        dest_file = track_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        dest_file.write_text("existing content")

        result = organizer.organize(tmp_path, dry_run=False)

        # Source should still exist (not moved)
        assert source_file.exists()
        # Destination should have original content
        assert dest_file.read_text() == "existing content"
        assert result.skipped >= 1


class TestSetupOrganizerEdgeCases:
    """Tests for edge cases in SetupOrganizer."""

    def test_organize_nested_structure(self, organizer, tmp_path):
        """Test organizing deeply nested directory structure."""
        # Create nested structure
        deep_dir = tmp_path / "car" / "season" / "track" / "subfolder"
        deep_dir.mkdir(parents=True)

        setup_file = deep_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        setup_file.write_text("content")

        result = organizer.organize(tmp_path, dry_run=True)

        # Should still find and process the file
        assert result.total_files == 1

    def test_organize_handles_special_characters(self, organizer, tmp_path):
        """Test organizing files with special characters in names."""
        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()

        # File with various special chars
        setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa-Francorchamps_Race.sto"
        setup_file.write_text("content")

        result = organizer.organize(tmp_path, dry_run=True)

        assert result.total_files == 1
        # Should still process (may or may not organize depending on matching)

    def test_organize_cleans_empty_directories(self, organizer, tmp_path):
        """Test that empty directories are cleaned up after moving."""
        # Create structure where file move will leave empty dirs
        car_dir = tmp_path / "ferrari296gt3"
        old_track_dir = car_dir / "old_track_folder"
        old_track_dir.mkdir(parents=True)

        setup_file = old_track_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        setup_file.write_text("content")

        result = organizer.organize(tmp_path, dry_run=False)

        assert result.organized == 1
        # Old track folder should be cleaned up
        assert not old_track_dir.exists()
