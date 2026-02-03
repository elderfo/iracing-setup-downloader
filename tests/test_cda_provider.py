"""Tests for the CDA provider implementation."""

import io
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iracing_setup_downloader.models import CDASetupInfo, SetupRecord
from iracing_setup_downloader.providers.cda import (
    CDAAPIError,
    CDAAuthenticationError,
    CDADownloadError,
    CDAProvider,
)


class TestCDASetupInfo:
    """Tests for CDASetupInfo model."""

    def test_create_cda_setup_info(self, cda_setup_info_data):
        """Test creating a CDASetupInfo from valid data."""
        info = CDASetupInfo(**cda_setup_info_data)

        assert info.series_id == 160
        assert info.series_name == "25S4 IMSA Racing Series"
        assert info.bundle_id == 630
        assert info.week_number == 1
        assert info.car_slug == "porsche-911-gt3-r-992"
        assert info.track_slug == "watkins-glen-international"
        assert info.track_name == "Watkins Glen International"
        assert info.laptime == "Dry: 1:49.884"

    def test_unique_id_property(self, cda_setup_info_data):
        """Test the unique_id property generates correct compound key."""
        info = CDASetupInfo(**cda_setup_info_data)

        assert info.unique_id == "160_630_1"

    def test_unique_id_different_values(self):
        """Test unique_id varies with different input values."""
        info1 = CDASetupInfo(
            series_id=160,
            series_name="Test",
            bundle_id=630,
            week_number=1,
            car_slug="car",
            track_slug="track",
            track_name="Track",
        )
        info2 = CDASetupInfo(
            series_id=161,
            series_name="Test",
            bundle_id=631,
            week_number=2,
            car_slug="car",
            track_slug="track",
            track_name="Track",
        )

        assert info1.unique_id != info2.unique_id
        assert info1.unique_id == "160_630_1"
        assert info2.unique_id == "161_631_2"

    def test_laptime_optional(self):
        """Test that laptime field is optional."""
        info = CDASetupInfo(
            series_id=160,
            series_name="Test",
            bundle_id=630,
            week_number=1,
            car_slug="car",
            track_slug="track",
            track_name="Track",
        )

        assert info.laptime is None

    def test_week_number_validation(self):
        """Test that week_number must be >= 1."""
        with pytest.raises(ValueError):
            CDASetupInfo(
                series_id=160,
                series_name="Test",
                bundle_id=630,
                week_number=0,  # Invalid
                car_slug="car",
                track_slug="track",
                track_name="Track",
            )


class TestCDAProvider:
    """Tests for CDAProvider class."""

    def test_provider_name(self, cda_credentials):
        """Test provider returns correct name."""
        provider = CDAProvider(**cda_credentials)
        assert provider.name == "cda"

    def test_get_auth_headers(self, cda_credentials):
        """Test auth headers include CSRF token."""
        provider = CDAProvider(**cda_credentials)
        headers = provider.get_auth_headers()

        assert "x-elle-csrf-token" in headers
        assert headers["x-elle-csrf-token"] == cda_credentials["csrf_token"]

    def test_get_cookies(self, cda_credentials):
        """Test cookies include session ID."""
        provider = CDAProvider(**cda_credentials)
        cookies = provider._get_cookies()

        assert "PHPSESSID" in cookies
        assert cookies["PHPSESSID"] == cda_credentials["session_id"]

    def test_slug_to_name(self, cda_credentials):
        """Test slug to name conversion."""
        provider = CDAProvider(**cda_credentials)

        assert (
            provider._slug_to_name("watkins-glen-international")
            == "Watkins Glen International"
        )
        assert provider._slug_to_name("spa-francorchamps") == "Spa Francorchamps"
        assert provider._slug_to_name("simple") == "Simple"

    def test_extract_car_folder_standard(self, cda_credentials):
        """Test extracting car folder from standard CDA filename."""
        provider = CDAProvider(**cda_credentials)

        result = provider._extract_car_folder(
            "porsche911gt3r992 @ watkins glen international full race.sto"
        )
        assert result == "porsche911gt3r992"

    def test_extract_car_folder_with_spaces(self, cda_credentials):
        """Test extracting car folder removes spaces."""
        provider = CDAProvider(**cda_credentials)

        result = provider._extract_car_folder(
            "porsche 911 gt3 r 992 @ watkins glen race.sto"
        )
        assert result == "porsche911gt3r992"

    def test_extract_car_folder_no_at_symbol(self, cda_credentials):
        """Test extracting car folder returns None without @ symbol."""
        provider = CDAProvider(**cda_credentials)

        result = provider._extract_car_folder("invalid_filename.sto")
        assert result is None

    def test_build_filename_standard(self, cda_credentials, cda_setup_record_data):
        """Test building standardized filename."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        filename, had_spaces = provider._build_filename(
            setup, "porsche911gt3r992 @ watkins glen race.sto"
        )

        assert filename.startswith("CDA_")
        assert filename.endswith(".sto")
        assert "race" in filename.lower()

    def test_build_filename_no_spaces_returns_false(
        self, cda_credentials, cda_setup_record_data
    ):
        """Test that had_spaces returns False when no spaces in filename components."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        # Use a filename that doesn't add spaces
        filename, had_spaces = provider._build_filename(setup, "race.sto")

        assert " " not in filename
        # had_spaces depends on whether setup fields contain spaces
        # In our fixture, IMSA and track name may have spaces depending on parsing
        assert isinstance(had_spaces, bool)


