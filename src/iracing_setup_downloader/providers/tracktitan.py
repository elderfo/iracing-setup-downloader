"""Track Titan setup provider implementation."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import random
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp

from iracing_setup_downloader.deduplication import DuplicateInfo, ExtractResult
from iracing_setup_downloader.models import SetupRecord, TracKTitanSetupInfo
from iracing_setup_downloader.providers.base import SetupProvider

if TYPE_CHECKING:
    from iracing_setup_downloader.deduplication import DuplicateDetector
    from iracing_setup_downloader.track_matcher import TrackMatcher

logger = logging.getLogger(__name__)


class TracKTitanProviderError(Exception):
    """Base exception for TracKTitan provider errors."""


class TracKTitanAuthenticationError(TracKTitanProviderError):
    """Raised when authentication fails."""


class TracKTitanAPIError(TracKTitanProviderError):
    """Raised when API request fails."""


class TracKTitanDownloadError(TracKTitanProviderError):
    """Raised when setup download fails."""


class TracKTitanProvider(SetupProvider):
    """Provider for Track Titan setups.

    This provider interfaces with the Track Titan API to fetch and download
    iRacing setups. It requires an AWS Cognito JWT access token and user ID
    for authentication.

    Track Titan organizes setups by season/week, with each setup representing
    a car/track combination for a specific racing week. Downloads are provided
    as ZIP files containing .sto setup files.

    Attributes:
        API_BASE: The Track Titan API base URL
        SETUPS_ENDPOINT: The API endpoint for fetching setups
        DOWNLOAD_URL_TEMPLATE: Template for constructing download URLs
        REQUEST_TIMEOUT: Default timeout for HTTP requests in seconds
        DEFAULT_PAGE_LIMIT: Default number of setups per page
        CONSUMER_ID: The x-consumer-id header value
    """

    API_BASE = "https://services.tracktitan.io"
    SETUPS_ENDPOINT = "/api/v2/games/iRacing/setups"
    DOWNLOAD_URL_TEMPLATE = "/api/v2/games/iRacing/setups/{setup_id}/download"
    REQUEST_TIMEOUT = 30.0
    DEFAULT_PAGE_LIMIT = 12
    CONSUMER_ID = "trackTitan"
    PAGE_DELAY_MIN = 1.0
    PAGE_DELAY_MAX = 3.0

    def __init__(
        self,
        access_token: str,
        user_id: str,
        track_matcher: TrackMatcher | None = None,
        duplicate_detector: DuplicateDetector | None = None,
    ) -> None:
        """Initialize the Track Titan provider.

        Args:
            access_token: AWS Cognito JWT access token for authentication
            user_id: Track Titan user UUID for API requests
            track_matcher: Optional TrackMatcher for track-based folder organization
            duplicate_detector: Optional DuplicateDetector for skipping binary duplicates
        """
        self._access_token = access_token
        self._user_id = user_id
        self._track_matcher = track_matcher
        self._duplicate_detector = duplicate_detector
        self._session: aiohttp.ClientSession | None = None
        logger.info("Track Titan provider initialized")

    @property
    def name(self) -> str:
        """Return the provider name.

        Returns:
            The lowercase provider name "tracktitan"
        """
        return "tracktitan"

    def get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests.

        Returns:
            Dictionary containing authorization and custom Track Titan headers.
        """
        return {
            "authorization": self._access_token,
            "x-consumer-id": self.CONSUMER_ID,
            "x-user-device": "desktop",
            "x-user-id": self._user_id,
        }

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
        """Fetch available setups from the Track Titan API.

        Makes paginated GET requests to the setups endpoint and transforms
        the response into a flat list of SetupRecord objects.

        Returns:
            List of SetupRecord objects representing available setups

        Raises:
            TracKTitanAuthenticationError: If authentication fails (401/403)
            TracKTitanAPIError: If the API request fails or returns invalid data
        """
        logger.info("Fetching setups from Track Titan API")

        all_setups: list[SetupRecord] = []
        page = 1

        try:
            while True:
                setups, has_more = await self._fetch_page(page)
                all_setups.extend(setups)

                if not has_more:
                    break

                # Human-like delay between page fetches
                delay = random.uniform(self.PAGE_DELAY_MIN, self.PAGE_DELAY_MAX)
                logger.debug("Waiting %.1fs before fetching next page", delay)
                await asyncio.sleep(delay)

                page += 1

            logger.info("Successfully fetched %d Track Titan setups", len(all_setups))
            return all_setups

        except (TracKTitanAuthenticationError, TracKTitanAPIError):
            raise
        except aiohttp.ClientError as e:
            msg = f"Network error while fetching setups: {e}"
            logger.error(msg)
            raise TracKTitanAPIError(msg) from e
        except Exception as e:
            msg = f"Unexpected error while fetching setups: {e}"
            logger.error(msg)
            raise TracKTitanAPIError(msg) from e

    async def _fetch_page(self, page: int) -> tuple[list[SetupRecord], bool]:
        """Fetch a single page of setups from the API.

        Args:
            page: Page number to fetch (1-indexed)

        Returns:
            Tuple of (list of SetupRecord objects, whether more pages exist)

        Raises:
            TracKTitanAuthenticationError: If authentication fails
            TracKTitanAPIError: If the API request fails
        """
        url = f"{self.API_BASE}{self.SETUPS_ENDPOINT}"
        params = {"page": str(page), "limit": str(self.DEFAULT_PAGE_LIMIT)}

        session = await self._get_session()
        logger.debug("Fetching page %d (limit=%s) from %s", page, params["limit"], url)
        async with session.get(
            url,
            headers=self.get_auth_headers(),
            params=params,
        ) as response:
            if response.status == 401:
                msg = "Authentication failed: Invalid or expired access token"
                logger.error(msg)
                raise TracKTitanAuthenticationError(msg)

            if response.status == 403:
                msg = "Access forbidden: Insufficient permissions"
                logger.error(msg)
                raise TracKTitanAuthenticationError(msg)

            if response.status >= 400:
                error_text = await response.text()
                msg = f"API request failed with status {response.status}: {error_text}"
                logger.error(msg)
                raise TracKTitanAPIError(msg)

            try:
                data = await response.json()
            except aiohttp.ContentTypeError as e:
                msg = f"Invalid JSON response from API: {e}"
                logger.error(msg)
                raise TracKTitanAPIError(msg) from e

            return self._parse_setups_response(data)

    def _parse_setups_response(
        self, data: dict[str, Any]
    ) -> tuple[list[SetupRecord], bool]:
        """Parse the Track Titan setups API response.

        The response structure is:
        {
            "success": true,
            "status": 200,
            "data": {
                "setups": [
                    {
                        "id": "uuid",
                        "title": "...",
                        "config": [{"gameId": "iRacing", "carId": "...", "trackId": "..."}],
                        "period": {"season": "1", "week": "8", "year": 2026, "name": "..."},
                        "hymoSeries": {"seriesName": "..."},
                        "hymoDriver": {"driverName": "..."},
                        "lastUpdatedAt": 1770000194000,
                        "isActive": true,
                        ...
                    }
                ]
            }
        }

        Args:
            data: Raw API response dictionary

        Returns:
            Tuple of (list of SetupRecord objects, whether more pages exist)

        Raises:
            TracKTitanAPIError: If the response structure is invalid
        """
        if not isinstance(data, dict):
            msg = f"Unexpected response type: {type(data).__name__}"
            raise TracKTitanAPIError(msg)

        if not data.get("success"):
            msg = f"API returned error: status {data.get('status')}"
            raise TracKTitanAPIError(msg)

        setups_data = data.get("data", {}).get("setups", [])
        if not isinstance(setups_data, list):
            msg = "Invalid setups data structure"
            raise TracKTitanAPIError(msg)

        setups: list[SetupRecord] = []
        for item in setups_data:
            try:
                setup_record = self._create_setup_record(item)
                if setup_record:
                    setups.append(setup_record)
            except Exception as e:
                logger.warning("Failed to parse setup entry: %s. Skipping.", e)
                continue

        # If we got fewer setups than the page limit, there are no more pages
        has_more = len(setups_data) >= self.DEFAULT_PAGE_LIMIT

        return setups, has_more

    def _create_setup_record(self, item: dict[str, Any]) -> SetupRecord | None:
        """Create a SetupRecord from a Track Titan setup entry.

        Args:
            item: Individual setup entry from the API response

        Returns:
            SetupRecord if parsing succeeds, None otherwise
        """
        setup_id = item.get("id")
        if not setup_id:
            logger.warning("Missing setup ID, skipping")
            return None

        # Extract config (car/track)
        config = item.get("config", [])
        if not config:
            logger.warning("Missing config for setup %s, skipping", setup_id)
            return None

        first_config = config[0]
        car_id = first_config.get("carId", "")
        track_id = first_config.get("trackId", "")
        car_shorthand = first_config.get("carShorthand", "")

        # Extract names from setupCombos (more human-readable)
        setup_combos = item.get("setupCombos", [])
        car_name = ""
        track_name = ""
        if setup_combos:
            first_combo = setup_combos[0]
            car_name = first_combo.get("car", {}).get("name", "")
            track_name = first_combo.get("track", {}).get("name", "")

        if not car_name:
            car_name = self._slug_to_name(car_id)
        if not track_name:
            track_name = self._slug_to_name(track_id)

        # Extract period info (period or its fields can be None)
        period = item.get("period") or {}
        season = period.get("season", "")
        week = period.get("week", "")
        year = period.get("year", "")

        # Extract series and driver (can be None)
        series_name = (item.get("hymoSeries") or {}).get("seriesName", "")
        driver_name = (item.get("hymoDriver") or {}).get("driverName", "")

        # Create TracKTitan-specific info
        tt_info = TracKTitanSetupInfo(
            setup_uuid=setup_id,
            car_id=car_id,
            track_id=track_id,
            car_name=car_name,
            track_name=track_name,
            car_shorthand=car_shorthand,
            series_name=series_name,
            driver_name=driver_name,
            season=season,
            week=week,
            year=year,
            has_wet_setup=item.get("hasWetSetup", False),
            is_bundle=item.get("isBundle", False),
        )

        # Construct download URL
        download_url = (
            f"{self.API_BASE}{self.DOWNLOAD_URL_TEMPLATE.format(setup_id=setup_id)}"
        )

        # Build download name in the standard format for SetupRecord parsing
        download_name = f"IR - V1 - {car_name} - {track_name}"

        # Generate a stable unique numeric ID using SHA-256
        hash_bytes = hashlib.sha256(tt_info.unique_id.encode()).digest()
        unique_id = int.from_bytes(hash_bytes[:4], "big") & 0x7FFFFFFF

        # Build season/version string using 2-digit year for consistency
        short_year = str(year)[-2:] if year else ""
        ver = f"{short_year}S{season} W{week}" if all([year, season, week]) else ""

        # Parse lastUpdatedAt (unix ms timestamp)
        last_updated_ms = item.get("lastUpdatedAt")
        if last_updated_ms and isinstance(last_updated_ms, int):
            updated_date = datetime.fromtimestamp(last_updated_ms / 1000, tz=UTC)
        else:
            updated_date = datetime(2024, 1, 1, tzinfo=UTC)

        # Extract series category (abbreviated)
        series_cat = self._extract_series_category(series_name)

        return SetupRecord(
            id=unique_id,
            download_name=download_name,
            download_url=download_url,
            creation_date=updated_date,
            updated_date=updated_date,
            ver=ver,
            setup_ver="1.0",
            changelog="",
            cat=series_cat,
            series=series_cat,
        )

    def _extract_series_category(self, series_name: str) -> str:
        """Extract a short category from the series name.

        Args:
            series_name: Full series name (e.g., "Production Car Challenge")

        Returns:
            Abbreviated category string
        """
        if not series_name:
            return ""

        # Common abbreviations
        abbreviations = {
            "Production Car Challenge": "PCC",
            "IMSA": "IMSA",
            "GT Sprint Series": "GTS",
            "INDYCAR Series": "INDYCAR",
            "Falken Tyre Sports Car Challenge": "FTSC",
            "Super Formula": "SF",
            "Super Formula Lights": "SFL",
            "Formula C": "FC",
            "Formula B": "FB",
        }

        for name, abbrev in abbreviations.items():
            if name.lower() in series_name.lower():
                return abbrev

        return series_name

    def _slug_to_name(self, slug: str) -> str:
        """Convert a slug/ID to a human-readable name.

        Args:
            slug: URL-safe identifier (e.g., "mx-5_cup")

        Returns:
            Human-readable name (e.g., "Mx 5 Cup")
        """
        return slug.replace("-", " ").replace("_", " ").title()

    async def download_setup(
        self, setup: SetupRecord, output_path: Path
    ) -> ExtractResult:
        """Download and extract a setup ZIP from Track Titan.

        Downloads the setup ZIP file and extracts .sto files to the output path.
        The car folder is determined from the carShorthand field in the ZIP filenames.

        Args:
            setup: The SetupRecord to download
            output_path: Base output directory path (typically iRacing setups folder)

        Returns:
            ExtractResult containing extracted file paths and duplicate info

        Raises:
            TracKTitanDownloadError: If download/extraction fails or no .sto files found
            TracKTitanAuthenticationError: If authentication fails during download
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
                    raise TracKTitanAuthenticationError(msg)

                if response.status == 403:
                    msg = "Download failed: Access forbidden"
                    logger.error(msg)
                    raise TracKTitanAuthenticationError(msg)

                if response.status == 404:
                    msg = f"Download failed: Setup not found at {setup.download_url}"
                    logger.error(msg)
                    raise TracKTitanDownloadError(msg)

                if response.status >= 400:
                    error_text = await response.text()
                    msg = f"Download failed with status {response.status}: {error_text}"
                    logger.error(msg)
                    raise TracKTitanDownloadError(msg)

                # Download ZIP content
                try:
                    content = await response.read()
                except aiohttp.ClientError as e:
                    msg = f"Failed to read download content: {e}"
                    logger.error(msg)
                    raise TracKTitanDownloadError(msg) from e

                # Extract ZIP file with duplicate detection
                extracted_files, duplicates, files_renamed = self._extract_zip(
                    content, output_path, setup
                )

                if not extracted_files and not duplicates:
                    msg = f"No .sto files found in ZIP for setup {setup.id}"
                    logger.error(msg)
                    raise TracKTitanDownloadError(msg)

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

        except (TracKTitanAuthenticationError, TracKTitanDownloadError):
            raise
        except aiohttp.ClientError as e:
            msg = f"Network error while downloading setup: {e}"
            logger.error(msg)
            raise TracKTitanDownloadError(msg) from e
        except Exception as e:
            msg = f"Unexpected error while downloading setup: {e}"
            logger.error(msg)
            raise TracKTitanDownloadError(msg) from e

    def _build_filename(
        self,
        setup: SetupRecord,
        original_filename: str,
    ) -> tuple[str, bool]:
        """Build standardized filename from setup metadata.

        Format: <creator>_<series>_<season>_<track>_<setup_type>.sto
        Missing sections are excluded. No leading/trailing underscores or double
        underscores. Spaces in any component are replaced with underscores.

        Args:
            setup: The setup record with metadata
            original_filename: Original filename from ZIP to extract setup type

        Returns:
            Tuple of (standardized filename, whether spaces were sanitized)
        """
        # Extract setup type from original filename (last part before .sto)
        original_stem = Path(original_filename).stem
        parts = original_stem.replace("_", " ").split()
        setup_type = parts[-1] if parts else ""

        # Build filename components
        components = [
            "TT",  # creator (Track Titan)
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
        when a TrackMatcher is available.

        Args:
            content: ZIP file content as bytes
            output_path: Base directory to extract to
            setup: The setup record with metadata for filename generation

        Returns:
            Tuple of (list of extracted file paths, list of DuplicateInfo,
            count of files that had spaces sanitized)

        Raises:
            TracKTitanDownloadError: If extraction fails
        """
        extracted_files: list[Path] = []
        duplicates: list[DuplicateInfo] = []
        files_renamed: int = 0

        # Resolve track subdirectory if track matcher is available
        track_subdir = ""
        if self._track_matcher:
            match_result = self._track_matcher.match(
                setup.track, category_hint=setup.cat
            )
            if match_result.track_dirpath:
                track_subdir = match_result.track_dirpath.replace("\\", os.sep)
                logger.debug(
                    "Matched track '%s' to path '%s' (confidence: %.2f%s)",
                    setup.track,
                    track_subdir,
                    match_result.confidence,
                    ", ambiguous" if match_result.ambiguous else "",
                )
            else:
                logger.warning(
                    "Could not match track '%s' to iRacing path, using flat structure",
                    setup.track,
                )

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # Check for bad ZIP file
                if zf.testzip() is not None:
                    msg = f"Corrupted ZIP file for setup {setup.id}"
                    logger.error(msg)
                    raise TracKTitanDownloadError(msg)

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

                    # Extract car folder (first path component)
                    path_parts = relative_path.split("/")
                    car_folder = path_parts[0] if len(path_parts) > 1 else ""

                    if not car_folder:
                        # If flat ZIP (no folder), try to derive car folder
                        # from filename pattern
                        car_folder = self._extract_car_folder(path_parts[-1])
                        if not car_folder:
                            logger.warning(
                                "Could not determine car folder for: %s",
                                relative_path,
                            )
                            continue

                    original_filename = path_parts[-1]

                    # Build standardized filename
                    new_filename, was_renamed = self._build_filename(
                        setup, original_filename
                    )
                    if was_renamed:
                        files_renamed += 1

                    # Build output directory
                    output_dir = output_path / car_folder
                    if track_subdir:
                        output_dir = output_dir / track_subdir

                    output_file = output_dir / new_filename

                    # Security: verify output path stays within output_path
                    try:
                        resolved_output = output_file.resolve()
                        resolved_base = output_path.resolve()
                        if not resolved_output.is_relative_to(resolved_base):
                            logger.warning(
                                "Path traversal attempt blocked: %s", output_file
                            )
                            continue
                    except (OSError, ValueError) as e:
                        logger.warning("Could not resolve path %s: %s", output_file, e)
                        continue

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
            raise TracKTitanDownloadError(msg) from e
        except OSError as e:
            msg = f"Failed to extract setup {setup.id}: {e}"
            logger.error(msg)
            raise TracKTitanDownloadError(msg) from e

        return extracted_files, duplicates, files_renamed

    def _extract_car_folder(self, filename: str) -> str | None:
        """Extract the car folder name from a filename.

        Track Titan filenames may follow patterns like:
        "mx5 mx52016 @ bathurst CR.sto" or use iRacing car folder names directly.

        Args:
            filename: Original filename from ZIP

        Returns:
            Car folder name suitable for iRacing, or None if parsing fails
        """
        stem = Path(filename).stem.lower()

        # Try "car @ track setuptype.sto" pattern
        # car_shorthand may list multiple folder names (e.g., "mx5 mx52016"),
        # use the first token as the actual iRacing car folder
        if " @ " in stem:
            car_part = stem.split(" @ ")[0].strip()
            tokens = car_part.split()
            car_folder = tokens[0].replace("-", "") if tokens else ""
        else:
            return None

        # Security: validate car_folder contains only safe characters
        if not car_folder:
            return None

        if car_folder in (".", "..") or "/" in car_folder or "\\" in car_folder:
            logger.warning("Rejected unsafe car folder name: %s", car_folder)
            return None

        if not re.match(r"^[a-z0-9]+$", car_folder):
            logger.warning(
                "Car folder contains non-alphanumeric characters: %s", car_folder
            )
            return None

        return car_folder

    async def close(self) -> None:
        """Clean up provider resources.

        Closes the HTTP session if it exists and is still open.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("HTTP session closed")
            self._session = None
