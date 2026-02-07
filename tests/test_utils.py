"""Tests for the shared utility functions."""

from iracing_setup_downloader.utils import sanitize_filename


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_sanitize_filename_with_spaces(self):
        """Test that spaces are replaced with underscores."""
        result, changed = sanitize_filename("GO Fast Setup Race.sto")

        assert result == "GO_Fast_Setup_Race.sto"
        assert changed is True

    def test_sanitize_filename_no_spaces(self):
        """Test that filenames without spaces are unchanged."""
        result, changed = sanitize_filename("GoFast_Setup_Race.sto")

        assert result == "GoFast_Setup_Race.sto"
        assert changed is False

    def test_sanitize_filename_empty(self):
        """Test that empty filenames are handled."""
        result, changed = sanitize_filename("")

        assert result == ""
        assert changed is False

    def test_sanitize_filename_only_spaces(self):
        """Test filename with only spaces."""
        result, changed = sanitize_filename("   ")

        assert result == "___"
        assert changed is True

    def test_sanitize_filename_multiple_consecutive_spaces(self):
        """Test filename with multiple consecutive spaces."""
        result, changed = sanitize_filename("GO  Fast   Setup.sto")

        assert result == "GO__Fast___Setup.sto"
        assert changed is True

    def test_sanitize_filename_leading_trailing_spaces(self):
        """Test filename with leading and trailing spaces."""
        result, changed = sanitize_filename(" setup.sto ")

        assert result == "_setup.sto_"
        assert changed is True

    def test_sanitize_filename_forward_slash(self):
        """Test that forward slashes are replaced with underscores."""
        result, changed = sanitize_filename("BES/WEC_Setup.sto")

        assert result == "BES_WEC_Setup.sto"
        assert changed is True

    def test_sanitize_filename_backslash(self):
        """Test that backslashes are replaced with underscores."""
        result, changed = sanitize_filename("BES\\WEC_Setup.sto")

        assert result == "BES_WEC_Setup.sto"
        assert changed is True

    def test_sanitize_filename_mixed_unsafe_characters(self):
        """Test filename with spaces and path separators."""
        result, changed = sanitize_filename("Nürburgring - BES/WEC Setup.sto")

        assert result == "Nürburgring_-_BES_WEC_Setup.sto"
        assert changed is True