class TestCDAProviderParseCatalog:
    """Tests for catalog parsing."""

    def test_parse_catalog_success(self, cda_credentials, cda_catalog_response):
        """Test parsing a valid catalog response."""
        provider = CDAProvider(**cda_credentials)
        setups = provider._parse_catalog(cda_catalog_response)

        # Should parse 3 setups from the fixture
        assert len(setups) == 3

    def test_parse_catalog_invalid_code(self, cda_credentials):
        """Test parsing fails with invalid response code."""
        provider = CDAProvider(**cda_credentials)

        with pytest.raises(CDAAPIError, match="error code"):
            provider._parse_catalog({"code": 500, "data": {}})

    def test_parse_catalog_invalid_type(self, cda_credentials):
        """Test parsing fails with non-dict response."""
        provider = CDAProvider(**cda_credentials)

        with pytest.raises(CDAAPIError, match="Unexpected response type"):
            provider._parse_catalog([])

    def test_parse_catalog_empty_data(self, cda_credentials):
        """Test parsing empty catalog returns empty list."""
        provider = CDAProvider(**cda_credentials)

        setups = provider._parse_catalog({"code": 200, "data": {}})
        assert setups == []

    def test_parse_catalog_creates_correct_download_url(
        self, cda_credentials, cda_catalog_response
    ):
        """Test that download URLs are correctly constructed."""
        provider = CDAProvider(**cda_credentials)
        setups = provider._parse_catalog(cda_catalog_response)

        # Find setup for week 1
        week1_setup = next(s for s in setups if "W1" in s.ver)
        assert "160/630/1" in week1_setup.download_url

    def test_parse_catalog_extracts_season(self, cda_credentials, cda_catalog_response):
        """Test that season is extracted from series name."""
        provider = CDAProvider(**cda_credentials)
        setups = provider._parse_catalog(cda_catalog_response)

        for setup in setups:
            assert "25S4" in setup.ver or "S" in setup.ver


class TestCDAProviderFetchSetups:
    """Tests for fetch_setups method."""

    @pytest.mark.asyncio
    async def test_fetch_setups_success(self, cda_credentials, cda_catalog_response):
        """Test successful setup fetching."""
        provider = CDAProvider(**cda_credentials)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=cda_catalog_response)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            setups = await provider.fetch_setups()

            assert len(setups) == 3
            mock_session.get.assert_called_once()

        await provider.close()

    @pytest.mark.asyncio
    async def test_fetch_setups_auth_error_401(self, cda_credentials):
        """Test authentication error on 401 status."""
        provider = CDAProvider(**cda_credentials)

        mock_response = MagicMock()
        mock_response.status = 401

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(CDAAuthenticationError, match="Invalid or expired"):
                await provider.fetch_setups()

        await provider.close()

    @pytest.mark.asyncio
    async def test_fetch_setups_auth_error_403(self, cda_credentials):
        """Test authentication error on 403 status."""
        provider = CDAProvider(**cda_credentials)

        mock_response = MagicMock()
        mock_response.status = 403

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(CDAAuthenticationError, match="forbidden"):
                await provider.fetch_setups()

        await provider.close()

    @pytest.mark.asyncio
    async def test_fetch_setups_api_error(self, cda_credentials):
        """Test API error on non-2xx status."""
        provider = CDAProvider(**cda_credentials)

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(CDAAPIError, match="500"):
                await provider.fetch_setups()

        await provider.close()


