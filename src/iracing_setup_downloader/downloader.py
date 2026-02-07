"""Setup downloader orchestration with concurrent downloads and retry logic."""

import asyncio
import logging
import random
from pathlib import Path

from pydantic import BaseModel, Field
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
)

from iracing_setup_downloader.models import SetupRecord
from iracing_setup_downloader.providers.base import SetupProvider
from iracing_setup_downloader.state import DownloadState

logger = logging.getLogger(__name__)


class DownloadResult(BaseModel):
    """Result of a download operation.

    Attributes:
        total_available: Total number of setups available from provider
        skipped: Number of setups skipped (already downloaded)
        downloaded: Number of setups successfully downloaded
        failed: Number of setups that failed to download
        errors: List of tuples containing failed setups and error messages
        duplicates_skipped: Number of duplicate files skipped during extraction
        bytes_saved: Total bytes saved by skipping duplicates
        files_renamed: Number of files whose names were sanitized (spaces to underscores)
    """

    total_available: int = Field(..., description="Total setups available")
    skipped: int = Field(..., description="Setups already downloaded")
    downloaded: int = Field(..., description="Setups successfully downloaded")
    failed: int = Field(..., description="Setups that failed to download")
    errors: list[tuple[str, str]] = Field(
        default_factory=list,
        description="List of (setup_id, error_message) tuples",
    )
    duplicates_skipped: int = Field(
        default=0, description="Duplicate files skipped during extraction"
    )
    bytes_saved: int = Field(
        default=0, description="Bytes saved by skipping duplicates"
    )
    files_renamed: int = Field(
        default=0,
        description="Files whose names were sanitized (spaces to underscores)",
    )

    def __str__(self) -> str:
        """Return human-readable summary of download results.

        Returns:
            Formatted string with download statistics
        """
        lines = [
            f"Total available: {self.total_available}",
            f"Downloaded: {self.downloaded}",
            f"Skipped: {self.skipped}",
            f"Failed: {self.failed}",
        ]

        if self.duplicates_skipped > 0:
            lines.append(f"Duplicates skipped: {self.duplicates_skipped}")

        if self.files_renamed > 0:
            lines.append(f"Files renamed: {self.files_renamed}")

        if self.errors:
            lines.append("\nErrors:")
            for setup_id, error in self.errors:
                lines.append(f"  - Setup {setup_id}: {error}")

        return "\n".join(lines)


