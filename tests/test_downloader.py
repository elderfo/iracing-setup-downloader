"""Tests for the downloader module."""

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from iracing_setup_downloader.downloader import DownloadResult, SetupDownloader
from iracing_setup_downloader.models import SetupRecord
from iracing_setup_downloader.providers.base import SetupProvider
from iracing_setup_downloader.state import DownloadState


class MockProvider(SetupProvider):
    """Mock provider for testing."""

    def __init__(self, setups: list[SetupRecord] | None = None):
        """Initialize mock provider."""
        self._setups = setups or []
        self._download_delay = 0
        self._should_fail = False
        self._fail_count = 0

    @property
    def name(self) -> str:
        """Return provider name."""
        return "mock_provider"

    async def fetch_setups(self) -> list[SetupRecord]:
        """Fetch setups."""
        return self._setups

    async def download_setup(self, setup: SetupRecord, output_path: Path) -> list[Path]:
        """Download a setup."""
        if self._download_delay > 0:
            await asyncio.sleep(self._download_delay)

        if self._should_fail and self._fail_count > 0:
            self._fail_count -= 1
            msg = "Mock download failure"
            raise Exception(msg)

        # Create the file using car/track from setup
        output_dir = output_path / setup.car / setup.track
        file_path = output_dir / f"setup_{setup.id}.sto"
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path.write_text("mock setup content")
        return [file_path]

    def get_auth_headers(self) -> dict[str, str]:
        """Return auth headers."""
        return {}


@pytest.fixture
def sample_setup() -> SetupRecord:
    """Create a sample setup record."""
    return SetupRecord(
        id=123,
        download_name="IR - V1 - Test Car - Test Track",
        download_url="https://example.com/setup.sto",
        creation_date=datetime(2024, 1, 1, 12, 0, 0),
        updated_date=datetime(2024, 1, 2, 12, 0, 0),
        ver="26 S1 W8",
        setup_ver="v1.0",
        changelog="Initial setup",
        cat="GT3",
        series="IMSA",
    )


@pytest.fixture
def sample_setups() -> list[SetupRecord]:
    """Create multiple sample setup records."""
    return [
        SetupRecord(
            id=i,
            download_name=f"IR - V1 - Car {i} - Track {i}",
            download_url=f"https://example.com/setup{i}.sto",
            creation_date=datetime(2024, 1, 1, 12, 0, 0),
            updated_date=datetime(2024, 1, 2, 12, 0, 0),
            ver="26 S1 W8",
            setup_ver="v1.0",
            changelog="Initial setup",
            cat="GT3",
            series="IMSA",
        )
        for i in range(1, 6)
    ]


@pytest.fixture
def mock_state(tmp_path: Path) -> DownloadState:
    """Create a mock download state."""
    state = DownloadState(state_file=tmp_path / "state.json")
    state.load()
    return state


class TestDownloadResult:
    """Tests for DownloadResult model."""

    def test_download_result_creation(self):
        """Test creating a DownloadResult."""
        result = DownloadResult(
            total_available=10,
            skipped=3,
            downloaded=5,
            failed=2,
        )

        assert result.total_available == 10
        assert result.skipped == 3
        assert result.downloaded == 5
        assert result.failed == 2
        assert result.errors == []

    def test_download_result_with_errors(self):
        """Test DownloadResult with errors."""
        result = DownloadResult(
            total_available=5,
            skipped=0,
            downloaded=3,
            failed=2,
            errors=[("123", "Network error"), ("456", "File not found")],
        )

        assert result.failed == 2
        assert len(result.errors) == 2
        assert result.errors[0] == ("123", "Network error")

    def test_download_result_str(self):
        """Test string representation of DownloadResult."""
        result = DownloadResult(
            total_available=10,
            skipped=3,
            downloaded=5,
            failed=2,
            errors=[("123", "Network error")],
        )

        result_str = str(result)
        assert "Total available: 10" in result_str
        assert "Downloaded: 5" in result_str
        assert "Skipped: 3" in result_str
        assert "Failed: 2" in result_str
        assert "Setup 123: Network error" in result_str


