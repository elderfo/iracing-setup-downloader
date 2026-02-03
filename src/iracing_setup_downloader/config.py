"""Configuration management for iRacing Setup Downloader."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.

    Configuration priority (highest to lowest):
    1. Environment variables
    2. .env file
    3. Default values

    Attributes:
        token: Go Fast bearer token for API authentication
        output_path: Directory where downloaded setups will be saved
        max_concurrent: Maximum number of parallel downloads allowed
        min_delay: Minimum seconds to wait between consecutive downloads
        max_delay: Maximum seconds to wait between consecutive downloads
        timeout: Connection timeout in seconds for HTTP requests
        max_retries: Maximum number of retry attempts for failed downloads
    """

    token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("token", "gofast_token"),
        description="Go Fast bearer token for API authentication",
    )
    cda_session_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("cda_session_id"),
        description="CDA PHPSESSID cookie for API authentication",
    )
    cda_csrf_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("cda_csrf_token"),
        description="CDA x-elle-csrf-token header for API authentication",
    )
    output_path: Path = Field(
        default=Path.home() / "Documents" / "iRacing" / "setups",
        validation_alias=AliasChoices("output_path", "iracing_setups_path"),
        description="Directory where downloaded setups will be saved",
    )
    max_concurrent: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of parallel downloads",
    )
    min_delay: float = Field(
        default=0.5,
        ge=0.0,
        description="Minimum seconds between downloads",
    )
    max_delay: float = Field(
        default=1.5,
        ge=0.0,
        description="Maximum seconds between downloads",
    )
    timeout: int = Field(
        default=30,
        ge=1,
        description="Connection timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts for failed downloads",
    )
    tracks_data_path: Path | None = Field(
        default=None,
        description="Custom path to tracks.json. If None, uses bundled data.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        # Map environment variable names to field names
        env_nested_delimiter="__",
    )

    @field_validator("output_path", mode="before")
    @classmethod
    def expand_path(cls, v: str | Path) -> Path:
        """Expand ~ and environment variables in the output path.

        Args:
            v: Path value to expand

        Returns:
            Expanded absolute path
        """
        if isinstance(v, str):
            # Expand ~ to home directory and resolve environment variables
            expanded = Path(v).expanduser().resolve()
            return expanded
        return Path(v).expanduser().resolve()

    @field_validator("max_delay")
    @classmethod
    def validate_delay_range(cls, v: float, info) -> float:
        """Ensure max_delay is greater than or equal to min_delay.

        Args:
            v: max_delay value
            info: Validation context containing other field values

        Returns:
            Validated max_delay value

        Raises:
            ValueError: If max_delay is less than min_delay
        """
        if "min_delay" in info.data and v < info.data["min_delay"]:
            raise ValueError("max_delay must be greater than or equal to min_delay")
        return v


@lru_cache
def get_settings() -> Settings:
    """Get cached singleton instance of application settings.

    This function uses lru_cache to ensure settings are loaded only once
    and reused throughout the application lifecycle.

    Returns:
        Settings instance with configuration loaded from environment
        variables and .env file

    Example:
        >>> settings = get_settings()
        >>> print(settings.output_path)
        /home/user/Documents/iRacing/setups
    """
    return Settings()
