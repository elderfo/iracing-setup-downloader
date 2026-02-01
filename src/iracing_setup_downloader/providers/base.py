"""Base provider interface for setup providers."""

from abc import ABC, abstractmethod
from pathlib import Path

from iracing_setup_downloader.models import SetupRecord


class SetupProvider(ABC):
    """Abstract base class for setup providers.

    This class defines the interface that all setup providers must implement
    to fetch and download iRacing setups from various sources.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider identifier.

        Returns:
            Provider identifier string (e.g., "gofast")
        """
        ...

    @abstractmethod
    async def fetch_setups(self) -> list[SetupRecord]:
        """Fetch available setups from the provider's API.

        This method retrieves the list of all available setup records
        from the provider's API endpoint.

        Returns:
            List of SetupRecord objects representing available setups

        Raises:
            aiohttp.ClientError: If the API request fails
            ValueError: If the API response is invalid
        """
        ...

    @abstractmethod
    async def download_setup(self, setup: SetupRecord, output_path: Path) -> Path:
        """Download a single setup file.

        Downloads the setup file from the provider and saves it to the
        specified output path.

        Args:
            setup: The SetupRecord to download
            output_path: Directory path where the setup file should be saved

        Returns:
            Path object pointing to the saved setup file

        Raises:
            aiohttp.ClientError: If the download request fails
            IOError: If writing the file fails
            ValueError: If the setup URL is invalid
        """
        ...

    def get_auth_headers(self) -> dict[str, str]:
        """Return authorization headers for API requests.

        This method can be overridden by subclasses to provide custom
        authentication headers. The default implementation returns an
        empty dictionary.

        Returns:
            Dictionary of HTTP headers for authentication
        """
        return {}
