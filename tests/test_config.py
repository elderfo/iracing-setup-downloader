"""Tests for configuration management."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from iracing_setup_downloader.config import Settings, get_settings


class TestSettings:
    """Test suite for Settings class."""

    def test_default_settings(self) -> None:
        """Test that default settings are properly initialized."""
        settings = Settings()

        assert settings.token is None
        assert settings.output_path == Path.home() / "Documents" / "iRacing" / "setups"
        assert settings.max_concurrent == 5
        assert settings.min_delay == 0.5
        assert settings.max_delay == 1.5
        assert settings.timeout == 30
        assert settings.max_retries == 3

    def test_output_path_is_absolute(self) -> None:
        """Test that output_path is always converted to absolute path."""
        settings = Settings()
        assert settings.output_path.is_absolute()

    def test_output_path_tilde_expansion(self) -> None:
        """Test that ~ in output_path is expanded to home directory."""
        with patch.dict(os.environ, {"OUTPUT_PATH": "~/custom/setups"}, clear=False):
            settings = Settings()
            assert str(settings.output_path).startswith(str(Path.home()))
            assert "~" not in str(settings.output_path)

    def test_output_path_relative_conversion(self) -> None:
        """Test that relative paths are converted to absolute."""
        with patch.dict(os.environ, {"OUTPUT_PATH": "relative/path"}, clear=False):
            settings = Settings()
            assert settings.output_path.is_absolute()

    def test_env_var_override_token(self) -> None:
        """Test that TOKEN environment variable overrides default."""
        test_token = "test-bearer-token-123"
        with patch.dict(os.environ, {"TOKEN": test_token}, clear=False):
            settings = Settings()
            assert settings.token == test_token

    def test_env_var_override_gofast_token(self) -> None:
        """Test that GOFAST_TOKEN environment variable works."""
        test_token = "gofast-token-456"
        with patch.dict(os.environ, {"GOFAST_TOKEN": test_token}, clear=False):
            settings = Settings()
            assert settings.token == test_token

    def test_env_var_override_max_concurrent(self) -> None:
        """Test that MAX_CONCURRENT environment variable overrides default."""
        with patch.dict(os.environ, {"MAX_CONCURRENT": "10"}, clear=False):
            settings = Settings()
            assert settings.max_concurrent == 10

    def test_env_var_override_min_delay(self) -> None:
        """Test that MIN_DELAY environment variable overrides default."""
        with patch.dict(os.environ, {"MIN_DELAY": "1.0"}, clear=False):
            settings = Settings()
            assert settings.min_delay == 1.0

    def test_env_var_override_max_delay(self) -> None:
        """Test that MAX_DELAY environment variable overrides default."""
        with patch.dict(
            os.environ, {"MIN_DELAY": "0.5", "MAX_DELAY": "2.0"}, clear=False
        ):
            settings = Settings()
            assert settings.max_delay == 2.0

    def test_env_var_override_timeout(self) -> None:
        """Test that TIMEOUT environment variable overrides default."""
        with patch.dict(os.environ, {"TIMEOUT": "60"}, clear=False):
            settings = Settings()
            assert settings.timeout == 60

    def test_env_var_override_max_retries(self) -> None:
        """Test that MAX_RETRIES environment variable overrides default."""
        with patch.dict(os.environ, {"MAX_RETRIES": "5"}, clear=False):
            settings = Settings()
            assert settings.max_retries == 5

    def test_iracing_setups_path_env_var(self) -> None:
        """Test that IRACING_SETUPS_PATH environment variable works."""
        custom_path = "/custom/iracing/setups"
        with patch.dict(os.environ, {"IRACING_SETUPS_PATH": custom_path}, clear=False):
            settings = Settings()
            assert str(settings.output_path) == custom_path

    def test_max_concurrent_validation_min(self) -> None:
        """Test that max_concurrent must be at least 1."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(max_concurrent=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_max_concurrent_validation_max(self) -> None:
        """Test that max_concurrent cannot exceed 20."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(max_concurrent=21)
        assert "less than or equal to 20" in str(exc_info.value)

    def test_min_delay_validation_negative(self) -> None:
        """Test that min_delay cannot be negative."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(min_delay=-1.0)
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_max_delay_validation_negative(self) -> None:
        """Test that max_delay cannot be negative."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(max_delay=-1.0)
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_max_delay_less_than_min_delay(self) -> None:
        """Test that max_delay must be >= min_delay."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(min_delay=2.0, max_delay=1.0)
        assert "max_delay must be greater than or equal to min_delay" in str(
            exc_info.value
        )

    def test_max_delay_equal_to_min_delay(self) -> None:
        """Test that max_delay can equal min_delay."""
        settings = Settings(min_delay=1.0, max_delay=1.0)
        assert settings.min_delay == 1.0
        assert settings.max_delay == 1.0

    def test_timeout_validation_min(self) -> None:
        """Test that timeout must be at least 1 second."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(timeout=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_max_retries_validation_zero(self) -> None:
        """Test that max_retries can be 0 (no retries)."""
        settings = Settings(max_retries=0)
        assert settings.max_retries == 0

    def test_max_retries_validation_negative(self) -> None:
        """Test that max_retries cannot be negative."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(max_retries=-1)
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_case_insensitive_env_vars(self) -> None:
        """Test that environment variables are case-insensitive."""
        with patch.dict(os.environ, {"timeout": "45"}, clear=False):
            settings = Settings()
            assert settings.timeout == 45

    def test_extra_env_vars_ignored(self) -> None:
        """Test that extra environment variables are ignored."""
        with patch.dict(
            os.environ, {"UNKNOWN_SETTING": "value", "TOKEN": "test"}, clear=False
        ):
            # Should not raise an error
            settings = Settings()
            assert settings.token == "test"