class SetupDownloader:
    """Orchestrates downloading setups from providers with concurrency control.

    This class manages the download process with features including:
    - Concurrent downloads with configurable limits
    - Random delays between downloads
    - Exponential backoff retry logic
    - State tracking to avoid re-downloading
    - Progress bar visualization
    - Graceful handling of interruptions

    Example:
        >>> async with GoFastProvider(token="...") as provider:
        ...     state = DownloadState()
        ...     state.load()
        ...     downloader = SetupDownloader(
        ...         provider=provider,
        ...         state=state,
        ...         max_concurrent=5,
        ...     )
        ...     result = await downloader.download_all(Path("./setups"))
        ...     print(f"Downloaded {result.downloaded} setups")
    """

    def __init__(
        self,
        provider: SetupProvider,
        state: DownloadState,
        max_concurrent: int = 5,
        min_delay: float = 0.5,
        max_delay: float = 1.5,
        max_retries: int = 3,
    ) -> None:
        """Initialize the setup downloader.

        Args:
            provider: The setup provider to download from
            state: Download state tracker for avoiding duplicates
            max_concurrent: Maximum number of concurrent downloads
            min_delay: Minimum delay in seconds between downloads
            max_delay: Maximum delay in seconds between downloads
            max_retries: Maximum number of retry attempts for failed downloads
        """
        self._provider = provider
        self._state = state
        self._max_concurrent = max_concurrent
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._max_retries = max_retries
        self._cancelled = False

    async def download_all(
        self, output_path: Path, dry_run: bool = False, limit: int | None = None
    ) -> DownloadResult:
        """Download all available setups from the provider.

        Fetches all setups, filters out already-downloaded ones, and downloads
        the remaining setups with concurrency control and retry logic.

        Args:
            output_path: Base directory path for saving downloaded setups
            dry_run: If True, only simulate downloads without actually downloading
            limit: Maximum number of new setups to download. If None, download all.

        Returns:
            DownloadResult containing download statistics and any errors

        Raises:
            ValueError: If state hasn't been loaded
            aiohttp.ClientError: If provider communication fails
        """
        if not self._state._loaded:
            msg = "State must be loaded before downloading"
            raise ValueError(msg)

        logger.info(f"Fetching setups from {self._provider.name}")

        try:
            # Fetch all available setups
            all_setups = await self._provider.fetch_setups()
            logger.info(f"Found {len(all_setups)} total setups")

            if not all_setups:
                return DownloadResult(
                    total_available=0,
                    skipped=0,
                    downloaded=0,
                    failed=0,
                )

            # Filter out already-downloaded setups
            setups_to_download = self._filter_new_setups(all_setups, output_path)
            already_downloaded = len(all_setups) - len(setups_to_download)

            # Apply limit if specified
            if limit is not None and len(setups_to_download) > limit:
                logger.info(
                    f"Limiting downloads to {limit} of {len(setups_to_download)} new setups"
                )
                setups_to_download = setups_to_download[:limit]

            result = DownloadResult(
                total_available=len(all_setups),
                skipped=already_downloaded,
                downloaded=0,
                failed=0,
            )

            logger.info(
                f"Skipping {result.skipped} already-downloaded setups, "
                f"{len(setups_to_download)} to download"
            )

            if not setups_to_download:
                return result

            if dry_run:
                logger.info(f"Dry run: would download {len(setups_to_download)} setups")
                return result

            # Download setups with concurrency control
            await self._download_concurrent(setups_to_download, output_path, result)

            return result

        except asyncio.CancelledError:
            logger.warning("Download cancelled by user")
            self._cancelled = True
            raise
        except Exception as e:
            logger.error(f"Error during download_all: {e}")
            raise

    def _filter_new_setups(
        self,
        setups: list[SetupRecord],
        output_path: Path,  # noqa: ARG002
    ) -> list[SetupRecord]:
        """Filter out setups that have already been downloaded.

        Args:
            setups: List of all available setups
            output_path: Base output directory (unused, kept for interface consistency)

        Returns:
            List of setups that need to be downloaded
        """
        new_setups: list[SetupRecord] = []

        for setup in setups:
            # Check if already downloaded by ID and updated_date
            if not self._state.is_downloaded(
                self._provider.name, setup.id, setup.updated_date
            ):
                new_setups.append(setup)
            else:
                logger.debug(f"Skipping already-downloaded setup: {setup.id}")

        return new_setups

    async def _download_concurrent(
        self,
        setups: list[SetupRecord],
        output_path: Path,
        result: DownloadResult,
    ) -> None:
        """Download setups concurrently with progress tracking.

        Args:
            setups: List of setups to download
            output_path: Base output directory
            result: DownloadResult to update with progress
        """
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self._max_concurrent)

        # Create progress bar
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            DownloadColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task_id = progress.add_task(
                f"Downloading from {self._provider.name}",
                total=len(setups),
            )

            # Create download tasks
            tasks = [
                asyncio.create_task(
                    self._download_with_semaphore(
                        semaphore, setup, output_path, progress, task_id, result
                    )
                )
                for setup in setups
            ]

            # Run all downloads concurrently
            try:
                await asyncio.gather(*tasks, return_exceptions=False)
            except asyncio.CancelledError:
                logger.warning("Downloads cancelled, cleaning up...")
                # Cancel remaining tasks
                for task in tasks:
                    if not task.done():
                        task.cancel()
                raise

    async def _download_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        setup: SetupRecord,
        output_path: Path,
        progress: Progress,
        task_id: TaskID,
        result: DownloadResult,
    ) -> None:
        """Download a single setup with semaphore control.

        Args:
            semaphore: Semaphore for limiting concurrent downloads
            setup: Setup to download
            output_path: Base output directory
            progress: Rich progress bar instance
            task_id: Progress task ID to update
            result: DownloadResult to update
        """
        async with semaphore:
            if self._cancelled:
                return

            # Add random delay before download
            delay = random.uniform(self._min_delay, self._max_delay)
            await asyncio.sleep(delay)

            # Download the setup (passes result for duplicate stats tracking)
            success = await self.download_one(setup, output_path, result)

            # Update result
            if success:
                result.downloaded += 1
            else:
                result.failed += 1

            # Update progress bar
            progress.update(task_id, advance=1)

    async def download_one(
        self, setup: SetupRecord, output_path: Path, result: DownloadResult
    ) -> bool:
        """Download a single setup with retry logic.

        Attempts to download the setup ZIP and extract it with exponential
        backoff retry logic. On success, marks the setup as downloaded in state.

        Args:
            setup: Setup to download
            output_path: Base output directory (iRacing setups folder)
            result: DownloadResult to update with duplicate statistics

        Returns:
            True if download was successful, False otherwise
        """
        retry_count = 0
        last_error = ""

        while retry_count <= self._max_retries:
            try:
                # Download and extract the setup ZIP
                logger.debug(
                    f"Downloading setup {setup.id} (attempt {retry_count + 1})"
                )
                extract_result = await self._provider.download_setup(setup, output_path)

                # Verify files were extracted (or at least duplicates were found)
                if not extract_result.extracted_files and not extract_result.duplicates:
                    msg = "No .sto files extracted from ZIP"
                    raise FileNotFoundError(msg)

                # Verify all extracted files exist
                for file_path in extract_result.extracted_files:
                    if not file_path.exists():
                        msg = f"Extracted file does not exist: {file_path}"
                        raise FileNotFoundError(msg)

                # Update duplicate statistics
                if extract_result.duplicates:
                    result.duplicates_skipped += len(extract_result.duplicates)
                    result.bytes_saved += extract_result.total_bytes_saved

                # Update files renamed statistics
                if extract_result.files_renamed > 0:
                    result.files_renamed += extract_result.files_renamed

                # Mark as downloaded in state with file paths
                # When all files are duplicates, use the existing duplicate paths
                # so that is_downloaded() can still verify the setup was processed
                files_for_state = extract_result.extracted_files
                if not files_for_state and extract_result.duplicates:
                    # Use the existing paths that the duplicates matched against
                    files_for_state = [
                        d.existing_path for d in extract_result.duplicates
                    ]

                self._state.mark_downloaded(
                    self._provider.name,
                    setup.id,
                    setup.updated_date,
                    files_for_state,
                )

                logger.info(
                    f"Successfully downloaded setup {setup.id}: "
                    f"{len(extract_result.extracted_files)} files extracted"
                    + (
                        f", {len(extract_result.duplicates)} duplicates skipped"
                        if extract_result.duplicates
                        else ""
                    )
                )
                return True

            except asyncio.CancelledError:
                logger.warning(f"Download of setup {setup.id} cancelled")
                raise

            except Exception as e:
                last_error = str(e)
                retry_count += 1

                if retry_count <= self._max_retries:
                    # Exponential backoff: 1s, 2s, 4s
                    backoff = 2 ** (retry_count - 1)
                    logger.warning(
                        f"Error downloading setup {setup.id}: {e}. "
                        f"Retrying in {backoff}s (attempt {retry_count}/{self._max_retries})"
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        f"Failed to download setup {setup.id} after "
                        f"{self._max_retries} retries: {e}"
                    )

        # All retries failed
        logger.error(f"Setup {setup.id} failed permanently: {last_error}")
        return False
