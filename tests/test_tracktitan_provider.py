"""Tests for the Track Titan provider implementation."""

import io
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iracing_setup_downloader.models import SetupRecord, TracKTitanSetupInfo
from iracing_setup_downloader.providers.tracktitan import (
    TracKTitanAPIError,
    TracKTitanAuthenticationError,
    TracKTitanDownloadError,
    TracKTitanProvider,
)


class TestTracKTitanSetupInfo:
    """Tests for TracKTitanSetupInfo model."""

    def test_create_setup_info(self, tt_setup_info_data):
        """Test creating a TracKTitanSetupInfo from valid data."""
        info = TracKTitanSetupInfo(**tt_setup_info_data)

        assert info.setup_uuid == "f28c1355-b9a6-4a6b-8fc7-02afed6fd47d"
        assert info.car_id == "mx-5_cup"
        assert info.track_id == "bathurst"
        assert info.car_name == "Global Mazda MX-5 Cup"
        assert info.track_name == "Mount Panorama Circuit"
        assert info.car_shorthand == "mx5 mx52016"
        assert info.series_name == "Production Car Challenge"
        assert info.driver_name == "William Chadwick"
        assert info.season == "1"
        assert info.week == "8"
        assert info.year == 2026
        assert info.has_wet_setup is True
        assert info.is_bundle is False

    def test_unique_id_property(self, tt_setup_info_data):
        """Test the unique_id property returns the setup UUID."""
        info = TracKTitanSetupInfo(**tt_setup_info_data)

        assert info.unique_id == "f28c1355-b9a6-4a6b-8fc7-02afed6fd47d"

    def test_unique_id_different_values(self):
        """Test unique_id varies with different UUIDs."""
        info1 = TracKTitanSetupInfo(
            setup_uuid="uuid-1",
            car_id="car",
            track_id="track",
            car_name="Car",
            track_name="Track",
        )
        info2 = TracKTitanSetupInfo(
            setup_uuid="uuid-2",
            car_id="car",
            track_id="track",
            car_name="Car",
            track_name="Track",
        )

        assert info1.unique_id != info2.unique_id

    def test_optional_fields_default(self):
        """Test that optional fields have correct defaults."""
        info = TracKTitanSetupInfo(
            setup_uuid="test",
            car_id="car",
            track_id="track",
            car_name="Car",
            track_name="Track",
        )

        assert info.car_shorthand == ""
        assert info.series_name == ""
        assert info.driver_name == ""
        assert info.season == ""
        assert info.week == ""
        assert info.has_wet_setup is False
        assert info.is_bundle is False


class TestTracKTitanProvider:
    """Tests for TracKTitanProvider class."""

    def test_provider_name(self, tt_credentials):
        """Test provider returns correct name."""
        provider = TracKTitanProvider(**tt_credentials)
        assert provider.name == "tracktitan"

    def test_get_auth_headers(self, tt_credentials):
        """Test auth headers include all required Track Titan headers."""
        provider = TracKTitanProvider(**tt_credentials)
        headers = provider.get_auth_headers()

        assert headers["authorization"] == tt_credentials["access_token"]
        assert headers["x-consumer-id"] == "trackTitan"
        assert headers["x-user-device"] == "desktop"
        assert headers["x-user-id"] == tt_credentials["user_id"]

    def test_slug_to_name(self, tt_credentials):
        """Test slug to name conversion."""
        provider = TracKTitanProvider(**tt_credentials)

        assert provider._slug_to_name("mx-5_cup") == "Mx 5 Cup"
        assert provider._slug_to_name("bathurst") == "Bathurst"
        assert provider._slug_to_name("dallara-ir18") == "Dallara Ir18"

    def test_extract_series_category(self, tt_credentials):
        """Test series name to category abbreviation."""
        provider = TracKTitanProvider(**tt_credentials)

        assert provider._extract_series_category("Production Car Challenge") == "PCC"
        assert provider._extract_series_category("INDYCAR Series") == "INDYCAR"
        assert (
            provider._extract_series_category("Falken Tyre Sports Car Challenge")
            == "FTSC"
        )
        assert provider._extract_series_category("IMSA Racing") == "IMSA"
        assert provider._extract_series_category("") == ""
        # Unknown series returns full name
        assert provider._extract_series_category("Unknown Series") == "Unknown Series"

    def test_extract_car_folder_standard(self, tt_credentials):
        """Test extracting car folder from standard filename."""
        provider = TracKTitanProvider(**tt_credentials)

        result = provider._extract_car_folder("mx5 @ bathurst CR.sto")
        assert result == "mx5"

    def test_extract_car_folder_multi_token(self, tt_credentials):
        """Test extracting car folder uses first token from multi-token shorthand."""
        provider = TracKTitanProvider(**tt_credentials)

        result = provider._extract_car_folder("mx5 mx52016 @ bathurst CR.sto")
        assert result == "mx5"

    def test_extract_car_folder_no_at_symbol(self, tt_credentials):
        """Test extracting car folder returns None without @ symbol."""
        provider = TracKTitanProvider(**tt_credentials)

        result = provider._extract_car_folder("invalid_filename.sto")
        assert result is None

    def test_extract_car_folder_blocks_path_traversal(self, tt_credentials):
        """Test that path traversal is blocked."""
        provider = TracKTitanProvider(**tt_credentials)

        assert provider._extract_car_folder(".. @ track race.sto") is None
        assert provider._extract_car_folder(". @ track race.sto") is None

    def test_build_filename_standard(self, tt_credentials, tt_setup_record_data):
        """Test building standardized filename."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        filename, had_spaces = provider._build_filename(setup, "mx5 @ bathurst CR.sto")

        assert filename.startswith("TT_")
        assert filename.endswith(".sto")
        assert "CR" in filename

    def test_build_filename_no_double_underscores(
        self, tt_credentials, tt_setup_record_data
    ):
        """Test that no double underscores appear in filename."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        filename, _ = provider._build_filename(setup, "test.sto")

        assert "__" not in filename