class TestGetSettings:
    """Test suite for get_settings function."""

    def test_get_settings_returns_settings(self) -> None:
        """Test that get_settings returns a Settings instance."""
        # Clear the cache before testing
        get_settings.cache_clear()
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_caching(self) -> None:
        """Test that get_settings returns cached instance."""
        # Clear the cache before testing
        get_settings.cache_clear()

        settings1 = get_settings()
        settings2 = get_settings()

        # Should return the same instance due to lru_cache
        assert settings1 is settings2

    def test_get_settings_cache_invalidation(self) -> None:
        """Test that cache can be manually cleared."""
        get_settings.cache_clear()

        settings1 = get_settings()
        get_settings.cache_clear()
        settings2 = get_settings()

        # Should be different instances after cache clear
        assert settings1 is not settings2

    def test_get_settings_with_env_override(self) -> None:
        """Test get_settings with environment variable override."""
        get_settings.cache_clear()

        with patch.dict(os.environ, {"TOKEN": "cached-token"}, clear=False):
            settings = get_settings()
            assert settings.token == "cached-token"

        # Clear cache for subsequent tests
        get_settings.cache_clear()


class TestSettingsIntegration:
    """Integration tests for Settings with various configurations."""

    def test_complete_custom_configuration(self) -> None:
        """Test Settings with all custom values via environment variables."""
        env_vars = {
            "TOKEN": "integration-test-token",
            "OUTPUT_PATH": "~/test/setups",
            "MAX_CONCURRENT": "8",
            "MIN_DELAY": "1.0",
            "MAX_DELAY": "3.0",
            "TIMEOUT": "45",
            "MAX_RETRIES": "5",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings()

            assert settings.token == "integration-test-token"
            assert "test/setups" in str(settings.output_path)
            assert settings.max_concurrent == 8
            assert settings.min_delay == 1.0
            assert settings.max_delay == 3.0
            assert settings.timeout == 45
            assert settings.max_retries == 5

    def test_partial_configuration(self) -> None:
        """Test Settings with partial custom configuration."""
        env_vars = {
            "TOKEN": "partial-token",
            "MAX_CONCURRENT": "3",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings()

            # Custom values
            assert settings.token == "partial-token"
            assert settings.max_concurrent == 3

            # Default values
            assert settings.min_delay == 0.5
            assert settings.max_delay == 1.5
            assert settings.timeout == 30
            assert settings.max_retries == 3

    def test_path_expansion_complex(self) -> None:
        """Test complex path expansion scenarios."""
        # Test with tilde and multiple path components
        with patch.dict(
            os.environ, {"OUTPUT_PATH": "~/iRacing/cars/setups"}, clear=False
        ):
            settings = Settings()
            path_str = str(settings.output_path)
            assert "~" not in path_str
            assert settings.output_path.is_absolute()
            assert "iRacing/cars/setups" in path_str
