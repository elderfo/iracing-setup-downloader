"""GoFast setup provider implementation."""

import io
import logging
import zipfile
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

                # Handle API response structure: {status, msg, data: {records: [...]}}
                if isinstance(data, dict):
                    if not data.get("status"):
                        msg = f"API returned error: {data.get('msg', 'Unknown error')}"
                        logger.error(msg)
                        raise GoFastAPIError(msg)
                    records = data.get("data", {}).get("records", [])
                elif isinstance(data, list):
                    # Fallback for direct list response
                    records = data
                else:
                    msg = f"Unexpected response format from API: {type(data).__name__}"
                    logger.error(msg)
                    raise GoFastAPIError(msg)

                setups = []
                for item in records:
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

    async def download_setup(self, setup: SetupRecord, output_path: Path) -> list[Path]:
        """Download and extract a setup ZIP from GoFast.

        Downloads the setup ZIP file and extracts its contents to the output path.
        The ZIP contains the proper iRacing folder structure that is preserved.

        Args:
            setup: The SetupRecord to download
            output_path: Base output directory path (typically iRacing setups folder)

        Returns:
            List of paths to the extracted setup files (.sto files)

        Raises:
            GoFastDownloadError: If the download or extraction fails
            GoFastAuthenticationError: If authentication fails during download
        """
        logger.info("Downloading setup: %s", setup.download_name)

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

                # Download ZIP content
                try:
                    content = await response.read()
                except aiohttp.ClientError as e:
                    msg = f"Failed to read download content: {e}"
                    logger.error(msg)
                    raise GoFastDownloadError(msg) from e

                # Extract ZIP file
                extracted_files = self._extract_zip(content, output_path, setup)
                logger.info(
                    "Successfully extracted %d files from setup %s",
                    len(extracted_files),
                    setup.download_name,
                )
                return extracted_files

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

    def _extract_zip(
        self, content: bytes, output_path: Path, setup: SetupRecord
    ) -> list[Path]:
        """Extract ZIP content to the output path.

        Preserves the folder structure inside the ZIP which contains
        the iRacing-compatible directory structure.

        Args:
            content: ZIP file content as bytes
            output_path: Base directory to extract to
            setup: The setup record (for logging)

        Returns:
            List of paths to extracted .sto files

        Raises:
            GoFastDownloadError: If extraction fails
        """
        extracted_files: list[Path] = []

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # Check for bad ZIP file
                if zf.testzip() is not None:
                    msg = f"Corrupted ZIP file for setup {setup.id}"
                    logger.error(msg)
                    raise GoFastDownloadError(msg)

                for zip_info in zf.infolist():
                    # Skip directories
                    if zip_info.is_dir():
                        continue

                    # Normalize path separators (Windows -> Unix)
                    relative_path = zip_info.filename.replace("\\", "/")

                    # Security: prevent path traversal
                    if ".." in relative_path or relative_path.startswith("/"):
                        logger.warning(
                            "Skipping potentially unsafe path: %s", relative_path
                        )
                        continue

                    output_file = output_path / relative_path
                    output_file.parent.mkdir(parents=True, exist_ok=True)

                    # Extract file
                    with zf.open(zip_info) as src:
                        output_file.write_bytes(src.read())

                    logger.debug("Extracted: %s", output_file)

                    # Track .sto files
                    if output_file.suffix.lower() == ".sto":
                        extracted_files.append(output_file)

        except zipfile.BadZipFile as e:
            msg = f"Invalid ZIP file for setup {setup.id}: {e}"
            logger.error(msg)
            raise GoFastDownloadError(msg) from e
        except OSError as e:
            msg = f"Failed to extract setup {setup.id}: {e}"
            logger.error(msg)
            raise GoFastDownloadError(msg) from e

        return extracted_files

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