class TestTracKTitanProviderParseResponse:
    """Tests for setup response parsing."""

    def test_parse_setups_success(self, tt_credentials, tt_setups_response):
        """Test parsing a valid setups response."""
        provider = TracKTitanProvider(**tt_credentials)
        setups, has_more = provider._parse_setups_response(tt_setups_response)

        assert len(setups) == 2

    def test_parse_setups_creates_correct_download_urls(
        self, tt_credentials, tt_setups_response
    ):
        """Test that download URLs are correctly constructed."""
        provider = TracKTitanProvider(**tt_credentials)
        setups, _ = provider._parse_setups_response(tt_setups_response)

        for setup in setups:
            assert setup.download_url.startswith("https://services.tracktitan.io")
            assert "/download" in setup.download_url

    def test_parse_setups_extracts_car_and_track(
        self, tt_credentials, tt_setups_response
    ):
        """Test that car and track names are extracted correctly."""
        provider = TracKTitanProvider(**tt_credentials)
        setups, _ = provider._parse_setups_response(tt_setups_response)

        # Find the MX-5 setup
        mx5_setup = next(s for s in setups if "Mazda" in s.download_name)
        assert mx5_setup.car == "Global Mazda MX-5 Cup"
        assert mx5_setup.track == "Mount Panorama Circuit"

    def test_parse_setups_extracts_season(self, tt_credentials, tt_setups_response):
        """Test that season version is extracted correctly."""
        provider = TracKTitanProvider(**tt_credentials)
        setups, _ = provider._parse_setups_response(tt_setups_response)

        for setup in setups:
            assert "26S1" in setup.ver
            assert "W8" in setup.ver

    def test_parse_setups_invalid_response_type(self, tt_credentials):
        """Test parsing fails with non-dict response."""
        provider = TracKTitanProvider(**tt_credentials)

        with pytest.raises(TracKTitanAPIError, match="Unexpected response type"):
            provider._parse_setups_response([])

    def test_parse_setups_api_error(self, tt_credentials):
        """Test parsing fails when success is false."""
        provider = TracKTitanProvider(**tt_credentials)

        with pytest.raises(TracKTitanAPIError, match="error"):
            provider._parse_setups_response(
                {"success": False, "status": 500, "data": {}}
            )

    def test_parse_setups_empty_data(self, tt_credentials):
        """Test parsing empty setups returns empty list."""
        provider = TracKTitanProvider(**tt_credentials)

        setups, has_more = provider._parse_setups_response(
            {"success": True, "status": 200, "data": {"setups": []}}
        )
        assert setups == []
        assert has_more is False

    def test_parse_setups_has_more_detection(self, tt_credentials):
        """Test that has_more is False when fewer than page limit items."""
        provider = TracKTitanProvider(**tt_credentials)
        setups, has_more = provider._parse_setups_response(
            {
                "success": True,
                "status": 200,
                "data": {
                    "setups": [
                        {
                            "id": f"uuid-{i}",
                            "title": f"Setup {i}",
                            "config": [
                                {"gameId": "iRacing", "carId": "car", "trackId": "trk"}
                            ],
                            "setupCombos": [
                                {
                                    "car": {"name": "Car"},
                                    "track": {"name": "Track"},
                                }
                            ],
                            "period": {"season": "1", "week": "1", "year": 2026},
                            "hymoSeries": {"seriesName": "PCC"},
                            "hymoDriver": {"driverName": "Test"},
                            "lastUpdatedAt": 1770000000000,
                            "isActive": True,
                        }
                        for i in range(provider.DEFAULT_PAGE_LIMIT)
                    ]
                },
            }
        )
        assert has_more is True

    def test_parse_setups_includes_inactive(self, tt_credentials):
        """Test that inactive setups are included."""
        provider = TracKTitanProvider(**tt_credentials)
        setups, _ = provider._parse_setups_response(
            {
                "success": True,
                "status": 200,
                "data": {
                    "setups": [
                        {
                            "id": "uuid-1",
                            "title": "Active Setup",
                            "config": [
                                {"gameId": "iRacing", "carId": "car", "trackId": "trk"}
                            ],
                            "setupCombos": [
                                {"car": {"name": "Car"}, "track": {"name": "Track"}}
                            ],
                            "period": {"season": "1", "week": "1", "year": 2026},
                            "hymoSeries": {"seriesName": "PCC"},
                            "hymoDriver": {"driverName": "Test"},
                            "lastUpdatedAt": 1770000000000,
                            "isActive": True,
                        },
                        {
                            "id": "uuid-2",
                            "title": "Inactive Setup",
                            "config": [
                                {
                                    "gameId": "iRacing",
                                    "carId": "car2",
                                    "trackId": "trk2",
                                }
                            ],
                            "setupCombos": [
                                {"car": {"name": "Car2"}, "track": {"name": "Track2"}}
                            ],
                            "period": {"season": "1", "week": "1", "year": 2026},
                            "hymoSeries": {"seriesName": "PCC"},
                            "hymoDriver": {"driverName": "Test"},
                            "lastUpdatedAt": 1770000000000,
                            "isActive": False,
                        },
                    ]
                },
            }
        )
        assert len(setups) == 2


