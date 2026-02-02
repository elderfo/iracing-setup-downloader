"""Tests for CLI commands."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from iracing_setup_downloader.cli import app
from iracing_setup_downloader.downloader import DownloadResult

runner = CliRunner()


def test_version():
    """Test --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "iracing-setup-downloader version: 0.1.0" in result.stdout


def test_help():
    """Test --help flag."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "A CLI tool for downloading iRacing setups" in result.stdout


def test_download_help():
    """Test download command help."""
    result = runner.invoke(app, ["download", "--help"])
    assert result.exit_code == 0
    assert "Download setups from a provider" in result.stdout


def test_download_gofast_help():
    """Test download gofast command help."""
    result = runner.invoke(app, ["download", "gofast", "--help"])
    assert result.exit_code == 0
    assert "Download setups from GoFast provider" in result.stdout


def test_download_gofast_no_token():
    """Test download gofast without token should fail."""
    result = runner.invoke(app, ["download", "gofast"])
    assert result.exit_code == 1
    assert "GoFast token is required" in result.stdout


def test_list_help():
    """Test list command help."""
    result = runner.invoke(app, ["list", "--help"])
    assert result.exit_code == 0
    assert "List available setups from a provider" in result.stdout


def test_list_gofast_help():
    """Test list gofast command help."""
    result = runner.invoke(app, ["list", "gofast", "--help"])
    assert result.exit_code == 0
    assert "List available setups from GoFast provider" in result.stdout


def test_list_gofast_no_token():
    """Test list gofast without token should fail."""
    result = runner.invoke(app, ["list", "gofast"])
    assert result.exit_code == 1
    assert "GoFast token is required" in result.stdout


@patch("iracing_setup_downloader.cli.GoFastProvider")
@patch("iracing_setup_downloader.cli.DownloadState")
@patch("iracing_setup_downloader.cli.SetupDownloader")
def test_download_gofast_dry_run(
    mock_downloader_class, mock_state_class, mock_provider_class
):
    """Test download gofast with dry run."""
    # Mock the provider
    mock_provider = MagicMock()
    mock_provider.name = "gofast"
    mock_provider.close = AsyncMock()
    mock_provider_class.return_value = mock_provider

    # Mock the state
    mock_state = MagicMock()
    mock_state.load = MagicMock()
    mock_state.save = MagicMock()
    mock_state_class.return_value = mock_state

    # Mock the downloader
    mock_downloader = MagicMock()
    mock_result = DownloadResult(total_available=10, skipped=5, downloaded=0, failed=0)
    mock_downloader.download_all = AsyncMock(return_value=mock_result)
    mock_downloader_class.return_value = mock_downloader

    # Run the command
    result = runner.invoke(
        app, ["download", "gofast", "--token", "Bearer test123", "--dry-run"]
    )

    # Verify the result
    assert result.exit_code == 0
    assert "Configuration" in result.stdout
    assert "GoFast" in result.stdout
    assert "Dry Run" in result.stdout

    # Verify mocks were called correctly
    mock_provider_class.assert_called_once()
    mock_state.load.assert_called_once()
    # State should not be saved on dry run
    mock_state.save.assert_not_called()


@patch("iracing_setup_downloader.cli.GoFastProvider")
def test_list_gofast_empty(mock_provider_class):
    """Test list gofast with no setups."""
    # Mock the provider
    mock_provider = MagicMock()
    mock_provider.fetch_setups = AsyncMock(return_value=[])
    mock_provider.close = AsyncMock()
    mock_provider_class.return_value = mock_provider

    # Run the command
    result = runner.invoke(app, ["list", "gofast", "--token", "Bearer test123"])

    # Verify the result
    assert result.exit_code == 0
    assert "Fetching setups from GoFast" in result.stdout
    assert "No setups found" in result.stdout

    # Verify provider was closed
    mock_provider.close.assert_called_once()


def test_organize_help():
    """Test organize command help."""
    result = runner.invoke(app, ["organize", "--help"])
    assert result.exit_code == 0
    assert "Organize existing setup files" in result.stdout


def test_organize_nonexistent_directory():
    """Test organize with nonexistent directory."""
    result = runner.invoke(app, ["organize", "/nonexistent/path"])
    # Typer validates this and returns exit code 2
    assert result.exit_code == 2


@pytest.fixture
def sample_tracks_json(tmp_path):
    """Create a sample tracks.json for testing."""
    tracks_data = {
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
        ],
    }
    tracks_file = tmp_path / "tracks.json"
    with open(tracks_file, "w") as f:
        json.dump(tracks_data, f)
    return tracks_file


def test_organize_dry_run(tmp_path, sample_tracks_json):
    """Test organize with dry run."""
    # Create test setup file
    car_dir = tmp_path / "ferrari296gt3"
    car_dir.mkdir()
    setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
    setup_file.write_text("setup content")

    # Mock get_settings to use our tracks file
    with patch("iracing_setup_downloader.cli.get_settings") as mock_settings:
        mock_settings.return_value.tracks_data_path = sample_tracks_json

        result = runner.invoke(app, ["organize", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    assert "Organization Results (Dry Run)" in result.stdout
    # File should still be in original location
    assert setup_file.exists()


def test_organize_empty_directory(tmp_path, sample_tracks_json):
    """Test organize with empty directory."""
    with patch("iracing_setup_downloader.cli.get_settings") as mock_settings:
        mock_settings.return_value.tracks_data_path = sample_tracks_json

        result = runner.invoke(app, ["organize", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    assert "Total Files:" in result.stdout
    assert "0" in result.stdout


def test_organize_with_output(tmp_path, sample_tracks_json):
    """Test organize with output directory."""
    # Create source directory with setup
    source_dir = tmp_path / "source"
    car_dir = source_dir / "ferrari296gt3"
    car_dir.mkdir(parents=True)
    setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
    setup_file.write_text("setup content")

    # Create output directory
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch("iracing_setup_downloader.cli.get_settings") as mock_settings:
        mock_settings.return_value.tracks_data_path = sample_tracks_json

        result = runner.invoke(
            app,
            ["organize", str(source_dir), "--output", str(output_dir), "--dry-run"],
        )

    assert result.exit_code == 0
    assert "Organization Results (Dry Run)" in result.stdout


def test_organize_with_category_hint(tmp_path, sample_tracks_json):
    """Test organize with category hint."""
    car_dir = tmp_path / "ferrari296gt3"
    car_dir.mkdir()
    setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
    setup_file.write_text("setup content")

    with patch("iracing_setup_downloader.cli.get_settings") as mock_settings:
        mock_settings.return_value.tracks_data_path = sample_tracks_json

        result = runner.invoke(
            app,
            ["organize", str(tmp_path), "--category", "GT3", "--dry-run"],
        )

    assert result.exit_code == 0
    assert "GT3" in result.stdout  # Category should be displayed


def test_organize_verbose(tmp_path, sample_tracks_json):
    """Test organize with verbose output."""
    car_dir = tmp_path / "ferrari296gt3"
    car_dir.mkdir()
    setup_file = car_dir / "GoFast_IMSA_26S1W8_Spa_Race.sto"
    setup_file.write_text("setup content")

    with patch("iracing_setup_downloader.cli.get_settings") as mock_settings:
        mock_settings.return_value.tracks_data_path = sample_tracks_json

        result = runner.invoke(
            app,
            ["organize", str(tmp_path), "--dry-run", "--verbose"],
        )

    assert result.exit_code == 0
    # Verbose should show file movements
    assert "Would move" in result.stdout or "Organized:" in result.stdout
