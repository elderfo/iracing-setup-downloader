"""Tests for CLI commands."""

from unittest.mock import AsyncMock, MagicMock, patch

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