class TestTracKTitanProviderFetchSetups:
    """Tests for fetch_setups method."""

    @pytest.mark.asyncio
    async def test_fetch_setups_success(self, tt_credentials, tt_setups_response):
        """Test successful setup fetching."""
        provider = TracKTitanProvider(**tt_credentials)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=tt_setups_response)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            setups = await provider.fetch_setups()

            assert len(setups) == 2
            mock_session.get.assert_called_once()

        await provider.close()

    @pytest.mark.asyncio
    async def test_fetch_setups_auth_error_401(self, tt_credentials):
        """Test authentication error on 401 status."""
        provider = TracKTitanProvider(**tt_credentials)

        mock_response = MagicMock()
        mock_response.status = 401

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(
                TracKTitanAuthenticationError, match="Invalid or expired"
            ):
                await provider.fetch_setups()

        await provider.close()

    @pytest.mark.asyncio
    async def test_fetch_setups_auth_error_403(self, tt_credentials):
        """Test authentication error on 403 status."""
        provider = TracKTitanProvider(**tt_credentials)

        mock_response = MagicMock()
        mock_response.status = 403

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(TracKTitanAuthenticationError, match="forbidden"):
                await provider.fetch_setups()

        await provider.close()

    @pytest.mark.asyncio
    async def test_fetch_setups_api_error(self, tt_credentials):
        """Test API error on non-2xx status."""
        provider = TracKTitanProvider(**tt_credentials)

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(TracKTitanAPIError, match="500"):
                await provider.fetch_setups()

        await provider.close()


