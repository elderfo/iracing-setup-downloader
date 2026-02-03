"""Coach Dave Academy (CDA) setup provider implementation."""

from __future__ import annotations

import io
import logging
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp

from iracing_setup_downloader.deduplication import DuplicateInfo, ExtractResult
from iracing_setup_downloader.models import CDASetupInfo, SetupRecord
from iracing_setup_downloader.providers.base import SetupProvider

if TYPE_CHECKING:
    from iracing_setup_downloader.deduplication import DuplicateDetector
    from iracing_setup_downloader.track_matcher import TrackMatcher

logger = logging.getLogger(__name__)


class CDAProviderError(Exception):
    """Base exception for CDA provider errors."""


class CDAAuthenticationError(CDAProviderError):
    """Raised when authentication fails."""


class CDAAPIError(CDAProviderError):
    """Raised when API request fails."""


class CDADownloadError(CDAProviderError):
    """Raised when setup download fails."""


class CDAProvider(SetupProvider):
    """Provider for Coach Dave Academy setups.

    This provider interfaces with the CDA Delta API to fetch and download
    iRacing setups. It requires a PHPSESSID cookie and x-elle-csrf-token
    header for authentication.

    CDA organizes setups by series/week, with each "setup" representing
    all setups for a given car/track combination in a racing week.
    Downloads are provided as ZIP files containing .sto setup files.

    Attributes:
        CATALOG_ENDPOINT: The CDA API endpoint for fetching the catalog
        DOWNLOAD_URL_TEMPLATE: Template for constructing download URLs
        REQUEST_TIMEOUT: Default timeout for HTTP requests in seconds
    """

    CATALOG_ENDPOINT = "https://delta.coachdaveacademy.com/api/driving/iracing/catalog"
    DOWNLOAD_URL_TEMPLATE = "https://delta.coachdaveacademy.com/iracing/install/{series}/{bundle}/{week}/setups/zip"
    REQUEST_TIMEOUT = 30.0

    def __init__(
        self,
        session_id: str,
        csrf_token: str,
        track_matcher: TrackMatcher | None = None,
        duplicate_detector: DuplicateDetector | None = None,
    ) -> None:
        """Initialize the CDA provider.

        Args:
            session_id: PHPSESSID cookie value for authentication
            csrf_token: x-elle-csrf-token header value for authentication
            track_matcher: Optional TrackMatcher for track-based folder organization
            duplicate_detector: Optional DuplicateDetector for skipping binary duplicates
        """
        self._session_id = session_id
        self._csrf_token = csrf_token
        self._track_matcher = track_matcher
        self._duplicate_detector = duplicate_detector
        self._session: aiohttp.ClientSession | None = None
        logger.info("CDA provider initialized")

    @property
    def name(self) -> str:
        """Return the provider name.

        Returns:
            The lowercase provider name "cda"
        """
        return "cda"

    def get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests.

        Returns:
            Dictionary containing the x-elle-csrf-token header.
        """
        return {"x-elle-csrf-token": self._csrf_token}

    def _get_cookies(self) -> dict[str, str]:
        """Get cookies for API requests.

        Returns:
            Dictionary containing the PHPSESSID cookie.
        """
        return {"PHPSESSID": self._session_id}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session.

        Returns:
            Active aiohttp ClientSession instance

        Note:
            Session is created lazily on first use and reused for subsequent requests.
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
            # Set up cookie jar with our session cookie
            cookies = self._get_cookies()
            self._session = aiohttp.ClientSession(timeout=timeout, cookies=cookies)
            logger.debug("Created new HTTP session")
        return self._session

    async def fetch_setups(self) -> list[SetupRecord]:
        """Fetch available setups from the CDA API.

        Makes a GET request to the catalog endpoint and transforms the nested
        response structure into a flat list of SetupRecord objects.

        Returns:
            List of SetupRecord objects representing available setups

        Raises:
            CDAAuthenticationError: If authentication fails (401/403)
            CDAAPIError: If the API request fails or returns invalid data
        """
        logger.info("Fetching setups from CDA API")

        try:
            session = await self._get_session()
            async with session.get(
                self.CATALOG_ENDPOINT,
                headers=self.get_auth_headers(),
            ) as response:
                if response.status == 401:
                    msg = "Authentication failed: Invalid or expired session"
                    logger.error(msg)
                    raise CDAAuthenticationError(msg)

                if response.status == 403:
                    msg = "Access forbidden: Insufficient permissions"
                    logger.error(msg)
                    raise CDAAuthenticationError(msg)

                if response.status >= 400:
                    error_text = await response.text()
                    msg = f"API request failed with status {response.status}: {error_text}"
                    logger.error(msg)
                    raise CDAAPIError(msg)

                try:
                    data = await response.json()
                except aiohttp.ContentTypeError as e:
                    msg = f"Invalid JSON response from API: {e}"
                    logger.error(msg)
                    raise CDAAPIError(msg) from e

                # Parse the nested catalog structure
                setups = self._parse_catalog(data)

                logger.info("Successfully fetched %d CDA setups", len(setups))
                return setups

        except (CDAAuthenticationError, CDAAPIError):
            raise
        except aiohttp.ClientError as e:
            msg = f"Network error while fetching setups: {e}"
            logger.error(msg)
            raise CDAAPIError(msg) from e
        except Exception as e:
            msg = f"Unexpected error while fetching setups: {e}"
            logger.error(msg)
            raise CDAAPIError(msg) from e

    def _parse_catalog(self, data: dict[str, Any]) -> list[SetupRecord]:
        """Parse the CDA catalog response into SetupRecord objects.

        The catalog structure is:
        {
            "code": 200,
            "data": {
                "<car_slug>": {
                    "<track_slug>": {
                        "<series_name>": [{
                            "series": 160,
                            "seriesName": "25S4 IMSA Racing Series",
                            "bundle": 630,
                            "week": 1,
                            "laptime": "Dry: 1:49.884"
                        }]
                    }
                }
            }
        }

        Args:
            data: Raw API response dictionary

        Returns:
            List of SetupRecord objects

        Raises:
            CDAAPIError: If the response structure is invalid
        """
        if not isinstance(data, dict):
            msg = f"Unexpected response type: {type(data).__name__}"
            raise CDAAPIError(msg)

        # Check response code
        code = data.get("code")
        if code != 200:
            msg = f"API returned error code: {code}"
            raise CDAAPIError(msg)

        catalog_data = data.get("data", {})
        if not isinstance(catalog_data, dict):
            msg = "Invalid catalog data structure"
            raise CDAAPIError(msg)

        setups: list[SetupRecord] = []
        now = datetime.now()

        # Iterate through the nested structure: car > track > series > entries
        for car_slug, tracks in catalog_data.items():
            if not isinstance(tracks, dict):
                logger.warning("Invalid track data for car %s, skipping", car_slug)
                continue

            for track_slug, series_data in tracks.items():
                if not isinstance(series_data, dict):
                    logger.warning(
                        "Invalid series data for %s/%s, skipping", car_slug, track_slug
                    )
                    continue

                for series_name, entries in series_data.items():
                    if not isinstance(entries, list):
                        logger.warning(
                            "Invalid entries for %s/%s/%s, skipping",
                            car_slug,
                            track_slug,
                            series_name,
                        )
                        continue

                    for entry in entries:
                        try:
                            setup_record = self._create_setup_record(
                                car_slug=car_slug,
                                track_slug=track_slug,
                                series_name=series_name,
                                entry=entry,
                                now=now,
                            )
                            if setup_record:
                                setups.append(setup_record)
                        except Exception as e:
                            logger.warning(
                                "Failed to parse catalog entry: %s. Skipping.", e
                            )
                            continue

        return setups

    def _create_setup_record(
        self,
        car_slug: str,
        track_slug: str,
        series_name: str,
        entry: dict[str, Any],
        now: datetime,
    ) -> SetupRecord | None:
        """Create a SetupRecord from a catalog entry.

        Args:
            car_slug: Car identifier from catalog path
            track_slug: Track identifier from catalog path
            series_name: Series name from catalog path
            entry: Individual entry from the catalog
            now: Current datetime for timestamps

        Returns:
            SetupRecord if parsing succeeds, None otherwise
        """
        series_id = entry.get("series")
        bundle_id = entry.get("bundle")
        week = entry.get("week")
        laptime = entry.get("laptime")
        entry_series_name = entry.get("seriesName", series_name)

        if not all([series_id, bundle_id, week]):
            logger.warning("Missing required fields in entry: %s", entry)
            return None

        # Create CDA-specific info for metadata
        cda_info = CDASetupInfo(
            series_id=series_id,
            series_name=entry_series_name,
            bundle_id=bundle_id,
            week_number=week,
            car_slug=car_slug,
            track_slug=track_slug,
            track_name=self._slug_to_name(track_slug),
            laptime=laptime,
        )

        # Construct download URL
        download_url = self.DOWNLOAD_URL_TEMPLATE.format(
            series=series_id,
            bundle=bundle_id,
            week=week,
        )

        # Extract season from series name (e.g., "25S4" from "25S4 IMSA Racing Series")
        season_match = re.match(r"(\d+S\d+)", entry_series_name)
        season = season_match.group(1) if season_match else ""

        # Extract series type (e.g., "IMSA" from "25S4 IMSA Racing Series")
        series_type_match = re.search(
            r"\d+S\d+\s+(.+?)(?:\s+Racing\s+Series)?$", entry_series_name
        )
        series_type = (
            series_type_match.group(1).strip()
            if series_type_match
            else entry_series_name
        )

        # Create a human-readable download name
        car_name = self._slug_to_name(car_slug)
        track_name = self._slug_to_name(track_slug)
        download_name = f"CDA - {car_name} - {track_name}"

        # Generate a unique numeric ID from the compound key
        unique_id = hash(cda_info.unique_id) & 0x7FFFFFFF  # Ensure positive

        return SetupRecord(
            id=unique_id,
            download_name=download_name,
            download_url=download_url,
            creation_date=now,
            updated_date=now,
            ver=f"{season} W{week}",
            setup_ver="1.0",
            changelog="",
            cat=series_type,
            series=series_type,
            # Store CDA-specific info in metadata via model_dump
        )

    def _slug_to_name(self, slug: str) -> str:
        """Convert a URL slug to a human-readable name.

        Args:
            slug: URL-safe identifier (e.g., "watkins-glen-international")

        Returns:
            Human-readable name (e.g., "Watkins Glen International")
        """
        return slug.replace("-", " ").title()

    async def download_setup(
        self, setup: SetupRecord, output_path: Path
    ) -> ExtractResult:
        """Download and extract a setup ZIP from CDA.

        Downloads the setup ZIP file and extracts .sto files to the output path.
        The car folder is determined from the filename pattern in the ZIP.

        Args:
            setup: The SetupRecord to download
            output_path: Base output directory path (typically iRacing setups folder)

        Returns:
            ExtractResult containing extracted file paths and duplicate info

        Raises:
            CDADownloadError: If the download, extraction fails, or no .sto files found
            CDAAuthenticationError: If authentication fails during download
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
                    raise CDAAuthenticationError(msg)

                if response.status == 403:
                    msg = "Download failed: Access forbidden"
                    logger.error(msg)
                    raise CDAAuthenticationError(msg)

                if response.status == 404:
                    msg = f"Download failed: Setup not found at {setup.download_url}"
                    logger.error(msg)
                    raise CDADownloadError(msg)

                if response.status >= 400:
                    error_text = await response.text()
                    msg = f"Download failed with status {response.status}: {error_text}"
                    logger.error(msg)
                    raise CDADownloadError(msg)

                # Download ZIP content
                try:
                    content = await response.read()
                except aiohttp.ClientError as e:
                    msg = f"Failed to read download content: {e}"
                    logger.error(msg)
                    raise CDADownloadError(msg) from e

                # Extract ZIP file with duplicate detection
                extracted_files, duplicates, files_renamed = self._extract_zip(
                    content, output_path, setup
                )

                if not extracted_files and not duplicates:
                    msg = f"No .sto files found in ZIP for setup {setup.id}"
                    logger.error(msg)
                    raise CDADownloadError(msg)

                if duplicates:
                    logger.info(
                        "Skipped %d duplicate files from setup %s",
                        len(duplicates),
                        setup.download_name,
                    )

                logger.info(
                    "Successfully extracted %d files from setup %s%s",
                    len(extracted_files),
                    setup.download_name,
                    f" ({files_renamed} renamed)" if files_renamed > 0 else "",
                )
                return ExtractResult(
                    extracted_files=extracted_files,
                    duplicates=duplicates,
                    files_renamed=files_renamed,
                )

        except (CDAAuthenticationError, CDADownloadError):
            raise
        except aiohttp.ClientError as e:
            msg = f"Network error while downloading setup: {e}"
            logger.error(msg)
            raise CDADownloadError(msg) from e
        except Exception as e:
            msg = f"Unexpected error while downloading setup: {e}"
            logger.error(msg)
            raise CDADownloadError(msg) from e

    def _build_filename(
        self,
        setup: SetupRecord,
        original_filename: str,
    ) -> tuple[str, bool]:
        """Build standardized filename from setup metadata.

        Format: <creator>_<series>_<season>_<track>_<setup_type>.sto
        Missing sections are excluded. No leading/trailing underscores or double underscores.
        Spaces in any component are replaced with underscores.

        Args:
            setup: The setup record with metadata
            original_filename: Original filename from ZIP to extract setup type

        Returns:
            Tuple of (standardized filename, whether spaces were sanitized)
        """
        # Extract setup type from original filename (last part before .sto)
        original_stem = Path(original_filename).stem
        # Get the last word/section as setup type
        parts = original_stem.replace("_", " ").split()
        setup_type = parts[-1] if parts else ""

        # Build filename components
        components = [
            "CDA",  # creator
            setup.series if setup.series else "",
            setup.season if setup.season else "",
            setup.track if setup.track else "",
            setup_type,
        ]

        # Filter out empty components and join with underscores
        non_empty = [c for c in components if c]
        filename = "_".join(non_empty)

        # Track if any spaces exist before sanitizing
        had_spaces = " " in filename

        # Sanitize: replace spaces with underscores
        filename = filename.replace(" ", "_")

        # Safety: ensure no double underscores
        while "__" in filename:
            filename = filename.replace("__", "_")

        # Safety: strip leading/trailing underscores
        filename = filename.strip("_")

        result = f"{filename}.sto" if filename else "setup.sto"
        return result, had_spaces

    def _extract_zip(
        self, content: bytes, output_path: Path, setup: SetupRecord
    ) -> tuple[list[Path], list[DuplicateInfo], int]:
        """Extract ZIP content to the output path.

        Extracts .sto files from the ZIP, preserving the car folder
        (first path component) and optionally organizing by track folder
        when a TrackMatcher is available. Files are renamed to follow
        the standard naming convention. Spaces in filenames are replaced
        with underscores.

        CDA ZIP files have flat structure with filenames like:
        "porsche911gt3r992 @ watkins glen international full race.sto"

        Args:
            content: ZIP file content as bytes
            output_path: Base directory to extract to
            setup: The setup record with metadata for filename generation

        Returns:
            Tuple of (list of extracted file paths, list of DuplicateInfo,
            count of files that had spaces sanitized)

        Raises:
            CDADownloadError: If extraction fails
        """
        extracted_files: list[Path] = []
        duplicates: list[DuplicateInfo] = []
        files_renamed: int = 0

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # Check for bad ZIP file
                if zf.testzip() is not None:
                    msg = f"Corrupted ZIP file for setup {setup.id}"
                    logger.error(msg)
                    raise CDADownloadError(msg)

                for zip_info in zf.infolist():
                    # Skip directories
                    if zip_info.is_dir():
                        continue

                    # Normalize path separators
                    relative_path = zip_info.filename.replace("\\", "/")

                    # Security: prevent path traversal
                    if ".." in relative_path or relative_path.startswith("/"):
                        logger.warning(
                            "Skipping potentially unsafe path: %s", relative_path
                        )
                        continue

                    # Only process .sto files
                    if not relative_path.lower().endswith(".sto"):
                        logger.debug("Skipping non-.sto file: %s", relative_path)
                        continue

                    original_filename = Path(relative_path).name

                    # Extract car folder from CDA filename pattern
                    # Format: "carname @ trackname setuptype.sto"
                    car_folder = self._extract_car_folder(original_filename)
                    if not car_folder:
                        logger.warning(
                            "Could not extract car folder from: %s", original_filename
                        )
                        continue

                    # Resolve track subdirectory if track matcher is available
                    track_subdir = ""
                    if self._track_matcher:
                        match_result = self._track_matcher.match(
                            setup.track, category_hint=setup.cat
                        )
                        if match_result.track_dirpath:
                            track_subdir = match_result.track_dirpath.replace(
                                "\\", os.sep
                            )
                            logger.debug(
                                "Matched track '%s' to path '%s' (confidence: %.2f%s)",
                                setup.track,
                                track_subdir,
                                match_result.confidence,
                                ", ambiguous" if match_result.ambiguous else "",
                            )
                        else:
                            logger.warning(
                                "Could not match track '%s' to iRacing path",
                                setup.track,
                            )

                    # Build standardized filename
                    new_filename, was_renamed = self._build_filename(
                        setup, original_filename
                    )
                    if was_renamed:
                        files_renamed += 1

                    # Build output directory: <output_path>/<car_folder>/[<track_subdir>/]
                    output_dir = output_path / car_folder
                    if track_subdir:
                        output_dir = output_dir / track_subdir

                    output_file = output_dir / new_filename

                    # Read file content for duplicate checking
                    with zf.open(zip_info) as src:
                        file_content = src.read()

                    # Check for binary duplicates before writing
                    if self._duplicate_detector:
                        content_hash = (
                            self._duplicate_detector.hash_cache.compute_hash_from_bytes(
                                file_content
                            )
                        )
                        existing = self._duplicate_detector.find_duplicate_by_hash(
                            content_hash, len(file_content), original_filename
                        )
                        if existing:
                            dup_info = DuplicateInfo(
                                source_path=output_file,
                                existing_path=existing,
                                file_hash=content_hash,
                                file_size=len(file_content),
                            )
                            duplicates.append(dup_info)
                            logger.debug(
                                "Skipping duplicate: %s (matches %s)",
                                new_filename,
                                existing.name,
                            )
                            continue

                    # Create output directory
                    output_dir.mkdir(parents=True, exist_ok=True)

                    # Write file
                    output_file.write_bytes(file_content)

                    # Add to duplicate detector index
                    if self._duplicate_detector:
                        self._duplicate_detector.add_to_index(output_file)

                    logger.debug("Extracted: %s", output_file)
                    extracted_files.append(output_file)

        except zipfile.BadZipFile as e:
            msg = f"Invalid ZIP file for setup {setup.id}: {e}"
            logger.error(msg)
            raise CDADownloadError(msg) from e
        except OSError as e:
            msg = f"Failed to extract setup {setup.id}: {e}"
            logger.error(msg)
            raise CDADownloadError(msg) from e

        return extracted_files, duplicates, files_renamed

    def _extract_car_folder(self, filename: str) -> str | None:
        """Extract the car folder name from a CDA filename.

        CDA filenames follow the pattern: "carname @ trackname setuptype.sto"
        The car name needs to be converted to iRacing's folder format.

        Args:
            filename: Original filename from CDA ZIP

        Returns:
            Car folder name suitable for iRacing, or None if parsing fails
        """
        # Remove .sto extension
        stem = Path(filename).stem.lower()

        # Split on " @ " to separate car and track
        if " @ " in stem:
            car_part = stem.split(" @ ")[0].strip()
        else:
            # Fallback: try to find car name some other way
            logger.debug("Filename doesn't match expected pattern: %s", filename)
            return None

        # Convert to iRacing folder format: remove spaces and special chars
        car_folder = car_part.replace(" ", "").replace("-", "")

        return car_folder if car_folder else None

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