class TestSetupDownloader:
    """Tests for SetupDownloader class."""

    def test_initialization(self, mock_state: DownloadState):
        """Test downloader initialization."""
        provider = MockProvider()
        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            max_concurrent=3,
            min_delay=0.1,
            max_delay=0.2,
            max_retries=2,
        )

        assert downloader._provider == provider
        assert downloader._state == mock_state
        assert downloader._max_concurrent == 3
        assert downloader._min_delay == 0.1
        assert downloader._max_delay == 0.2
        assert downloader._max_retries == 2
        assert downloader._cancelled is False

    def test_initialization_defaults(self, mock_state: DownloadState):
        """Test downloader initialization with defaults."""
        provider = MockProvider()
        downloader = SetupDownloader(provider=provider, state=mock_state)

        assert downloader._max_concurrent == 5
        assert downloader._min_delay == 0.5
        assert downloader._max_delay == 1.5
        assert downloader._max_retries == 3

    async def test_download_all_empty(self, tmp_path: Path, mock_state: DownloadState):
        """Test downloading when no setups are available."""
        provider = MockProvider(setups=[])
        downloader = SetupDownloader(provider=provider, state=mock_state)

        result = await downloader.download_all(tmp_path)

        assert result.total_available == 0
        assert result.skipped == 0
        assert result.downloaded == 0
        assert result.failed == 0

    async def test_download_all_success(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test successfully downloading multiple setups."""
        provider = MockProvider(setups=sample_setups)
        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            min_delay=0.01,
            max_delay=0.02,
        )

        result = await downloader.download_all(tmp_path)

        assert result.total_available == 5
        assert result.skipped == 0
        assert result.downloaded == 5
        assert result.failed == 0

        # Verify files were created
        for setup in sample_setups:
            file_path = tmp_path / setup.car / setup.track / f"setup_{setup.id}.sto"
            assert file_path.exists()
            assert file_path.read_text() == "mock setup content"

    async def test_download_all_skip_existing(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test skipping already-downloaded setups."""
        provider = MockProvider(setups=sample_setups)
        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            min_delay=0.01,
            max_delay=0.02,
        )

        # First download
        result1 = await downloader.download_all(tmp_path)
        assert result1.downloaded == 5
        assert result1.skipped == 0

        # Save state
        mock_state.save()

        # Second download should skip all
        result2 = await downloader.download_all(tmp_path)
        assert result2.total_available == 5
        assert result2.skipped == 5
        assert result2.downloaded == 0

    async def test_download_all_dry_run(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test dry run mode."""
        provider = MockProvider(setups=sample_setups)
        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            min_delay=0.01,
            max_delay=0.02,
        )

        result = await downloader.download_all(tmp_path, dry_run=True)

        assert result.total_available == 5
        assert result.skipped == 0
        assert result.downloaded == 0
        assert result.failed == 0

        # Verify no files were created
        for setup in sample_setups:
            file_path = tmp_path / setup.car / setup.track / f"setup_{setup.id}.sto"
            assert not file_path.exists()

    async def test_download_all_unloaded_state(self, tmp_path: Path):
        """Test that download_all raises error if state not loaded."""
        provider = MockProvider()
        state = DownloadState(state_file=tmp_path / "state.json")
        # Don't load state
        downloader = SetupDownloader(provider=provider, state=state)

        with pytest.raises(ValueError, match="State must be loaded"):
            await downloader.download_all(tmp_path)

    async def test_download_one_success(
        self, tmp_path: Path, mock_state: DownloadState, sample_setup: SetupRecord
    ):
        """Test successfully downloading a single setup."""
        provider = MockProvider()
        downloader = SetupDownloader(provider=provider, state=mock_state)

        success = await downloader.download_one(sample_setup, tmp_path)

        assert success is True

        # Verify file was created
        file_path = (
            tmp_path
            / sample_setup.car
            / sample_setup.track
            / f"setup_{sample_setup.id}.sto"
        )
        assert file_path.exists()

        # Verify state was updated
        assert mock_state.is_downloaded(
            provider.name, sample_setup.id, sample_setup.updated_date
        )

    async def test_download_one_with_retry(
        self, tmp_path: Path, mock_state: DownloadState, sample_setup: SetupRecord
    ):
        """Test downloading with retry on failure."""
        provider = MockProvider()
        provider._should_fail = True
        provider._fail_count = 2  # Fail twice, then succeed

        downloader = SetupDownloader(provider=provider, state=mock_state, max_retries=3)

        success = await downloader.download_one(sample_setup, tmp_path)

        assert success is True

    async def test_download_one_max_retries(
        self, tmp_path: Path, mock_state: DownloadState, sample_setup: SetupRecord
    ):
        """Test that download fails after max retries."""
        provider = MockProvider()
        provider._should_fail = True
        provider._fail_count = 10  # Always fail

        downloader = SetupDownloader(provider=provider, state=mock_state, max_retries=2)

        success = await downloader.download_one(sample_setup, tmp_path)

        assert success is False

    async def test_download_one_cancel(
        self, tmp_path: Path, mock_state: DownloadState, sample_setup: SetupRecord
    ):
        """Test cancelling a download."""
        provider = MockProvider()
        provider._download_delay = 1.0  # Long delay to allow cancellation

        downloader = SetupDownloader(provider=provider, state=mock_state)

        async def cancel_download():
            await asyncio.sleep(0.1)
            # Find and cancel the download task
            for task in asyncio.all_tasks():
                if task.get_coro().__name__ == "download_one":
                    task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.gather(
                downloader.download_one(sample_setup, tmp_path), cancel_download()
            )

    async def test_concurrency_control(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test that concurrent downloads are limited."""
        provider = MockProvider(setups=sample_setups)
        provider._download_delay = 0.1

        # Track concurrent downloads
        concurrent_count = 0
        max_concurrent = 0

        original_download = provider.download_setup

        async def tracked_download(setup: SetupRecord, output_path: Path) -> Path:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            try:
                return await original_download(setup, output_path)
            finally:
                concurrent_count -= 1

        provider.download_setup = tracked_download  # type: ignore

        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            max_concurrent=2,
            min_delay=0.01,
            max_delay=0.02,
        )

        await downloader.download_all(tmp_path)

        # Verify concurrency was limited
        assert max_concurrent <= 2

    async def test_filter_new_setups(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test filtering new setups."""
        provider = MockProvider(setups=sample_setups)
        downloader = SetupDownloader(provider=provider, state=mock_state)

        # Download first 2 setups
        for setup in sample_setups[:2]:
            file_path = tmp_path / setup.car / setup.track / f"setup_{setup.id}.sto"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("content")
            mock_state.mark_downloaded(
                provider.name, setup.id, setup.updated_date, [file_path]
            )

        # Filter should return only last 3
        new_setups = downloader._filter_new_setups(sample_setups, tmp_path)
        assert len(new_setups) == 3
        assert all(s.id >= 3 for s in new_setups)

    async def test_download_all_with_failures(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test download_all with some failures."""
        provider = MockProvider(setups=sample_setups)

        # Make downloads fail for setups 2 and 4
        original_download = provider.download_setup

        async def selective_fail(setup: SetupRecord, output_path: Path) -> Path:
            if setup.id in [2, 4]:
                msg = "Simulated failure"
                raise Exception(msg)
            return await original_download(setup, output_path)

        provider.download_setup = selective_fail  # type: ignore

        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            min_delay=0.01,
            max_delay=0.02,
            max_retries=1,
        )

        result = await downloader.download_all(tmp_path)

        assert result.total_available == 5
        assert result.downloaded == 3
        assert result.failed == 2

    async def test_random_delay(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test that random delays are applied."""
        provider = MockProvider(setups=sample_setups[:2])
        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            min_delay=0.05,
            max_delay=0.1,
        )

        import time

        start = time.time()
        await downloader.download_all(tmp_path)
        elapsed = time.time() - start

        # Should take at least min_delay per download
        # With 2 downloads and semaphore, at least one delay should occur
        assert elapsed >= 0.05

    async def test_state_updated_on_success(
        self, tmp_path: Path, mock_state: DownloadState, sample_setup: SetupRecord
    ):
        """Test that state is updated after successful download."""
        provider = MockProvider()
        downloader = SetupDownloader(provider=provider, state=mock_state)

        # Initially not downloaded
        assert not mock_state.is_downloaded(
            provider.name, sample_setup.id, sample_setup.updated_date
        )

        await downloader.download_one(sample_setup, tmp_path)

        # Should be marked as downloaded
        assert mock_state.is_downloaded(
            provider.name, sample_setup.id, sample_setup.updated_date
        )

    async def test_state_not_updated_on_failure(
        self, tmp_path: Path, mock_state: DownloadState, sample_setup: SetupRecord
    ):
        """Test that state is not updated after failed download."""
        provider = MockProvider()
        provider._should_fail = True
        provider._fail_count = 10

        downloader = SetupDownloader(provider=provider, state=mock_state, max_retries=1)

        await downloader.download_one(sample_setup, tmp_path)

        # Should not be marked as downloaded
        assert not mock_state.is_downloaded(
            provider.name, sample_setup.id, sample_setup.updated_date
        )

    async def test_download_all_provider_error(
        self, tmp_path: Path, mock_state: DownloadState
    ):
        """Test download_all when provider fetch fails."""
        provider = MockProvider()

        # Make fetch_setups raise an exception
        async def failing_fetch():
            msg = "API error"
            raise Exception(msg)

        provider.fetch_setups = failing_fetch  # type: ignore

        downloader = SetupDownloader(provider=provider, state=mock_state)

        with pytest.raises(Exception, match="API error"):
            await downloader.download_all(tmp_path)

    async def test_download_all_cancelled_error(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test download_all handles CancelledError correctly."""
        provider = MockProvider(setups=sample_setups)
        provider._download_delay = 1.0

        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            min_delay=0.01,
            max_delay=0.02,
        )

        async def run_and_cancel():
            import contextlib

            task = asyncio.create_task(downloader.download_all(tmp_path))
            await asyncio.sleep(0.1)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        await run_and_cancel()
        assert downloader._cancelled is True

    async def test_download_concurrent_cancel_cleanup(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test that _download_concurrent cleans up on cancellation."""
        provider = MockProvider(setups=sample_setups)
        provider._download_delay = 1.0

        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            max_concurrent=2,
            min_delay=0.01,
            max_delay=0.02,
        )

        async def run_and_cancel():
            task = asyncio.create_task(downloader.download_all(tmp_path))
            await asyncio.sleep(0.1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        await run_and_cancel()

    async def test_download_with_cancelled_flag(
        self,
        tmp_path: Path,
        mock_state: DownloadState,
        sample_setups: list[SetupRecord],
    ):
        """Test that downloads respect the cancelled flag."""
        provider = MockProvider(setups=sample_setups)

        downloader = SetupDownloader(
            provider=provider,
            state=mock_state,
            min_delay=0.01,
            max_delay=0.02,
        )

        # Set cancelled flag
        downloader._cancelled = True

        result = DownloadResult(
            total_available=len(sample_setups),
            skipped=0,
            downloaded=0,
            failed=0,
        )

        # This should not download anything
        await downloader._download_concurrent(sample_setups, tmp_path, result)

        assert result.downloaded == 0
        assert result.failed == 0