class TestTracKTitanProviderDownloadSetup:
    """Tests for download_setup method."""

    def _create_test_zip(self, filenames: list[str]) -> bytes:
        """Create a ZIP file in memory with given filenames."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in filenames:
                zf.writestr(filename, b"test setup content")
        return buffer.getvalue()

    def _mock_two_step_download(self, mock_session, post_response, get_response):
        """Configure mock session for two-step download (POST then GET)."""
        mock_session.post.return_value.__aenter__.return_value = post_response
        mock_session.get.return_value.__aenter__.return_value = get_response

    @pytest.mark.asyncio
    async def test_download_setup_success(
        self, tt_credentials, tt_setup_record_data, temp_dir
    ):
        """Test successful setup download and extraction."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        zip_content = self._create_test_zip(["mx5/mx5 @ bathurst CR.sto"])

        # Step 1: POST returns signed URL
        mock_post_response = MagicMock()
        mock_post_response.status = 200
        mock_post_response.json = AsyncMock(
            return_value={"url": "https://cloudfront.example.com/setup.zip"}
        )

        # Step 2: GET downloads the ZIP
        mock_get_response = MagicMock()
        mock_get_response.status = 200
        mock_get_response.read = AsyncMock(return_value=zip_content)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            self._mock_two_step_download(
                mock_session, mock_post_response, mock_get_response
            )
            mock_get_session.return_value = mock_session

            result = await provider.download_setup(setup, temp_dir)

            assert len(result.extracted_files) == 1
            assert result.extracted_files[0].suffix == ".sto"
            mock_session.post.assert_called_once()
            mock_session.get.assert_called_once()

        await provider.close()

    @pytest.mark.asyncio
    async def test_download_setup_auth_error(
        self, tt_credentials, tt_setup_record_data, temp_dir
    ):
        """Test authentication error during download POST."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        mock_post_response = MagicMock()
        mock_post_response.status = 401

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.post.return_value.__aenter__.return_value = mock_post_response
            mock_get_session.return_value = mock_session

            with pytest.raises(TracKTitanAuthenticationError):
                await provider.download_setup(setup, temp_dir)

        await provider.close()

    @pytest.mark.asyncio
    async def test_download_setup_not_found(
        self, tt_credentials, tt_setup_record_data, temp_dir
    ):
        """Test 404 error during download POST."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        mock_post_response = MagicMock()
        mock_post_response.status = 404

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.post.return_value.__aenter__.return_value = mock_post_response
            mock_get_session.return_value = mock_session

            with pytest.raises(TracKTitanDownloadError, match="not found"):
                await provider.download_setup(setup, temp_dir)

        await provider.close()

    @pytest.mark.asyncio
    async def test_download_setup_no_sto_files(
        self, tt_credentials, tt_setup_record_data, temp_dir
    ):
        """Test error when ZIP contains no .sto files."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        zip_content = self._create_test_zip(["readme.txt", "info.json"])

        mock_post_response = MagicMock()
        mock_post_response.status = 200
        mock_post_response.json = AsyncMock(
            return_value={"url": "https://cloudfront.example.com/setup.zip"}
        )

        mock_get_response = MagicMock()
        mock_get_response.status = 200
        mock_get_response.read = AsyncMock(return_value=zip_content)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            self._mock_two_step_download(
                mock_session, mock_post_response, mock_get_response
            )
            mock_get_session.return_value = mock_session

            with pytest.raises(TracKTitanDownloadError, match="No .sto files"):
                await provider.download_setup(setup, temp_dir)

        await provider.close()

    @pytest.mark.asyncio
    async def test_download_setup_bad_zip(
        self, tt_credentials, tt_setup_record_data, temp_dir
    ):
        """Test error when ZIP file is corrupted."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        mock_post_response = MagicMock()
        mock_post_response.status = 200
        mock_post_response.json = AsyncMock(
            return_value={"url": "https://cloudfront.example.com/setup.zip"}
        )

        mock_get_response = MagicMock()
        mock_get_response.status = 200
        mock_get_response.read = AsyncMock(return_value=b"not a valid zip file")

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            self._mock_two_step_download(
                mock_session, mock_post_response, mock_get_response
            )
            mock_get_session.return_value = mock_session

            with pytest.raises(TracKTitanDownloadError, match="Invalid ZIP"):
                await provider.download_setup(setup, temp_dir)

        await provider.close()

    @pytest.mark.asyncio
    async def test_download_setup_missing_signed_url(
        self, tt_credentials, tt_setup_record_data, temp_dir
    ):
        """Test error when POST response has no download URL."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        mock_post_response = MagicMock()
        mock_post_response.status = 200
        mock_post_response.json = AsyncMock(return_value={})

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.post.return_value.__aenter__.return_value = mock_post_response
            mock_get_session.return_value = mock_session

            with pytest.raises(TracKTitanDownloadError, match="No download URL"):
                await provider.download_setup(setup, temp_dir)

        await provider.close()


class TestTracKTitanProviderExtractZip:
    """Tests for ZIP extraction."""

    def _create_test_zip(self, filenames: list[str]) -> bytes:
        """Create a ZIP file in memory with given filenames."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in filenames:
                zf.writestr(filename, b"test setup content")
        return buffer.getvalue()

    def test_extract_zip_with_car_folder(
        self, tt_credentials, tt_setup_record_data, temp_dir
    ):
        """Test that extraction preserves car folder from ZIP path."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        zip_content = self._create_test_zip(["mx5/race.sto"])

        extracted, duplicates, renamed = provider._extract_zip(
            zip_content, temp_dir, setup
        )

        assert len(extracted) == 1
        assert "mx5" in str(extracted[0])

    def test_extract_zip_skips_non_sto(
        self, tt_credentials, tt_setup_record_data, temp_dir
    ):
        """Test that non-.sto files are skipped."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        zip_content = self._create_test_zip(
            [
                "mx5/race.sto",
                "mx5/readme.txt",
                "mx5/info.json",
            ]
        )

        extracted, duplicates, renamed = provider._extract_zip(
            zip_content, temp_dir, setup
        )

        assert len(extracted) == 1

    def test_extract_zip_prevents_path_traversal(
        self, tt_credentials, tt_setup_record_data, temp_dir
    ):
        """Test that path traversal attempts are blocked."""
        provider = TracKTitanProvider(**tt_credentials)
        setup = SetupRecord(**tt_setup_record_data)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("../../../etc/passwd.sto", b"malicious")
            zf.writestr("mx5/valid.sto", b"valid")
        zip_content = buffer.getvalue()

        extracted, duplicates, renamed = provider._extract_zip(
            zip_content, temp_dir, setup
        )

        # Only the valid file should be extracted
        assert len(extracted) == 1
        for extracted_file in extracted:
            assert str(temp_dir) in str(extracted_file)


