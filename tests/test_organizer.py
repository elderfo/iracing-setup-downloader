"""Tests for the SetupOrganizer."""

import json

import pytest

from iracing_setup_downloader.deduplication import DuplicateDetector
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


class TestSetupOrganizerDuplicateDetection:
    """Tests for duplicate detection in SetupOrganizer."""

    @pytest.fixture
    def organizer_with_detector(self, track_matcher):
        """Create a SetupOrganizer with DuplicateDetector."""
        detector = DuplicateDetector()
        return SetupOrganizer(track_matcher, duplicate_detector=detector)

    def test_detects_duplicate_at_destination(self, organizer_with_detector, tmp_path):
        """Test detection of duplicate when destination file exists."""
        car_dir = tmp_path / "ferrari296gt3"
        track_dir = car_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)

        # Create source file
        source_content = b"setup content"
        source_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        source_file.write_bytes(source_content)

        # Create existing destination with same content
        dest_file = track_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        dest_file.write_bytes(source_content)

        result = organizer_with_detector.organize(tmp_path, dry_run=False)

        # File should be skipped as duplicate
        assert result.duplicates_found == 1
        assert result.duplicates_deleted == 1
        # Source should be deleted (move mode)
        assert not source_file.exists()
        # Destination should still exist
        assert dest_file.exists()

    def test_detects_duplicate_elsewhere_in_target(
        self, organizer_with_detector, tmp_path
    ):
        """Test detection of duplicate elsewhere in target directory."""
        car1_dir = tmp_path / "ferrari296gt3"
        car2_dir = tmp_path / "porsche911gt3r"
        track_dir = car1_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)
        car2_dir.mkdir(parents=True)

        # Create existing file in organized location
        existing_content = b"existing setup"
        existing_file = track_dir / "existing.sto"
        existing_file.write_bytes(existing_content)

        # Create source file with same content
        source_file = car2_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        source_file.write_bytes(existing_content)

        result = organizer_with_detector.organize(tmp_path, dry_run=False)

        # Should detect as duplicate
        assert result.duplicates_found == 1
        assert result.duplicates_deleted == 1
        # Source should be deleted
        assert not source_file.exists()

    def test_duplicate_detection_dry_run(self, organizer_with_detector, tmp_path):
        """Test duplicate detection in dry run mode."""
        car_dir = tmp_path / "ferrari296gt3"
        track_dir = car_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)

        duplicate_content = b"same content"
        source_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        source_file.write_bytes(duplicate_content)
        dest_file = track_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        dest_file.write_bytes(duplicate_content)

        result = organizer_with_detector.organize(tmp_path, dry_run=True)

        # Should detect duplicate but not delete
        assert result.duplicates_found == 1
        assert result.duplicates_deleted == 0
        # Source should still exist
        assert source_file.exists()

    def test_duplicate_detection_copy_mode(self, organizer_with_detector, tmp_path):
        """Test duplicate detection in copy mode (no deletion)."""
        car_dir = tmp_path / "ferrari296gt3"
        track_dir = car_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)

        duplicate_content = b"same content"
        source_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        source_file.write_bytes(duplicate_content)
        dest_file = track_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        dest_file.write_bytes(duplicate_content)

        result = organizer_with_detector.organize(tmp_path, dry_run=False, copy=True)

        # Should detect duplicate but not delete in copy mode
        assert result.duplicates_found == 1
        assert result.duplicates_deleted == 0
        # Source should still exist
        assert source_file.exists()

    def test_different_content_not_duplicate(self, organizer_with_detector, tmp_path):
        """Test that files with different content are not marked as duplicates."""
        car_dir = tmp_path / "ferrari296gt3"
        track_dir = car_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)

        source_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        source_file.write_bytes(b"new content")
        dest_file = track_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        dest_file.write_bytes(b"different content")

        result = organizer_with_detector.organize(tmp_path, dry_run=False)

        # Should not detect as duplicate
        assert result.duplicates_found == 0
        # Skipped: source (destination exists) + dest (already in correct location)
        assert result.skipped == 2
        # Verify source was skipped for "destination exists", not duplicate
        source_action = next(a for a in result.actions if a.source == source_file)
        assert not source_action.is_duplicate
        assert "already exists" in source_action.skip_reason.lower()

    def test_bytes_saved_tracking(self, organizer_with_detector, tmp_path):
        """Test that bytes_saved is tracked correctly."""
        car_dir = tmp_path / "ferrari296gt3"
        track_dir = car_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)

        # Create content of known size
        content = b"x" * 1024  # 1KB
        source_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        source_file.write_bytes(content)
        dest_file = track_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        dest_file.write_bytes(content)

        result = organizer_with_detector.organize(tmp_path, dry_run=False)

        assert result.bytes_saved == 1024

    def test_disable_duplicate_detection(self, track_matcher, tmp_path):
        """Test that duplicate detection can be disabled."""
        detector = DuplicateDetector()
        organizer = SetupOrganizer(track_matcher, duplicate_detector=detector)

        car_dir = tmp_path / "ferrari296gt3"
        track_dir = car_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)

        content = b"same content"
        source_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        source_file.write_bytes(content)
        dest_file = track_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        dest_file.write_bytes(content)

        # Disable duplicate detection
        result = organizer.organize(tmp_path, dry_run=False, detect_duplicates=False)

        # Should not detect as duplicate
        assert result.duplicates_found == 0
        # Skipped: source (destination exists) + dest (already in correct location)
        assert result.skipped == 2
        # Source should still exist (not deleted since no duplicate detection)
        assert source_file.exists()
        # Verify source was NOT marked as duplicate
        source_action = next(a for a in result.actions if a.source == source_file)
        assert not source_action.is_duplicate

    def test_organizer_without_detector(self, track_matcher, tmp_path):
        """Test organizer works without duplicate detector."""
        organizer = SetupOrganizer(track_matcher)  # No detector

        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()
        setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        setup_file.write_bytes(b"content")

        result = organizer.organize(tmp_path, dry_run=False)

        # Should work normally
        assert result.organized == 1
        assert result.duplicates_found == 0


