"""State management for tracking downloaded setups."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class DownloadRecord(BaseModel):
    """Record of a downloaded setup.

    Attributes:
        updated_date: ISO format datetime string when setup was last updated
        file_paths: List of absolute paths to the extracted .sto files
    """

    updated_date: str = Field(..., description="ISO format datetime of last update")
    file_paths: list[str] = Field(
        default_factory=list, description="Absolute paths to extracted .sto files"
    )

    # Legacy field for backwards compatibility with old state files
    file_path: str | None = Field(
        default=None, description="Deprecated: single file path for old records"
    )

    @field_validator("updated_date")
    @classmethod
    def validate_datetime_format(cls, v: str) -> str:
        """Validate that updated_date is a valid ISO format datetime string.

        Args:
            v: The datetime string to validate

        Returns:
            The validated datetime string

        Raises:
            ValueError: If the datetime string is not in valid ISO format
        """
        try:
            datetime.fromisoformat(v)
        except ValueError as e:
            msg = f"Invalid ISO datetime format: {v}"
            raise ValueError(msg) from e
        return v

    def get_all_paths(self) -> list[str]:
        """Get all file paths, handling legacy single-path records.

        Returns:
            List of file paths (may be empty for legacy records)
        """
        if self.file_paths:
            return self.file_paths
        if self.file_path:
            return [self.file_path]
        return []


class DownloadState:
    """Manages download state tracking for setup files.

    Stores download history in ~/.iracing-setup-downloader/state.json
    Format: {provider: {id: {updated_date: str, file_path: str}}}

    Example:
        >>> state = DownloadState()
        >>> state.load()
        >>> if not state.is_downloaded("gofast", 123, datetime.now(), Path("setup.sto")):
        ...     # Download the file
        ...     state.mark_downloaded("gofast", 123, datetime.now(), Path("setup.sto"))
        ...     state.save()
        >>> stats = state.get_stats()
        >>> print(f"Downloaded {stats['gofast']} setups from GoFast")
    """

    def __init__(self, state_file: Path | None = None, auto_save: bool = False) -> None:
        """Initialize the download state manager.

        Args:
            state_file: Path to the state file. Defaults to
                ~/.iracing-setup-downloader/state.json
            auto_save: If True, automatically save after mark_downloaded()
        """
        if state_file is None:
            state_file = Path.home() / ".iracing-setup-downloader" / "state.json"
        self._state_file = state_file
        self._auto_save = auto_save
        self._state: dict[str, dict[str, DownloadRecord]] = {}
        self._loaded = False

    @property
    def state_file(self) -> Path:
        """Get the path to the state file.

        Returns:
            Path to the state file
        """
        return self._state_file

    def load(self) -> None:
        """Load state from disk.

        Creates an empty state if the file doesn't exist.
        Creates parent directories if they don't exist.

        Raises:
            json.JSONDecodeError: If the state file contains invalid JSON
            OSError: If there are file system errors reading the file
        """
        try:
            if self._state_file.exists():
                logger.info(f"Loading state from {self._state_file}")
                data = json.loads(self._state_file.read_text(encoding="utf-8"))

                # Validate and convert to DownloadRecord objects
                validated_state: dict[str, dict[str, DownloadRecord]] = {}
                for provider, records in data.items():
                    validated_state[provider] = {}
                    for setup_id, record_data in records.items():
                        try:
                            validated_state[provider][setup_id] = DownloadRecord(
                                **record_data
                            )
                        except Exception as e:
                            logger.warning(
                                f"Skipping invalid record {provider}/{setup_id}: {e}"
                            )
                            continue

                self._state = validated_state
                logger.info(f"Loaded state with {len(self._state)} providers")
            else:
                logger.info("State file doesn't exist, creating new state")
                self._state = {}

            self._loaded = True

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in state file {self._state_file}: {e}")
            raise
        except OSError as e:
            logger.error(f"Error reading state file {self._state_file}: {e}")
            raise

    def save(self) -> None:
        """Save state to disk.

        Creates parent directories if they don't exist.
        Only saves if state has been loaded.

        Raises:
            OSError: If there are file system errors writing the file
        """
        if not self._loaded:
            logger.warning("Attempted to save unloaded state, skipping")
            return

        try:
            # Create parent directory if it doesn't exist
            self._state_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert DownloadRecord objects to dicts for JSON serialization
            serializable_state: dict[str, dict[str, dict[str, str]]] = {}
            for provider, records in self._state.items():
                serializable_state[provider] = {}
                for setup_id, record in records.items():
                    serializable_state[provider][setup_id] = record.model_dump()

            # Write with pretty formatting
            self._state_file.write_text(
                json.dumps(serializable_state, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            logger.info(f"Saved state to {self._state_file}")

        except OSError as e:
            logger.error(f"Error writing state file {self._state_file}: {e}")
            raise

    def is_downloaded(
        self, provider: str, setup_id: int, updated_date: datetime
    ) -> bool:
        """Check if a setup has been downloaded and is still valid.

        A setup is considered downloaded if:
        1. It exists in the state for this provider and ID
        2. At least one extracted file still exists
        3. The updated_date matches the stored value (setup hasn't changed)

        Args:
            provider: Name of the setup provider (e.g., "gofast")
            setup_id: Unique identifier for the setup
            updated_date: When the setup was last updated

        Returns:
            True if the setup is already downloaded and up to date,
            False otherwise
        """
        if not self._loaded:
            logger.warning("State not loaded, returning False for is_downloaded")
            return False

        # Convert ID to string for consistent storage
        id_str = str(setup_id)
        updated_str = updated_date.isoformat()

        # Check if provider and ID exist in state
        if provider not in self._state:
            logger.debug(f"Provider {provider} not in state")
            return False

        if id_str not in self._state[provider]:
            logger.debug(f"Setup {id_str} not in state for provider {provider}")
            return False

        record = self._state[provider][id_str]

        # Check if updated_date matches first (cheaper check)
        if record.updated_date != updated_str:
            logger.info(
                f"Setup {provider}/{id_str} has been updated "
                f"(stored: {record.updated_date}, current: {updated_str})"
            )
            return False

        # Check if at least one extracted file still exists
        file_paths = record.get_all_paths()
        if not file_paths:
            logger.info(f"Setup {provider}/{id_str} has no recorded file paths")
            return False

        files_exist = any(Path(fp).exists() for fp in file_paths)
        if not files_exist:
            logger.info(f"Setup {provider}/{id_str} in state but all files missing")
            return False

        logger.debug(f"Setup {provider}/{id_str} is up to date")
        return True

    def mark_downloaded(
        self,
        provider: str,
        setup_id: int,
        updated_date: datetime,
        file_paths: list[Path],
    ) -> None:
        """Record a successful download.

        Args:
            provider: Name of the setup provider (e.g., "gofast")
            setup_id: Unique identifier for the setup
            updated_date: When the setup was last updated
            file_paths: List of paths to the extracted .sto files

        Raises:
            ValueError: If state hasn't been loaded yet
        """
        if not self._loaded:
            msg = "State must be loaded before marking downloads"
            raise ValueError(msg)

        # Convert ID to string for consistent storage
        id_str = str(setup_id)
        updated_str = updated_date.isoformat()

        # Ensure provider key exists
        if provider not in self._state:
            self._state[provider] = {}

        # Store the download record with all file paths
        self._state[provider][id_str] = DownloadRecord(
            updated_date=updated_str,
            file_paths=[str(fp.absolute()) for fp in file_paths],
        )

        logger.info(
            f"Marked {provider}/{id_str} as downloaded: {len(file_paths)} files"
        )

        # Auto-save if enabled
        if self._auto_save:
            self.save()

    def get_stats(self) -> dict[str, int]:
        """Get download statistics per provider.

        Returns:
            Dictionary mapping provider names to count of downloaded setups.
            Providers with no downloads are not included.

        Example:
            >>> state = DownloadState()
            >>> state.load()
            >>> stats = state.get_stats()
            >>> print(stats)
            {'gofast': 42, 'craigs': 15}
        """
        if not self._loaded:
            logger.warning("State not loaded, returning empty stats")
            return {}

        return {
            provider: len(records)
            for provider, records in self._state.items()
            if records
        }

    def __enter__(self) -> "DownloadState":
        """Enter context manager, loading state.

        Returns:
            Self for use in with statement
        """
        self.load()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager, saving state.

        Args:
            exc_type: Exception type if an error occurred
            exc_val: Exception value if an error occurred
            exc_tb: Exception traceback if an error occurred
        """
        if exc_type is None:
            # Only save if no exception occurred
            self.save()