class TestTracKTitanProviderClose:
    """Tests for provider cleanup."""

    @pytest.mark.asyncio
    async def test_close_cleans_up_session(self, tt_credentials):
        """Test that close() properly cleans up the HTTP session."""
        provider = TracKTitanProvider(**tt_credentials)

        # Force session creation
        session = await provider._get_session()
        assert session is not None

        # Close should clean up
        await provider.close()
        assert provider._session is None

    @pytest.mark.asyncio
    async def test_close_handles_no_session(self, tt_credentials):
        """Test that close() handles case where session was never created."""
        provider = TracKTitanProvider(**tt_credentials)

        # Should not raise even if session doesn't exist
        await provider.close()


class TestTracKTitanProviderStableIds:
    """Tests for deterministic ID generation."""

    def test_id_is_deterministic(self, tt_credentials, tt_setups_response):
        """Test that setup IDs are deterministic across multiple calls."""
        provider = TracKTitanProvider(**tt_credentials)

        # Parse response twice
        setups1, _ = provider._parse_setups_response(tt_setups_response)
        setups2, _ = provider._parse_setups_response(tt_setups_response)

        # IDs should be identical
        ids1 = sorted(s.id for s in setups1)
        ids2 = sorted(s.id for s in setups2)
        assert ids1 == ids2

    def test_timestamps_use_last_updated(self, tt_credentials, tt_setups_response):
        """Test that timestamps come from lastUpdatedAt field."""
        provider = TracKTitanProvider(**tt_credentials)
        setups, _ = provider._parse_setups_response(tt_setups_response)

        for setup in setups:
            # lastUpdatedAt is 1770000194000 in fixture
            assert setup.updated_date.year == 2026


class TestTracKTitanProviderIntegration:
    """Integration tests for TracKTitanProvider workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, tt_credentials, tt_setups_response):
        """Test complete fetch -> verify workflow."""
        provider = TracKTitanProvider(**tt_credentials)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=tt_setups_response)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            setups = await provider.fetch_setups()

        assert len(setups) > 0

        for setup in setups:
            assert setup.download_url.startswith("https://services.tracktitan.io")
            assert "/download" in setup.download_url
            assert setup.car, f"car should not be empty for {setup.download_name}"
            assert setup.track, f"track should not be empty for {setup.download_name}"
            assert isinstance(setup.id, int)
            assert setup.id > 0

        await provider.close()

    @pytest.mark.asyncio
    async def test_setups_are_stable_across_fetches(
        self, tt_credentials, tt_setups_response
    ):
        """Test that repeated fetches produce identical setup records."""
        provider = TracKTitanProvider(**tt_credentials)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=tt_setups_response)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            setups1 = await provider.fetch_setups()
            setups2 = await provider.fetch_setups()

        ids1 = {s.id for s in setups1}
        ids2 = {s.id for s in setups2}
        assert ids1 == ids2, "Setup IDs should be stable across fetches"

        await provider.close()