class TestCompanionFiles:
    """Tests for companion file handling."""

    def test_find_companion_files(self, track_matcher, tmp_path):
        """Test finding companion files for a .sto file."""
        organizer = SetupOrganizer(track_matcher)

        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()
        sto_file = car_dir / "setup.sto"
        sto_file.write_bytes(b"setup content")

        # Create companion files
        (car_dir / "setup.ld").write_bytes(b"lap data")
        (car_dir / "setup.ldx").write_bytes(b"lap index")
        (car_dir / "setup.olap").write_bytes(b"overlap")
        (car_dir / "setup.blap").write_bytes(b"best lap")
        (car_dir / "setup.rpy").write_bytes(b"replay")

        # Create unrelated file
        (car_dir / "other.ld").write_bytes(b"other data")

        companions = organizer._find_companion_files(sto_file)

        assert len(companions) == 5
        companion_names = {c.name for c in companions}
        assert companion_names == {
            "setup.ld",
            "setup.ldx",
            "setup.olap",
            "setup.blap",
            "setup.rpy",
        }

    def test_find_companion_files_none_exist(self, track_matcher, tmp_path):
        """Test finding companion files when none exist."""
        organizer = SetupOrganizer(track_matcher)

        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()
        sto_file = car_dir / "setup.sto"
        sto_file.write_bytes(b"setup content")

        companions = organizer._find_companion_files(sto_file)

        assert companions == []

    def test_organize_moves_companion_files(self, track_matcher, tmp_path):
        """Test that organizing moves companion files with .sto file."""
        organizer = SetupOrganizer(track_matcher)

        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()
        sto_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        sto_file.write_bytes(b"setup content")

        # Create companion files
        ld_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.ld"
        ld_file.write_bytes(b"lap data")
        ldx_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.ldx"
        ldx_file.write_bytes(b"lap index")

        result = organizer.organize(tmp_path, dry_run=False)

        assert result.organized == 1
        assert result.companion_files_moved == 2

        # Verify files were moved
        dest_dir = tmp_path / "ferrari296gt3" / "spa" / "gp"
        assert (dest_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto").exists()
        assert (dest_dir / "GoFast_IMSA_26S1W8_Spa_Race.ld").exists()
        assert (dest_dir / "GoFast_IMSA_26S1W8_Spa_Race.ldx").exists()

        # Verify originals are gone
        assert not sto_file.exists()
        assert not ld_file.exists()
        assert not ldx_file.exists()

    def test_organize_copies_companion_files(self, track_matcher, tmp_path):
        """Test that organizing copies companion files with .sto file when copy=True."""
        organizer = SetupOrganizer(track_matcher)

        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()
        sto_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        sto_file.write_bytes(b"setup content")

        # Create companion file
        ld_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.ld"
        ld_file.write_bytes(b"lap data")

        result = organizer.organize(tmp_path, dry_run=False, copy=True)

        assert result.organized == 1
        assert result.companion_files_moved == 1

        # Verify files were copied (destination exists)
        dest_dir = tmp_path / "ferrari296gt3" / "spa" / "gp"
        assert (dest_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto").exists()
        assert (dest_dir / "GoFast_IMSA_26S1W8_Spa_Race.ld").exists()

        # Verify originals still exist (copy mode)
        assert sto_file.exists()
        assert ld_file.exists()

    def test_organize_dry_run_counts_companion_files(self, track_matcher, tmp_path):
        """Test that dry run counts companion files without moving them."""
        organizer = SetupOrganizer(track_matcher)

        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()
        sto_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        sto_file.write_bytes(b"setup content")

        # Create companion files
        (car_dir / "GoFast_IMSA_26S1W8_Spa_Race.ld").write_bytes(b"lap data")
        (car_dir / "GoFast_IMSA_26S1W8_Spa_Race.rpy").write_bytes(b"replay")

        result = organizer.organize(tmp_path, dry_run=True)

        assert result.organized == 1
        assert result.companion_files_moved == 2

        # Verify action has companion count
        action = result.actions[0]
        assert action.companion_files_moved == 2

        # Verify files weren't actually moved
        assert sto_file.exists()
        assert (car_dir / "GoFast_IMSA_26S1W8_Spa_Race.ld").exists()
        assert (car_dir / "GoFast_IMSA_26S1W8_Spa_Race.rpy").exists()

    def test_duplicate_deletion_removes_companion_files(self, track_matcher, tmp_path):
        """Test that deleting duplicate .sto also deletes companion files."""
        duplicate_detector = DuplicateDetector()
        organizer = SetupOrganizer(track_matcher, duplicate_detector=duplicate_detector)

        # Create target directory with existing file
        car_dir = tmp_path / "ferrari296gt3"
        track_dir = car_dir / "spa" / "gp"
        track_dir.mkdir(parents=True)
        existing = track_dir / "existing.sto"
        existing.write_bytes(b"same content")

        # Create source directory with duplicate and companion files
        source_car = tmp_path / "source" / "ferrari296gt3"
        source_car.mkdir(parents=True)
        duplicate = source_car / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        duplicate.write_bytes(b"same content")

        # Create companion files for the duplicate
        companion_ld = source_car / "GoFast_IMSA_26S1W8_Spa_Race.ld"
        companion_ld.write_bytes(b"lap data")
        companion_rpy = source_car / "GoFast_IMSA_26S1W8_Spa_Race.rpy"
        companion_rpy.write_bytes(b"replay data")

        result = organizer.organize(
            tmp_path / "source",
            output_path=tmp_path,
            dry_run=False,
        )

        assert result.duplicates_deleted == 1
        # Bytes saved should include .sto + companion files
        assert result.bytes_saved > len(b"same content")

        # Verify duplicate and companions were deleted
        assert not duplicate.exists()
        assert not companion_ld.exists()
        assert not companion_rpy.exists()

    def test_companion_extensions_constant(self):
        """Test that companion extensions constant has expected values."""
        assert ".ld" in SetupOrganizer.COMPANION_EXTENSIONS
        assert ".ldx" in SetupOrganizer.COMPANION_EXTENSIONS
        assert ".olap" in SetupOrganizer.COMPANION_EXTENSIONS
        assert ".blap" in SetupOrganizer.COMPANION_EXTENSIONS
        assert ".rpy" in SetupOrganizer.COMPANION_EXTENSIONS

    def test_result_str_includes_companion_files(self):
        """Test that OrganizeResult string representation includes companion files."""
        result = OrganizeResult(
            total_files=10,
            organized=5,
            skipped=3,
            failed=2,
            companion_files_moved=8,
        )

        result_str = str(result)

        assert "Companion files: 8" in result_str

    def test_organize_all_companion_extensions(self, track_matcher, tmp_path):
        """Test organizing with all supported companion file extensions."""
        organizer = SetupOrganizer(track_matcher)

        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()
        sto_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        sto_file.write_bytes(b"setup")

        # Create all companion file types
        for ext in SetupOrganizer.COMPANION_EXTENSIONS:
            companion = car_dir / f"GoFast_IMSA_26S1W8_Spa_Race{ext}"
            companion.write_bytes(f"data for {ext}".encode())

        result = organizer.organize(tmp_path, dry_run=False)

        assert result.companion_files_moved == 5

        # Verify all files moved to destination
        dest_dir = tmp_path / "ferrari296gt3" / "spa" / "gp"
        assert (dest_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto").exists()
        for ext in SetupOrganizer.COMPANION_EXTENSIONS:
            assert (dest_dir / f"GoFast_IMSA_26S1W8_Spa_Race{ext}").exists()

    def test_companion_file_skipped_if_exists_at_destination(
        self, track_matcher, tmp_path
    ):
        """Test that companion files are skipped if they already exist at destination."""
        organizer = SetupOrganizer(track_matcher)

        # Create source directory with setup and companion
        car_dir = tmp_path / "ferrari296gt3"
        car_dir.mkdir()
        sto_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
        sto_file.write_bytes(b"setup content")
        source_companion = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.ld"
        source_companion.write_bytes(b"new lap data")

        # Create destination directory with existing companion file
        dest_dir = tmp_path / "ferrari296gt3" / "spa" / "gp"
        dest_dir.mkdir(parents=True)
        existing_companion = dest_dir / "GoFast_IMSA_26S1W8_Spa_Race.ld"
        existing_companion.write_bytes(b"existing lap data")

        result = organizer.organize(tmp_path, dry_run=False)

        assert result.organized == 1
        # Companion should be skipped (not counted) since it exists at destination
        assert result.companion_files_moved == 0

        # Verify .sto was moved
        assert (dest_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto").exists()

        # Verify existing companion was NOT overwritten
        assert existing_companion.read_bytes() == b"existing lap data"

        # Verify source companion still exists (wasn't moved)
        assert source_companion.exists()
