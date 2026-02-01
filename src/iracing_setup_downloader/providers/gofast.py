"""GoFast setup provider implementation."""

import logging
from pathlib import Path

import aiohttp

from iracing_setup_downloader.models import SetupRecord
from iracing_setup_downloader.providers.base import SetupProvider

logger = logging.getLogger(__name__)


class GoFastProviderError(Exception):
    """Base exception for GoFast provider errors."""


class GoFastAuthenticationError(GoFastProviderError):
    """Raised when authentication fails."""


class GoFastAPIError(GoFastProviderError):
    """Raised when API request fails."""


class GoFastDownloadError(GoFastProviderError):
    """Raised when setup download fails."""


class GoFastProvider(SetupProvider):
    """Provider for GoFast setups.

    This provider interfaces with the GoFast API to fetch and download
    iRacing setups. It requires a bearer token for authentication.

    Attributes:
        API_ENDPOINT: The GoFast API endpoint for fetching setups
        REQUEST_TIMEOUT: Default timeout for HTTP requests in seconds
    """

    API_ENDPOINT = "https://go-fast.gg:5002/api/subscription/manualinstall"
    REQUEST_TIMEOUT = 30.0

    def __init__(self, token: str) -> None:
        """Initialize the GoFast provider.

        Args:
            token: GoFast API bearer token (should include "Bearer " prefix)
        """
        self._token = token
        self._session: aiohttp.ClientSession | None = None
        logger.info("GoFast provider initialized")

    @property
    def name(self) -> str:
        """Return the provider name.

        Returns:
            The lowercase provider name "gofast"
        """
        return "gofast"

    def get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests.

        Returns:
            Dictionary containing the Authorization header with the token.
            The token is used as-is since it already includes the "Bearer " prefix.
        """
        return {"Authorization": self._token}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session.

        Returns:
            Active aiohttp ClientSession instance

        Note:
            Session is created lazily on first use and reused for subsequent requests.
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
            logger.debug("Created new HTTP session")
        return self._session

    async def fetch_setups(self) -> list[SetupRecord]:
        """Fetch available setups from the GoFast API.

        Makes a GET request to the API endpoint and parses the response
        into a list of SetupRecord objects.

        Returns:
            List of SetupRecord objects representing available setups

        Raises:
            GoFastAuthenticationError: If authentication fails (401/403)
            GoFastAPIError: If the API request fails or returns invalid data
        """
        logger.info("Fetching setups from GoFast API")

        try:
            session = await self._get_session()
            async with session.get(
                self.API_ENDPOINT,
                headers=self.get_auth_headers(),
            ) as response:
                if response.status == 401:
                    msg = "Authentication failed: Invalid or expired token"
                    logger.error(msg)
                    raise GoFastAuthenticationError(msg)

                if response.status == 403:
                    msg = "Access forbidden: Insufficient permissions"
                    logger.error(msg)
                    raise GoFastAuthenticationError(msg)

                if response.status >= 400:
                    error_text = await response.text()
                    msg = f"API request failed with status {response.status}: {error_text}"
                    logger.error(msg)
                    raise GoFastAPIError(msg)

                try:
                    data = await response.json()
                except aiohttp.ContentTypeError as e:
                    msg = f"Invalid JSON response from API: {e}"
                    logger.error(msg)
                    raise GoFastAPIError(msg) from e

                if not isinstance(data, list):
                    msg = f"Expected list response from API, got {type(data).__name__}"
                    logger.error(msg)
                    raise GoFastAPIError(msg)

                setups = []
                for item in data:
                    try:
                        setup_record = SetupRecord(**item)
                        setups.append(setup_record)
                    except Exception as e:
                        logger.warning("Failed to parse setup record: %s. Skipping.", e)
                        continue

                logger.info("Successfully fetched %d setups", len(setups))
                return setups

        except (GoFastAuthenticationError, GoFastAPIError):
            raise
        except aiohttp.ClientError as e:
            msg = f"Network error while fetching setups: {e}"
            logger.error(msg)
            raise GoFastAPIError(msg) from e
        except Exception as e:
            msg = f"Unexpected error while fetching setups: {e}"
            logger.error(msg)
            raise GoFastAPIError(msg) from e

    async def download_setup(self, setup: SetupRecord, output_path: Path) -> Path:
        """Download a specific setup from GoFast.

        Downloads the setup file and saves it to the appropriate location
        based on the setup's metadata (car, track, etc.).

        Args:
            setup: The SetupRecord to download
            output_path: Base output directory path

        Returns:
            Path to the downloaded setup file

        Raises:
            GoFastDownloadError: If the download fails
            GoFastAuthenticationError: If authentication fails during download
        """
        logger.info("Downloading setup: %s", setup.download_name)

        # Create output directory structure: output_path / car / track /
        output_directory = output_path / setup.get_output_directory()
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
            logger.debug("Created output directory: %s", output_directory)
        except OSError as e:
            msg = f"Failed to create output directory {output_directory}: {e}"
            logger.error(msg)
            raise GoFastDownloadError(msg) from e

        # Determine output file path
        output_file = output_directory / setup.get_output_filename()
        logger.debug("Downloading to: %s", output_file)

        try:
            session = await self._get_session()
            async with session.get(
                setup.download_url,
                headers=self.get_auth_headers(),
            ) as response:
                if response.status == 401:
                    msg = "Download failed: Authentication required"
                    logger.error(msg)
                    raise GoFastAuthenticationError(msg)

                if response.status == 403:
                    msg = "Download failed: Access forbidden"
                    logger.error(msg)
                    raise GoFastAuthenticationError(msg)

                if response.status == 404:
                    msg = f"Download failed: Setup not found at {setup.download_url}"
                    logger.error(msg)
                    raise GoFastDownloadError(msg)

                if response.status >= 400:
                    error_text = await response.text()
                    msg = f"Download failed with status {response.status}: {error_text}"
                    logger.error(msg)
                    raise GoFastDownloadError(msg)

                # Download file content
                try:
                    content = await response.read()
                except aiohttp.ClientError as e:
                    msg = f"Failed to read download content: {e}"
                    logger.error(msg)
                    raise GoFastDownloadError(msg) from e

                # Write to file
                try:
                    output_file.write_bytes(content)
                    logger.info(
                        "Successfully downloaded setup to %s (%d bytes)",
                        output_file,
                        len(content),
                    )
                except OSError as e:
                    msg = f"Failed to write setup file to {output_file}: {e}"
                    logger.error(msg)
                    raise GoFastDownloadError(msg) from e

                return output_file

        except (GoFastAuthenticationError, GoFastDownloadError):
            raise
        except aiohttp.ClientError as e:
            msg = f"Network error while downloading setup: {e}"
            logger.error(msg)
            raise GoFastDownloadError(msg) from e
        except Exception as e:
            msg = f"Unexpected error while downloading setup: {e}"
            logger.error(msg)
            raise GoFastDownloadError(msg) from e

    async def close(self) -> None:
        """Clean up provider resources.

        Closes the HTTP session if it exists and is still open.
        This method should be called when the provider is no longer needed
        to ensure proper cleanup of network resources.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("HTTP session closed")
            self._session = None