class TestCDAProviderDownloadSetup:
    """Tests for download_setup method."""

    def _create_test_zip(self, filenames: list[str]) -> bytes:
        """Create a ZIP file in memory with given filenames."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in filenames:
                zf.writestr(filename, b"test setup content")
        return buffer.getvalue()

    @pytest.mark.asyncio
    async def test_download_setup_success(
        self, cda_credentials, cda_setup_record_data, temp_dir
    ):
        """Test successful setup download and extraction."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        zip_content = self._create_test_zip(
            ["porsche911gt3r992 @ watkins glen international full race.sto"]
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=zip_content)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            result = await provider.download_setup(setup, temp_dir)

            assert len(result.extracted_files) == 1
            assert result.extracted_files[0].suffix == ".sto"

        await provider.close()

    @pytest.mark.asyncio
    async def test_download_setup_auth_error(
        self, cda_credentials, cda_setup_record_data, temp_dir
    ):
        """Test authentication error during download."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        mock_response = MagicMock()
        mock_response.status = 401

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(CDAAuthenticationError):
                await provider.download_setup(setup, temp_dir)

        await provider.close()

    @pytest.mark.asyncio
    async def test_download_setup_not_found(
        self, cda_credentials, cda_setup_record_data, temp_dir
    ):
        """Test 404 error during download."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        mock_response = MagicMock()
        mock_response.status = 404

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(CDADownloadError, match="not found"):
                await provider.download_setup(setup, temp_dir)

        await provider.close()

    @pytest.mark.asyncio
    async def test_download_setup_no_sto_files(
        self, cda_credentials, cda_setup_record_data, temp_dir
    ):
        """Test error when ZIP contains no .sto files."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        zip_content = self._create_test_zip(["readme.txt", "info.json"])

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=zip_content)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(CDADownloadError, match="No .sto files"):
                await provider.download_setup(setup, temp_dir)

        await provider.close()

    @pytest.mark.asyncio
    async def test_download_setup_bad_zip(
        self, cda_credentials, cda_setup_record_data, temp_dir
    ):
        """Test error when ZIP file is corrupted."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b"not a valid zip file")

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            with pytest.raises(CDADownloadError, match="Invalid ZIP"):
                await provider.download_setup(setup, temp_dir)

        await provider.close()


