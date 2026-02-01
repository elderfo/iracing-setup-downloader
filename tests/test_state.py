"""Tests for the state module."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from iracing_setup_downloader.state import DownloadRecord, DownloadState


class TestDownloadRecord:
    """Tests for the DownloadRecord model."""

    def test_download_record_creation(self):
        """Test creating a DownloadRecord instance."""
        record = DownloadRecord(
            updated_date="2024-01-15T10:30:00",
            file_paths=["/path/to/setup.sto"],
        )

        assert record.updated_date == "2024-01-15T10:30:00"
        assert record.file_paths == ["/path/to/setup.sto"]

    def test_download_record_validates_datetime(self):
        """Test that DownloadRecord validates datetime format."""
        # Valid ISO format
        record = DownloadRecord(
            updated_date="2024-01-15T10:30:00.123456",
            file_paths=["/path/to/setup.sto"],
        )
        assert record.updated_date == "2024-01-15T10:30:00.123456"

        # Invalid format should raise ValueError
        with pytest.raises(ValueError, match="Invalid ISO datetime format"):
            DownloadRecord(
                updated_date="not-a-datetime",
                file_paths=["/path/to/setup.sto"],
            )

    def test_download_record_serialization(self):
        """Test that DownloadRecord can be serialized to dict."""
        record = DownloadRecord(
            updated_date="2024-01-15T10:30:00",
            file_paths=["/path/to/setup.sto"],
        )
        data = record.model_dump()

        assert data == {
            "updated_date": "2024-01-15T10:30:00",
            "file_paths": ["/path/to/setup.sto"],
            "file_path": None,
        }

    def test_download_record_get_all_paths(self):
        """Test get_all_paths method."""
        # With file_paths
        record = DownloadRecord(
            updated_date="2024-01-15T10:30:00",
            file_paths=["/path/to/setup1.sto", "/path/to/setup2.sto"],
        )
        assert record.get_all_paths() == ["/path/to/setup1.sto", "/path/to/setup2.sto"]

        # With legacy file_path
        record_legacy = DownloadRecord(
            updated_date="2024-01-15T10:30:00",
            file_path="/path/to/setup.sto",
        )
        assert record_legacy.get_all_paths() == ["/path/to/setup.sto"]

        # Empty
        record_empty = DownloadRecord(
            updated_date="2024-01-15T10:30:00",
        )
        assert record_empty.get_all_paths() == []


class TestDownloadState:
    """Tests for the DownloadState class."""

    def test_initialization_default_path(self):
        """Test DownloadState initialization with default path."""
        state = DownloadState()

        expected_path = Path.home() / ".iracing-setup-downloader" / "state.json"
        assert state.state_file == expected_path

    def test_initialization_custom_path(self):
        """Test DownloadState initialization with custom path."""
        custom_path = Path("/tmp/custom/state.json")
        state = DownloadState(state_file=custom_path)

        assert state.state_file == custom_path

    def test_load_nonexistent_file(self, temp_dir):
        """Test loading state when file doesn't exist."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)

        state.load()

        assert state.get_stats() == {}
        assert not state_file.exists()  # File only created on save

    def test_save_creates_file(self, temp_dir):
        """Test that save creates the state file."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)

        state.load()
        state.save()

        assert state_file.exists()

    def test_save_creates_parent_directories(self, temp_dir):
        """Test that save creates parent directories."""
        state_file = temp_dir / "subdir" / "nested" / "state.json"
        state = DownloadState(state_file=state_file)

        state.load()
        state.save()

        assert state_file.exists()
        assert state_file.parent.exists()

    def test_mark_downloaded_requires_load(self, temp_dir):
        """Test that mark_downloaded requires state to be loaded first."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)

        with pytest.raises(ValueError, match="State must be loaded"):
            state.mark_downloaded(
                provider="gofast",
                setup_id=123,
                updated_date=datetime.now(),
                file_paths=[Path("/tmp/setup.sto")],
            )

    def test_mark_downloaded_stores_record(self, temp_dir):
        """Test marking a setup as downloaded."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        now = datetime(2024, 1, 15, 10, 30, 0)
        file_path = temp_dir / "setup.sto"
        file_path.write_text("test setup")

        state.mark_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
            file_paths=[file_path],
        )

        assert state.is_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
        )

    def test_is_downloaded_checks_file_exists(self, temp_dir):
        """Test that is_downloaded checks if file exists."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        now = datetime(2024, 1, 15, 10, 30, 0)
        file_path = temp_dir / "setup.sto"

        # Mark as downloaded but don't create file
        state.mark_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
            file_paths=[file_path],
        )

        # Should return False because file doesn't exist
        assert not state.is_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
        )

        # Create the file
        file_path.write_text("test setup")

        # Now should return True
        assert state.is_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
        )

    def test_is_downloaded_checks_updated_date(self, temp_dir):
        """Test that is_downloaded checks if updated_date changed."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        old_date = datetime(2024, 1, 15, 10, 30, 0)
        new_date = datetime(2024, 1, 16, 10, 30, 0)
        file_path = temp_dir / "setup.sto"
        file_path.write_text("test setup")

        # Mark as downloaded with old date
        state.mark_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=old_date,
            file_paths=[file_path],
        )

        # Should return False with new date
        assert not state.is_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=new_date,
        )

        # Should return True with old date
        assert state.is_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=old_date,
        )

    def test_is_downloaded_provider_not_in_state(self, temp_dir):
        """Test is_downloaded when provider not in state."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        assert not state.is_downloaded(
            provider="unknown",
            setup_id=123,
            updated_date=datetime.now(),
        )

    def test_is_downloaded_id_not_in_state(self, temp_dir):
        """Test is_downloaded when ID not in state for provider."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        file_path = temp_dir / "setup.sto"
        file_path.write_text("test")

        # Add one setup
        state.mark_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=datetime.now(),
            file_paths=[file_path],
        )

        # Check for different ID
        assert not state.is_downloaded(
            provider="gofast",
            setup_id=456,
            updated_date=datetime.now(),
        )

    def test_save_and_load_persistence(self, temp_dir):
        """Test that state persists across save/load cycles."""
        state_file = temp_dir / "state.json"

        # Create and save state
        state1 = DownloadState(state_file=state_file)
        state1.load()

        now = datetime(2024, 1, 15, 10, 30, 0)
        file_path = temp_dir / "setup.sto"
        file_path.write_text("test")

        state1.mark_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
            file_paths=[file_path],
        )
        state1.save()

        # Load in new instance
        state2 = DownloadState(state_file=state_file)
        state2.load()

        assert state2.is_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
        )

    def test_get_stats_empty_state(self, temp_dir):
        """Test get_stats with empty state."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        stats = state.get_stats()

        assert stats == {}

    def test_get_stats_single_provider(self, temp_dir):
        """Test get_stats with single provider."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        now = datetime.now()
        for i in range(3):
            file_path = temp_dir / f"setup_{i}.sto"
            file_path.write_text("test")
            state.mark_downloaded(
                provider="gofast",
                setup_id=i,
                updated_date=now,
                file_paths=[file_path],
            )

        stats = state.get_stats()

        assert stats == {"gofast": 3}

    def test_get_stats_multiple_providers(self, temp_dir):
        """Test get_stats with multiple providers."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        now = datetime.now()

        # Add 3 from gofast
        for i in range(3):
            file_path = temp_dir / f"gofast_{i}.sto"
            file_path.write_text("test")
            state.mark_downloaded(
                provider="gofast",
                setup_id=i,
                updated_date=now,
                file_paths=[file_path],
            )

        # Add 2 from craigs
        for i in range(2):
            file_path = temp_dir / f"craigs_{i}.sto"
            file_path.write_text("test")
            state.mark_downloaded(
                provider="craigs",
                setup_id=i,
                updated_date=now,
                file_paths=[file_path],
            )

        stats = state.get_stats()

        assert stats == {"gofast": 3, "craigs": 2}

    def test_context_manager(self, temp_dir):
        """Test using DownloadState as context manager."""
        state_file = temp_dir / "state.json"
        now = datetime(2024, 1, 15, 10, 30, 0)
        file_path = temp_dir / "setup.sto"
        file_path.write_text("test")

        # Use as context manager
        with DownloadState(state_file=state_file) as state:
            state.mark_downloaded(
                provider="gofast",
                setup_id=123,
                updated_date=now,
                file_paths=[file_path],
            )

        # File should be saved automatically
        assert state_file.exists()

        # Verify data persisted
        with DownloadState(state_file=state_file) as state:
            assert state.is_downloaded(
                provider="gofast",
                setup_id=123,
                updated_date=now,
            )

    def test_context_manager_no_save_on_exception(self, temp_dir):
        """Test that context manager doesn't save on exception."""
        state_file = temp_dir / "state.json"

        try:
            with DownloadState(state_file=state_file):
                # Load state but don't make changes
                raise ValueError("Test error")
        except ValueError:
            pass

        # File shouldn't be created if exception occurred
        # (though in this case we didn't make changes anyway)
        assert not state_file.exists()

    def test_auto_save_feature(self, temp_dir):
        """Test auto_save parameter."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file, auto_save=True)
        state.load()

        now = datetime.now()
        file_path = temp_dir / "setup.sto"
        file_path.write_text("test")

        # mark_downloaded should automatically save
        state.mark_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
            file_paths=[file_path],
        )

        # File should exist without calling save()
        assert state_file.exists()

    def test_json_format(self, temp_dir):
        """Test that saved JSON has correct structure."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        now = datetime(2024, 1, 15, 10, 30, 0)
        file_path = temp_dir / "setup.sto"
        file_path.write_text("test")

        state.mark_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
            file_paths=[file_path],
        )
        state.save()

        # Load JSON and verify structure
        data = json.loads(state_file.read_text())

        assert "gofast" in data
        assert "123" in data["gofast"]
        assert data["gofast"]["123"]["updated_date"] == now.isoformat()
        assert data["gofast"]["123"]["file_paths"] == [str(file_path.absolute())]

    def test_handles_corrupted_records(self, temp_dir):
        """Test that loading handles corrupted records gracefully."""
        state_file = temp_dir / "state.json"

        # Create state with invalid record
        bad_data = {
            "gofast": {
                "123": {
                    "updated_date": "not-a-date",
                    "file_paths": ["/tmp/test.sto"],
                },
                "456": {
                    "updated_date": "2024-01-15T10:30:00",
                    "file_paths": ["/tmp/good.sto"],
                },
            }
        }
        state_file.write_text(json.dumps(bad_data))

        state = DownloadState(state_file=state_file)
        state.load()  # Should not raise, just skip invalid record

        # Valid record should be loaded
        stats = state.get_stats()
        assert stats == {"gofast": 1}

    def test_integer_id_conversion(self, temp_dir):
        """Test that integer IDs are converted to strings."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        now = datetime.now()
        file_path = temp_dir / "setup.sto"
        file_path.write_text("test")

        # Mark with integer ID
        state.mark_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
            file_paths=[file_path],
        )
        state.save()

        # Verify stored as string in JSON
        data = json.loads(state_file.read_text())
        assert "123" in data["gofast"]
        assert 123 not in data["gofast"]

    def test_absolute_path_storage(self, temp_dir):
        """Test that file paths are stored as absolute paths."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)
        state.load()

        now = datetime.now()
        # Use relative path
        file_path = Path("setup.sto")
        (temp_dir / file_path).write_text("test")

        state.mark_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=now,
            file_paths=[file_path],
        )
        state.save()

        # Verify stored as absolute path
        data = json.loads(state_file.read_text())
        stored_paths = data["gofast"]["123"]["file_paths"]
        assert Path(stored_paths[0]).is_absolute()

    def test_load_invalid_json(self, temp_dir):
        """Test that loading invalid JSON raises JSONDecodeError."""
        state_file = temp_dir / "state.json"
        state_file.write_text("not valid json {{{")

        state = DownloadState(state_file=state_file)

        with pytest.raises(json.JSONDecodeError):
            state.load()

    def test_save_without_load(self, temp_dir):
        """Test that saving without loading is a no-op."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)

        # Save without loading first
        state.save()

        # File should not be created
        assert not state_file.exists()

    def test_is_downloaded_without_load(self, temp_dir):
        """Test that is_downloaded returns False when state not loaded."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)

        result = state.is_downloaded(
            provider="gofast",
            setup_id=123,
            updated_date=datetime.now(),
        )

        assert result is False

    def test_get_stats_without_load(self, temp_dir):
        """Test that get_stats returns empty dict when state not loaded."""
        state_file = temp_dir / "state.json"
        state = DownloadState(state_file=state_file)

        stats = state.get_stats()

        assert stats == {}

    def test_load_permission_error(self, temp_dir):
        """Test that loading raises OSError on permission issues."""
        import stat

        state_file = temp_dir / "state.json"
        state_file.write_text("{}")

        # Make file unreadable
        state_file.chmod(0o000)

        state = DownloadState(state_file=state_file)

        try:
            with pytest.raises(OSError):
                state.load()
        finally:
            # Restore permissions for cleanup
            state_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_save_permission_error(self, temp_dir):
        """Test that saving raises OSError on permission issues."""
        import stat

        state_file = temp_dir / "readonly" / "state.json"
        readonly_dir = temp_dir / "readonly"
        readonly_dir.mkdir()

        state = DownloadState(state_file=state_file)
        state.load()

        # Make directory read-only
        readonly_dir.chmod(0o555)

        try:
            with pytest.raises(OSError):
                state.save()
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(stat.S_IRWXU)
