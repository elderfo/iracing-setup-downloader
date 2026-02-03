"""Tests for the GoFast provider."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from iracing_setup_downloader.models import SetupRecord
from iracing_setup_downloader.providers.gofast import (
    GoFastAPIError,
    GoFastAuthenticationError,
    GoFastDownloadError,
    GoFastProvider,
)
from iracing_setup_downloader.track_matcher import TrackMatcher, TrackMatchResult


@pytest.fixture
def gofast_token():
    """Sample GoFast API token."""
    return "Bearer test-token-12345"


@pytest.fixture
def gofast_provider(gofast_token):
    """GoFast provider instance."""
    return GoFastProvider(token=gofast_token)


@pytest.fixture
def sample_api_response():
    """Sample API response data."""
    return [
        {
            "id": 1,
            "download_name": "IR - V1 - Ferrari 488 GT3 Evo - Spa-Francorchamps",
            "download_url": "https://example.com/setup1.sto",
            "creation_date": "2024-01-15T10:30:00Z",
            "updated_date": "2024-01-20T14:45:00Z",
            "ver": "26 S1 W8",
            "setup_ver": "1.0.0",
            "changelog": "Initial release",
            "cat": "GT3",
            "series": "IMSA",
        },
        {
            "id": 2,
            "download_name": "IR - V1 - Porsche 911 GT3 R - Watkins Glen",
            "download_url": "https://example.com/setup2.sto",
            "creation_date": "2024-01-16T11:30:00Z",
            "updated_date": "2024-01-21T15:45:00Z",
            "ver": "26 S1 W9",
            "setup_ver": "1.1.0",
            "changelog": "Updated aero",
            "cat": "GT3",
            "series": "IMSA",
        },
    ]


@pytest.fixture
def sample_setup_record(sample_setup_record_data):
    """Sample SetupRecord instance."""
    return SetupRecord(**sample_setup_record_data)


class TestGoFastProvider:
    """Tests for GoFastProvider class."""

    def test_init(self, gofast_token):
        """Test provider initialization."""
        provider = GoFastProvider(token=gofast_token)

        assert provider._token == gofast_token
        assert provider._session is None

    def test_name_property(self, gofast_provider):
        """Test name property returns correct value."""
        assert gofast_provider.name == "gofast"

    def test_get_auth_headers(self, gofast_provider, gofast_token):
        """Test get_auth_headers returns correct headers."""
        headers = gofast_provider.get_auth_headers()

        assert headers == {"Authorization": gofast_token}
        assert "Bearer" in headers["Authorization"]

    async def test_get_session_creates_new_session(self, gofast_provider):
        """Test _get_session creates new session when none exists."""
        session = await gofast_provider._get_session()

        assert session is not None
        assert isinstance(session, aiohttp.ClientSession)
        assert not session.closed

        await session.close()

    async def test_get_session_reuses_existing_session(self, gofast_provider):
        """Test _get_session reuses existing session."""
        session1 = await gofast_provider._get_session()
        session2 = await gofast_provider._get_session()

        assert session1 is session2

        await session1.close()

    async def test_get_session_recreates_closed_session(self, gofast_provider):
        """Test _get_session recreates session if closed."""
        session1 = await gofast_provider._get_session()
        await session1.close()

        session2 = await gofast_provider._get_session()

        assert session1 is not session2
        assert not session2.closed

        await session2.close()

    async def test_fetch_setups_success(self, gofast_provider, sample_api_response):
        """Test successful fetch of setups."""
        mock_response = MagicMock()
        mock_response.status = 200
        # Wrap in API response structure
        api_response = {
            "status": True,
            "msg": "Success",
            "data": {"records": sample_api_response},
        }
        mock_response.json = AsyncMock(return_value=api_response)

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            setups = await gofast_provider.fetch_setups()

            assert len(setups) == 2
            assert all(isinstance(s, SetupRecord) for s in setups)
            assert setups[0].id == 1
            assert setups[0].car == "Ferrari 488 GT3 Evo"
            assert setups[1].id == 2
            assert setups[1].car == "Porsche 911 GT3 R"

    async def test_fetch_setups_authentication_error(self, gofast_provider):
        """Test fetch_setups with authentication error."""
        mock_response = MagicMock()
        mock_response.status = 401

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastAuthenticationError):
                await gofast_provider.fetch_setups()

    async def test_fetch_setups_forbidden_error(self, gofast_provider):
        """Test fetch_setups with forbidden error."""
        mock_response = MagicMock()
        mock_response.status = 403

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastAuthenticationError):
                await gofast_provider.fetch_setups()

    async def test_fetch_setups_api_error(self, gofast_provider):
        """Test fetch_setups with API error."""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal server error")

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastAPIError):
                await gofast_provider.fetch_setups()

    async def test_fetch_setups_invalid_json(self, gofast_provider):
        """Test fetch_setups with invalid JSON response."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            side_effect=aiohttp.ContentTypeError(MagicMock(), MagicMock())
        )

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastAPIError):
                await gofast_provider.fetch_setups()

    async def test_fetch_setups_non_list_response(self, gofast_provider):
        """Test fetch_setups with API error response."""
        mock_response = MagicMock()
        mock_response.status = 200
        # API returns error status
        mock_response.json = AsyncMock(
            return_value={"status": False, "msg": "Invalid response"}
        )

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastAPIError):
                await gofast_provider.fetch_setups()

    async def test_fetch_setups_skips_invalid_records(self, gofast_provider):
        """Test fetch_setups skips invalid setup records."""
        invalid_response = [
            {
                "id": 1,
                "download_name": "IR - V1 - Ferrari 488 GT3 Evo - Spa",
                "download_url": "https://example.com/setup.sto",
                "creation_date": "2024-01-15T10:30:00Z",
                "updated_date": "2024-01-20T14:45:00Z",
                "ver": "26 S1 W8",
                "setup_ver": "1.0.0",
                "changelog": "Test",
                "cat": "GT3",
                "series": "IMSA",
            },
            {
                "id": 2,
                # Missing required fields
            },
        ]

        mock_response = MagicMock()
        mock_response.status = 200
        # Wrap in API response structure
        api_response = {
            "status": True,
            "msg": "Success",
            "data": {"records": invalid_response},
        }
        mock_response.json = AsyncMock(return_value=api_response)

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            setups = await gofast_provider.fetch_setups()

            # Should only have 1 valid setup
            assert len(setups) == 1
            assert setups[0].id == 1

    async def test_fetch_setups_network_error(self, gofast_provider):
        """Test fetch_setups with network error."""
        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.side_effect = aiohttp.ClientError("Network error")
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastAPIError):
                await gofast_provider.fetch_setups()

    async def test_fetch_setups_filters_non_iracing(self, gofast_provider):
        """Test fetch_setups filters out non-iRacing setups (AMS2, LMU, AC, etc.)."""
        mixed_response = [
            {
                "id": 1,
                "download_name": "IR - V1 - Ferrari 296 GT3 - Spa",
                "download_url": "https://example.com/setup1.zip",
                "creation_date": "2024-01-15T10:30:00",
                "updated_date": "2024-01-15T10:30:00",
                "ver": "26 S1 W8",
                "setup_ver": "1.0.0",
                "changelog": "",
                "cat": "GT3",
                "series": "IMSA",
            },
            {
                "id": 2,
                "download_name": "AMS2 - V1.6 - MERCEDES AMG GT3 EVO - NURBURGRING",
                "download_url": "https://example.com/setup2.zip",
                "creation_date": "2024-01-15T10:30:00",
                "updated_date": "2024-01-15T10:30:00",
                "ver": "1.6",
                "setup_ver": "1.0.0",
                "changelog": "",
                "cat": "GT3",
                "series": "AMS2",
            },
            {
                "id": 3,
                "download_name": "LMU - V1 - FERRARI 488 GTE EVO - PAUL RICARD",
                "download_url": "https://example.com/setup3.zip",
                "creation_date": "2024-01-15T10:30:00",
                "updated_date": "2024-01-15T10:30:00",
                "ver": "1.0",
                "setup_ver": "1.0.0",
                "changelog": "",
                "cat": "GTE",
                "series": "LMU",
            },
            {
                "id": 4,
                "download_name": "IR - V1 - Porsche 911 GT3 R - Monza",
                "download_url": "https://example.com/setup4.zip",
                "creation_date": "2024-01-15T10:30:00",
                "updated_date": "2024-01-15T10:30:00",
                "ver": "26 S1 W8",
                "setup_ver": "1.0.0",
                "changelog": "",
                "cat": "GT3",
                "series": "IMSA",
            },
        ]

        mock_response = MagicMock()
        mock_response.status = 200
        api_response = {
            "status": True,
            "msg": "Success",
            "data": {"records": mixed_response},
        }
        mock_response.json = AsyncMock(return_value=api_response)

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            setups = await gofast_provider.fetch_setups()

            # Should only return the 2 iRacing setups (IDs 1 and 4)
            assert len(setups) == 2
            assert setups[0].id == 1
            assert setups[1].id == 4
            # Verify they're iRacing setups
            assert all(s.download_name.startswith("IR - ") for s in setups)

    async def test_download_setup_success(
        self, gofast_provider, sample_setup_record, temp_dir
    ):
        """Test successful setup download and extraction."""
        import io
        import zipfile

        # Create a valid ZIP file with a .sto file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add a .sto file with proper path structure
            zf.writestr(
                "Ferrari 488 GT3 Evo/Spa-Francorchamps/setup.sto", b"setup file content"
            )

        setup_content = zip_buffer.getvalue()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=setup_content)

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            result = await gofast_provider.download_setup(sample_setup_record, temp_dir)

            # Should return an ExtractResult with extracted files
            assert len(result.extracted_files) == 1

            result_path = result.extracted_files[0]
            assert result_path.exists()
            assert result_path.is_file()
            assert result_path.suffix == ".sto"
            assert result_path.read_bytes() == b"setup file content"

    async def test_download_setup_authentication_error(
        self, gofast_provider, sample_setup_record, temp_dir
    ):
        """Test download_setup with authentication error."""
        mock_response = MagicMock()
        mock_response.status = 401

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastAuthenticationError):
                await gofast_provider.download_setup(sample_setup_record, temp_dir)

    async def test_download_setup_forbidden(
        self, gofast_provider, sample_setup_record, temp_dir
    ):
        """Test download_setup with forbidden error."""
        mock_response = MagicMock()
        mock_response.status = 403

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastAuthenticationError):
                await gofast_provider.download_setup(sample_setup_record, temp_dir)

    async def test_download_setup_not_found(
        self, gofast_provider, sample_setup_record, temp_dir
    ):
        """Test download_setup with 404 error."""
        mock_response = MagicMock()
        mock_response.status = 404

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastDownloadError):
                await gofast_provider.download_setup(sample_setup_record, temp_dir)

    async def test_download_setup_server_error(
        self, gofast_provider, sample_setup_record, temp_dir
    ):
        """Test download_setup with server error."""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal server error")

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastDownloadError):
                await gofast_provider.download_setup(sample_setup_record, temp_dir)

    async def test_download_setup_network_error(
        self, gofast_provider, sample_setup_record, temp_dir
    ):
        """Test download_setup with network error."""
        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.side_effect = aiohttp.ClientError("Network error")
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastDownloadError):
                await gofast_provider.download_setup(sample_setup_record, temp_dir)

    async def test_download_setup_read_error(
        self, gofast_provider, sample_setup_record, temp_dir
    ):
        """Test download_setup with read error."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(side_effect=aiohttp.ClientError("Read error"))

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(GoFastDownloadError):
                await gofast_provider.download_setup(sample_setup_record, temp_dir)

    async def test_download_setup_flattens_structure(
        self, gofast_provider, sample_setup_record, temp_dir
    ):
        """Test download_setup flattens structure keeping only car folder."""
        import io
        import zipfile

        # Create a valid ZIP file with nested structure (car/track/season/file)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "Ferrari 488 GT3 Evo/Spa-Francorchamps/26s1/GO_Race.sto",
                b"setup file content",
            )

        setup_content = zip_buffer.getvalue()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=setup_content)

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            result = await gofast_provider.download_setup(sample_setup_record, temp_dir)

            # Verify one file extracted
            assert len(result.extracted_files) == 1

            # Verify car directory was created
            car_dir = temp_dir / "Ferrari 488 GT3 Evo"
            assert car_dir.exists()
            assert car_dir.is_dir()

            # Verify nested track/season directories were NOT created (flattened)
            track_dir = car_dir / "Spa-Francorchamps"
            assert not track_dir.exists()

            # Verify file is directly in car folder with standardized name
            result_path = result.extracted_files[0]
            assert result_path.parent == car_dir
            # Filename should be: GoFast_<series>_<season>_<track>_<setup_type>.sto
            # From sample_setup_record: series=IMSA, season=26S1W8, track=Spa-Francorchamps
            assert "GoFast" in result_path.name
            assert result_path.suffix == ".sto"

    async def test_close_closes_session(self, gofast_provider):
        """Test close method closes the session."""
        session = await gofast_provider._get_session()
        assert not session.closed

        await gofast_provider.close()

        assert session.closed

    async def test_close_with_no_session(self, gofast_provider):
        """Test close method with no session."""
        # Should not raise an error
        await gofast_provider.close()

    async def test_close_with_already_closed_session(self, gofast_provider):
        """Test close method with already closed session."""
        session = await gofast_provider._get_session()
        await session.close()

        # Should not raise an error
        await gofast_provider.close()


class TestGoFastProviderIntegration:
    """Integration tests for GoFastProvider."""

    async def test_full_workflow(self, gofast_provider, sample_api_response, temp_dir):
        """Test full workflow: fetch and download."""
        import io
        import zipfile

        # Create a valid ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "Ferrari 488 GT3 Evo/Spa-Francorchamps/setup.sto", b"setup file content"
            )

        setup_content = zip_buffer.getvalue()

        # Mock all HTTP calls
        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()

            # Mock fetch_setups call
            fetch_response = MagicMock()
            fetch_response.status = 200
            api_response = {
                "status": True,
                "msg": "Success",
                "data": {"records": sample_api_response},
            }
            fetch_response.json = AsyncMock(return_value=api_response)

            # Mock download call
            download_response = MagicMock()
            download_response.status = 200
            download_response.read = AsyncMock(return_value=setup_content)

            # Set up mock session to return appropriate responses
            call_count = [0]

            def mock_get(*_args, **_kwargs):
                call_count[0] += 1
                if call_count[0] == 1:  # First call is for fetch
                    return MagicMock(__aenter__=AsyncMock(return_value=fetch_response))
                # Subsequent calls are for download
                return MagicMock(__aenter__=AsyncMock(return_value=download_response))

            mock_session.get.side_effect = mock_get
            mock_get_session.return_value = mock_session

            # 1. Fetch setups
            setups = await gofast_provider.fetch_setups()
            assert len(setups) == 2

            # 2. Download first setup
            result = await gofast_provider.download_setup(setups[0], temp_dir)
            assert len(result.extracted_files) == 1
            assert result.extracted_files[0].exists()
            assert result.extracted_files[0].read_bytes() == b"setup file content"

            # 3. Close
            await gofast_provider.close()


class TestBuildFilename:
    """Tests for the _build_filename method."""

    @pytest.fixture
    def provider(self):
        """Create a provider instance for testing."""
        return GoFastProvider(token="Bearer test-token")

    def test_build_filename_all_fields(self, provider, sample_setup_record):
        """Test filename with all fields present."""
        filename, was_renamed = provider._build_filename(
            sample_setup_record, "GO_Race.sto"
        )

        assert filename == "GoFast_IMSA_26S1W8_Spa-Francorchamps_Race.sto"
        assert not filename.startswith("_")
        assert not filename.endswith("_.sto")
        assert "__" not in filename
        assert not was_renamed  # No spaces in track name "Spa-Francorchamps"

    def test_build_filename_missing_series(self, provider):
        """Test filename with missing series."""
        setup = SetupRecord(
            id=123,
            download_name="IR - V1 - Ferrari 296 GT3 - Monza",
            download_url="https://example.com/setup.zip",
            creation_date="2024-01-15T10:30:00",
            updated_date="2024-01-15T10:30:00",
            ver="26 S1 W8",
            setup_ver="1.0.0",
            changelog="",
            cat="GT3",
            series="",  # Missing series
        )
        filename, was_renamed = provider._build_filename(setup, "setup_Qualifying.sto")

        assert filename == "GoFast_26S1W8_Monza_Qualifying.sto"
        assert "__" not in filename
        assert not was_renamed  # No spaces in track name "Monza"

    def test_build_filename_missing_track(self, provider):
        """Test filename with missing track (unparseable download_name)."""
        setup = SetupRecord(
            id=123,
            download_name="Unknown Format",
            download_url="https://example.com/setup.zip",
            creation_date="2024-01-15T10:30:00",
            updated_date="2024-01-15T10:30:00",
            ver="26 S1 W8",
            setup_ver="1.0.0",
            changelog="",
            cat="GT3",
            series="IMSA",
        )
        filename, was_renamed = provider._build_filename(setup, "setup_eR.sto")

        assert "GoFast" in filename
        assert "IMSA" in filename
        assert "__" not in filename
        assert not filename.startswith("_")
        # Track name extracted from "Unknown Format" could have space
        # but the format is unparseable so track is empty

    def test_build_filename_extracts_setup_type(self, provider, sample_setup_record):
        """Test setup type extraction from original filename."""
        # Test various setup type formats
        test_cases = [
            ("GO 26S1 NextGen Daytona500 Qualifying.sto", "Qualifying"),
            ("setup_eR.sto", "eR"),
            ("GO_Race.sto", "Race"),
            ("setup_sQ.sto", "sQ"),
            ("GO 26S1 GT3 Spa sWet.sto", "sWet"),
        ]

        for original_name, expected_type in test_cases:
            filename, _was_renamed = provider._build_filename(
                sample_setup_record, original_name
            )
            assert filename.endswith(f"_{expected_type}.sto"), (
                f"Expected {expected_type} in {filename} from {original_name}"
            )

    def test_build_filename_no_double_underscores(self, provider):
        """Test that double underscores are never present."""
        setup = SetupRecord(
            id=123,
            download_name="Unknown",  # Will result in empty track
            download_url="https://example.com/setup.zip",
            creation_date="2024-01-15T10:30:00",
            updated_date="2024-01-15T10:30:00",
            ver="",  # Empty season
            setup_ver="1.0.0",
            changelog="",
            cat="",
            series="",  # Empty series
        )
        filename, _was_renamed = provider._build_filename(setup, "setup.sto")

        assert "__" not in filename
        assert not filename.startswith("_")
        assert not filename.endswith("_.sto")

    def test_build_filename_fallback(self, provider):
        """Test fallback to setup.sto if all fields are empty."""
        setup = SetupRecord(
            id=123,
            download_name="x",  # Minimal valid value
            download_url="https://example.com/setup.zip",
            creation_date="2024-01-15T10:30:00",
            updated_date="2024-01-15T10:30:00",
            ver="",
            setup_ver="1.0.0",
            changelog="",
            cat="",
            series="",
        )
        filename, was_renamed = provider._build_filename(setup, ".sto")  # No stem

        # Should at least have GoFast as creator
        assert "GoFast" in filename
        assert filename.endswith(".sto")
        assert not was_renamed  # No spaces to sanitize

    def test_build_filename_sanitizes_spaces(self, provider):
        """Test that spaces in track names are replaced with underscores."""
        setup = SetupRecord(
            id=123,
            download_name="IR - V1 - Ferrari 296 GT3 - Spa Francorchamps",  # Space in track
            download_url="https://example.com/setup.zip",
            creation_date="2024-01-15T10:30:00",
            updated_date="2024-01-15T10:30:00",
            ver="26 S1 W8",
            setup_ver="1.0.0",
            changelog="",
            cat="GT3",
            series="IMSA",
        )
        filename, was_renamed = provider._build_filename(setup, "setup_Race.sto")

        assert " " not in filename
        assert "Spa_Francorchamps" in filename
        assert was_renamed  # Space was sanitized

    def test_build_filename_sanitizes_series_spaces(self, provider):
        """Test that spaces in series names are replaced with underscores."""
        setup = SetupRecord(
            id=123,
            download_name="IR - V1 - Ferrari 296 GT3 - Monza",
            download_url="https://example.com/setup.zip",
            creation_date="2024-01-15T10:30:00",
            updated_date="2024-01-15T10:30:00",
            ver="26 S1 W8",
            setup_ver="1.0.0",
            changelog="",
            cat="GT3",
            series="Super GT Series",  # Space in series
        )
        filename, was_renamed = provider._build_filename(setup, "setup_Race.sto")

        assert " " not in filename
        assert "Super_GT_Series" in filename
        assert was_renamed  # Space was sanitized


class TestGoFastProviderTrackOrganization:
    """Tests for track-based folder organization."""

    @pytest.fixture
    def sample_tracks_data(self):
        """Sample tracks data for testing."""
        return {
            "type": "tracks",
            "data": [
                {
                    "track_id": 1,
                    "track_name": "Spa-Francorchamps - Grand Prix Pits",
                    "track_dirpath": "spa\\gp",
                    "config_name": "Grand Prix Pits",
                    "category": "road",
                    "retired": False,
                    "is_oval": False,
                    "is_dirt": False,
                },
                {
                    "track_id": 2,
                    "track_name": "Daytona International Speedway - Oval",
                    "track_dirpath": "daytonaint\\oval",
                    "config_name": "Oval",
                    "category": "oval",
                    "retired": False,
                    "is_oval": True,
                    "is_dirt": False,
                },
                {
                    "track_id": 3,
                    "track_name": "Daytona International Speedway - Road Course",
                    "track_dirpath": "daytonaint\\road",
                    "config_name": "Road Course",
                    "category": "road",
                    "retired": False,
                    "is_oval": False,
                    "is_dirt": False,
                },
            ],
        }

    @pytest.fixture
    def track_matcher(self, sample_tracks_data, tmp_path):
        """Create a TrackMatcher with sample data."""
        tracks_file = tmp_path / "tracks.json"
        with open(tracks_file, "w") as f:
            json.dump(sample_tracks_data, f)

        matcher = TrackMatcher(tracks_data_path=tracks_file)
        matcher.load()
        return matcher

    @pytest.fixture
    def provider_with_matcher(self, gofast_token, track_matcher):
        """Create a provider with track matcher."""
        return GoFastProvider(token=gofast_token, track_matcher=track_matcher)

    def test_provider_accepts_track_matcher(self, gofast_token, track_matcher):
        """Test provider accepts track_matcher parameter."""
        provider = GoFastProvider(token=gofast_token, track_matcher=track_matcher)

        assert provider._track_matcher is track_matcher

    def test_provider_accepts_none_track_matcher(self, gofast_token):
        """Test provider works without track_matcher."""
        provider = GoFastProvider(token=gofast_token)

        assert provider._track_matcher is None

    async def test_download_with_track_matcher_creates_track_subdir(
        self, provider_with_matcher, sample_setup_record, temp_dir
    ):
        """Test download creates track subdirectory when matcher matches."""
        import io
        import zipfile

        # Create a valid ZIP file with a .sto file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "Ferrari 488 GT3 Evo/Spa-Francorchamps/setup.sto", b"setup content"
            )

        setup_content = zip_buffer.getvalue()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=setup_content)

        with patch.object(
            provider_with_matcher, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            result = await provider_with_matcher.download_setup(
                sample_setup_record, temp_dir
            )

            assert len(result.extracted_files) == 1
            result_path = result.extracted_files[0]

            # Verify track subdirectory was created
            # Path should be: <temp_dir>/<car>/<track_dirpath>/<filename>
            # track_dirpath for Spa is "spa\gp" which becomes "spa/gp" on Unix
            assert result_path.exists()

            # Check that the track subdirectory is in the path
            relative_path = result_path.relative_to(temp_dir)
            path_parts = relative_path.parts

            # Should have: car_folder, track_dir, track_config, filename
            assert len(path_parts) >= 3  # At minimum: car, spa, gp, filename
            assert path_parts[0] == "Ferrari 488 GT3 Evo"  # Car folder
            # Track subdir should be spa/gp (or spa\gp on Windows)
            assert "spa" in str(relative_path).lower()
            assert "gp" in str(relative_path).lower()

    async def test_download_without_track_matcher_uses_flat_structure(
        self, gofast_provider, sample_setup_record, temp_dir
    ):
        """Test download uses flat structure when no track matcher."""
        import io
        import zipfile

        # Create a valid ZIP file with a .sto file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "Ferrari 488 GT3 Evo/Spa-Francorchamps/setup.sto", b"setup content"
            )

        setup_content = zip_buffer.getvalue()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=setup_content)

        with patch.object(
            gofast_provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            result = await gofast_provider.download_setup(sample_setup_record, temp_dir)

            assert len(result.extracted_files) == 1
            result_path = result.extracted_files[0]

            # Verify flat structure (no track subdir)
            # Path should be: <temp_dir>/<car>/<filename>
            assert result_path.exists()
            relative_path = result_path.relative_to(temp_dir)
            path_parts = relative_path.parts

            # Should have only: car_folder, filename (no track subdirs)
            assert len(path_parts) == 2
            assert path_parts[0] == "Ferrari 488 GT3 Evo"

    async def test_download_with_unmatched_track_uses_flat_structure(
        self, gofast_token, temp_dir
    ):
        """Test download falls back to flat structure when track doesn't match."""
        import io
        import zipfile

        # Create a mock track matcher that returns no match
        mock_matcher = MagicMock(spec=TrackMatcher)
        mock_matcher.match.return_value = TrackMatchResult()  # No match

        provider = GoFastProvider(token=gofast_token, track_matcher=mock_matcher)

        # Create setup with unknown track
        setup = SetupRecord(
            id=999,
            download_name="IR - V1 - Test Car - Unknown Track XYZ",
            download_url="https://example.com/setup.zip",
            creation_date="2024-01-15T10:30:00",
            updated_date="2024-01-15T10:30:00",
            ver="26 S1 W8",
            setup_ver="1.0.0",
            changelog="",
            cat="GT3",
            series="IMSA",
        )

        # Create a valid ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("Test Car/setup.sto", b"setup content")

        setup_content = zip_buffer.getvalue()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=setup_content)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            result = await provider.download_setup(setup, temp_dir)

            assert len(result.extracted_files) == 1
            result_path = result.extracted_files[0]

            # Verify flat structure
            relative_path = result_path.relative_to(temp_dir)
            path_parts = relative_path.parts
            assert len(path_parts) == 2  # car, filename only

            # Verify matcher was called with track name and category hint
            mock_matcher.match.assert_called_once_with(
                "Unknown Track XYZ", category_hint="GT3"
            )

    async def test_download_passes_category_hint_to_matcher(
        self, gofast_token, temp_dir
    ):
        """Test download passes category hint to track matcher for disambiguation."""
        import io
        import zipfile

        # Create a mock track matcher
        mock_matcher = MagicMock(spec=TrackMatcher)
        mock_matcher.match.return_value = TrackMatchResult(
            track_dirpath="daytonaint\\oval",
            confidence=0.9,
            ambiguous=False,
        )

        provider = GoFastProvider(token=gofast_token, track_matcher=mock_matcher)

        # Create setup with NASCAR category (should prefer oval)
        setup = SetupRecord(
            id=999,
            download_name="IR - V1 - NASCAR Next Gen - Daytona",
            download_url="https://example.com/setup.zip",
            creation_date="2024-01-15T10:30:00",
            updated_date="2024-01-15T10:30:00",
            ver="26 S1 W8",
            setup_ver="1.0.0",
            changelog="",
            cat="NASCAR",
            series="Cup",
        )

        # Create a valid ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("NASCAR Next Gen/setup.sto", b"setup content")

        setup_content = zip_buffer.getvalue()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=setup_content)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            await provider.download_setup(setup, temp_dir)

            # Verify matcher was called with NASCAR category hint
            mock_matcher.match.assert_called_once_with(
                "Daytona", category_hint="NASCAR"
            )