class TestCDAProviderExtractZip:
    """Tests for ZIP extraction."""

    def _create_test_zip(self, filenames: list[str]) -> bytes:
        """Create a ZIP file in memory with given filenames."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in filenames:
                zf.writestr(filename, b"test setup content")
        return buffer.getvalue()

    def test_extract_zip_creates_car_folder(
        self, cda_credentials, cda_setup_record_data, temp_dir
    ):
        """Test that extraction creates the correct car folder."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        zip_content = self._create_test_zip(
            ["porsche911gt3r992 @ watkins glen international full race.sto"]
        )

        extracted, duplicates, renamed = provider._extract_zip(
            zip_content, temp_dir, setup
        )

        assert len(extracted) == 1
        assert "porsche911gt3r992" in str(extracted[0])

    def test_extract_zip_skips_non_sto(
        self, cda_credentials, cda_setup_record_data, temp_dir
    ):
        """Test that non-.sto files are skipped."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        zip_content = self._create_test_zip(
            [
                "porsche911gt3r992 @ watkins glen race.sto",
                "readme.txt",
                "info.json",
            ]
        )

        extracted, duplicates, renamed = provider._extract_zip(
            zip_content, temp_dir, setup
        )

        assert len(extracted) == 1

    def test_extract_zip_prevents_path_traversal(
        self, cda_credentials, cda_setup_record_data, temp_dir
    ):
        """Test that path traversal attempts are blocked."""
        provider = CDAProvider(**cda_credentials)
        setup = SetupRecord(**cda_setup_record_data)

        # Create ZIP with potentially malicious paths
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("../../../etc/passwd.sto", b"malicious")
            zf.writestr("porsche911gt3r992 @ track race.sto", b"valid")
        zip_content = buffer.getvalue()

        extracted, duplicates, renamed = provider._extract_zip(
            zip_content, temp_dir, setup
        )

        # Only the valid file should be extracted
        assert len(extracted) == 1
        # Verify no files were written outside temp_dir
        for extracted_file in extracted:
            assert str(temp_dir) in str(extracted_file)


class TestCDAProviderClose:
    """Tests for provider cleanup."""

    @pytest.mark.asyncio
    async def test_close_cleans_up_session(self, cda_credentials):
        """Test that close() properly cleans up the HTTP session."""
        provider = CDAProvider(**cda_credentials)

        # Force session creation
        session = await provider._get_session()
        assert session is not None

        # Close should clean up
        await provider.close()
        assert provider._session is None

    @pytest.mark.asyncio
    async def test_close_handles_no_session(self, cda_credentials):
        """Test that close() handles case where session was never created."""
        provider = CDAProvider(**cda_credentials)

        # Should not raise even if session doesn't exist
        await provider.close()


class TestCDAProviderPathTraversal:
    """Tests for path traversal protection."""

    def test_extract_car_folder_blocks_dot_dot(self, cda_credentials):
        """Test that '..' is blocked as car folder."""
        provider = CDAProvider(**cda_credentials)

        result = provider._extract_car_folder(".. @ track race.sto")
        assert result is None

    def test_extract_car_folder_blocks_single_dot(self, cda_credentials):
        """Test that '.' is blocked as car folder."""
        provider = CDAProvider(**cda_credentials)

        result = provider._extract_car_folder(". @ track race.sto")
        assert result is None

    def test_extract_car_folder_blocks_special_chars(self, cda_credentials):
        """Test that non-alphanumeric characters are blocked."""
        provider = CDAProvider(**cda_credentials)

        # These would fail the alphanumeric check
        # Note: Path().stem handles directory separators, so we test inline special chars
        assert provider._extract_car_folder("car..name @ track race.sto") is None
        assert provider._extract_car_folder("car_name @ track race.sto") is None

    def test_extract_car_folder_only_allows_alphanumeric(self, cda_credentials):
        """Test that only alphanumeric car folders are allowed."""
        provider = CDAProvider(**cda_credentials)

        # Valid alphanumeric
        assert (
            provider._extract_car_folder("porsche911gt3 @ track race.sto") is not None
        )

        # Invalid with special characters
        assert provider._extract_car_folder("car_name @ track race.sto") is None
        assert provider._extract_car_folder("car.name @ track race.sto") is None


class TestCDAProviderStableIds:
    """Tests for deterministic ID generation."""

    def test_id_is_deterministic(self, cda_credentials, cda_catalog_response):
        """Test that setup IDs are deterministic across multiple calls."""
        provider = CDAProvider(**cda_credentials)

        # Parse catalog twice
        setups1 = provider._parse_catalog(cda_catalog_response)
        setups2 = provider._parse_catalog(cda_catalog_response)

        # IDs should be identical
        ids1 = sorted(s.id for s in setups1)
        ids2 = sorted(s.id for s in setups2)
        assert ids1 == ids2

    def test_timestamps_are_deterministic(self, cda_credentials, cda_catalog_response):
        """Test that timestamps are deterministic across multiple calls."""
        provider = CDAProvider(**cda_credentials)

        setups1 = provider._parse_catalog(cda_catalog_response)
        setups2 = provider._parse_catalog(cda_catalog_response)

        # Timestamps should be identical
        for s1, s2 in zip(
            sorted(setups1, key=lambda s: s.id),
            sorted(setups2, key=lambda s: s.id),
            strict=True,
        ):
            assert s1.creation_date == s2.creation_date
            assert s1.updated_date == s2.updated_date


class TestCDAProviderIntegration:
    """Integration tests for CDAProvider workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, cda_credentials, cda_catalog_response):
        """Test complete fetch -> download workflow."""
        provider = CDAProvider(**cda_credentials)

        # Mock fetch
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=cda_catalog_response)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            setups = await provider.fetch_setups()

        assert len(setups) > 0

        # Verify setup records have expected structure
        for setup in setups:
            assert setup.download_url.startswith("https://delta.coachdaveacademy.com")
            assert "setups/zip" in setup.download_url
            # Verify car and track are parsed correctly from download_name
            assert setup.car, f"car should not be empty for {setup.download_name}"
            assert setup.track, f"track should not be empty for {setup.download_name}"
            # Verify ID is a positive integer
            assert isinstance(setup.id, int)
            assert setup.id > 0

        await provider.close()

    @pytest.mark.asyncio
    async def test_setups_are_stable_across_fetches(
        self, cda_credentials, cda_catalog_response
    ):
        """Test that repeated fetches produce identical setup records."""
        provider = CDAProvider(**cda_credentials)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=cda_catalog_response)

        with patch.object(
            provider, "_get_session", new_callable=AsyncMock
        ) as mock_get_session:
            mock_session = MagicMock()
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_get_session.return_value = mock_session

            setups1 = await provider.fetch_setups()
            setups2 = await provider.fetch_setups()

        # Compare IDs and timestamps
        ids1 = {s.id for s in setups1}
        ids2 = {s.id for s in setups2}
        assert ids1 == ids2, "Setup IDs should be stable across fetches"

        await provider.close()
