"""CLI entry point for iRacing Setup Downloader."""

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from iracing_setup_downloader import __version__
from iracing_setup_downloader.config import get_settings
from iracing_setup_downloader.deduplication import DuplicateDetector, FileHashCache
from iracing_setup_downloader.downloader import SetupDownloader
from iracing_setup_downloader.organizer import OrganizeResult, SetupOrganizer
from iracing_setup_downloader.providers import (
    CDAProvider,
    GoFastProvider,
    TracKTitanProvider,
)
from iracing_setup_downloader.providers.cda import (
    CDAAuthenticationError,
    CDAProviderError,
)
from iracing_setup_downloader.providers.gofast import (
    GoFastAuthenticationError,
    GoFastProviderError,
)
from iracing_setup_downloader.providers.tracktitan import (
    TracKTitanAuthenticationError,
    TracKTitanProviderError,
)
from iracing_setup_downloader.state import DownloadState
from iracing_setup_downloader.track_matcher import TrackMatcher


def _format_bytes(size: int) -> str:
    """Format bytes into human-readable string.

    Args:
        size: Size in bytes

    Returns:
        Human-readable string like "1.5 MB" or "256 KB"
    """
    size_float = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_float) < 1024:
            if unit == "B":
                return f"{int(size_float)} {unit}"
            return f"{size_float:.1f} {unit}"
        size_float /= 1024
    return f"{size_float:.1f} TB"


app = typer.Typer(
    name="iracing-setup-downloader",
    help="A CLI tool for downloading iRacing setups from various providers.",
    add_completion=False,
)
console = Console()

# Create sub-apps for commands
download_app = typer.Typer(
    help="Download setups from a provider",
    add_completion=False,
)
list_app = typer.Typer(
    help="List available setups from a provider",
    add_completion=False,
)

app.add_typer(download_app, name="download")
app.add_typer(list_app, name="list")


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"iracing-setup-downloader version: {__version__}")
        raise typer.Exit()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application.

    Args:
        verbose: If True, set log level to DEBUG, otherwise INFO
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """iRacing Setup Downloader - Download setups from various providers."""


@download_app.command("gofast")
def download_gofast(
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GoFast bearer token (overrides env var)",
        envvar="GOFAST_TOKEN",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory path (overrides env var)",
        envvar="OUTPUT_PATH",
    ),
    max_concurrent: int | None = typer.Option(
        None,
        "--max-concurrent",
        "-c",
        help="Maximum number of parallel downloads",
        min=1,
        max=20,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be downloaded without downloading",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose logging",
    ),
) -> None:
    """Download setups from GoFast provider.

    Requires a GoFast bearer token for authentication.
    Token can be provided via --token flag or GOFAST_TOKEN environment variable.

    Example:
        iracing-setup-downloader download gofast --token "Bearer xxx" --output ~/setups
    """
    setup_logging(verbose)

    try:
        # Load settings from config
        settings = get_settings()

        # Override settings with CLI arguments
        if token:
            settings.token = token
        if output:
            settings.output_path = output
        if max_concurrent is not None:
            settings.max_concurrent = max_concurrent

        # Validate token
        if not settings.token:
            console.print(
                "[red]Error:[/red] GoFast token is required. "
                "Provide via --token flag or GOFAST_TOKEN environment variable."
            )
            raise typer.Exit(code=1)

        # Ensure token has Bearer prefix
        if not settings.token.startswith("Bearer "):
            settings.token = f"Bearer {settings.token}"

        # Display configuration
        config_table = Table(title="Configuration", show_header=False, box=None)
        config_table.add_row("Provider:", "[cyan]GoFast[/cyan]")
        config_table.add_row("Output Path:", str(settings.output_path))
        config_table.add_row("Max Concurrent:", str(settings.max_concurrent))
        config_table.add_row("Dry Run:", "[yellow]Yes[/yellow]" if dry_run else "No")
        console.print(config_table)
        console.print()

        # Initialize track matcher
        track_matcher = TrackMatcher(settings.tracks_data_path)
        try:
            track_matcher.load()
        except FileNotFoundError as e:
            console.print(f"[yellow]Warning:[/yellow] Could not load tracks data: {e}")
            console.print(
                "[yellow]Track-based folder organization will be disabled.[/yellow]"
            )
            track_matcher = None

        # Run async download
        asyncio.run(
            _download_gofast_async(
                settings.token,
                settings.output_path,
                settings.max_concurrent,
                settings.min_delay,
                settings.max_delay,
                settings.max_retries,
                dry_run,
                track_matcher,
            )
        )

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Download cancelled by user.[/yellow]")
        raise typer.Exit(code=130) from None
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1) from e


async def _download_gofast_async(
    token: str,
    output_path: Path,
    max_concurrent: int,
    min_delay: float,
    max_delay: float,
    max_retries: int,
    dry_run: bool,
    track_matcher: TrackMatcher | None = None,
) -> None:
    """Async implementation of GoFast download.

    Args:
        token: GoFast bearer token
        output_path: Directory to save setups
        max_concurrent: Maximum parallel downloads
        min_delay: Minimum delay between downloads
        max_delay: Maximum delay between downloads
        max_retries: Maximum retry attempts
        dry_run: If True, don't actually download
        track_matcher: Optional TrackMatcher for track-based folder organization
    """
    # Initialize persistent hash cache
    hash_cache = FileHashCache()
    hash_cache.load()

    # Initialize duplicate detector with persistent cache and build index
    duplicate_detector = DuplicateDetector(hash_cache=hash_cache)
    if output_path.exists() and not dry_run:
        console.print("[bold]Building duplicate detection index...[/bold]")
        duplicate_detector.build_index(output_path)

    provider = GoFastProvider(
        token=token,
        track_matcher=track_matcher,
        duplicate_detector=duplicate_detector if not dry_run else None,
    )

    try:
        # Create and load state
        state = DownloadState()
        state.load()

        # Create downloader
        downloader = SetupDownloader(
            provider=provider,
            state=state,
            max_concurrent=max_concurrent,
            min_delay=min_delay,
            max_delay=max_delay,
            max_retries=max_retries,
        )

        # Download all setups
        console.print("[bold]Starting download...[/bold]\n")
        result = await downloader.download_all(output_path, dry_run=dry_run)

        # Save state and hash cache
        if not dry_run:
            state.save()
            try:
                hash_cache.save()
            except OSError as e:
                console.print(
                    f"[yellow]Warning:[/yellow] Could not save hash cache: {e}"
                )

        # Display results
        console.print()
        _display_download_results(result, dry_run)

    except GoFastAuthenticationError as e:
        console.print(f"[red]Authentication Error:[/red] {e}")
        console.print(
            "\n[yellow]Hint:[/yellow] Check that your GoFast token is valid and has the correct permissions."
        )
        raise typer.Exit(code=1) from e
    except GoFastProviderError as e:
        console.print(f"[red]Provider Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise
    finally:
        await provider.close()


def _display_download_results(result, dry_run: bool) -> None:
    """Display download results in a formatted panel.

    Args:
        result: DownloadResult object
        dry_run: Whether this was a dry run
    """
    # Create results table
    results_table = Table(show_header=False, box=None, padding=(0, 2))
    results_table.add_column("Label", style="bold")
    results_table.add_column("Value")

    results_table.add_row("Total Available:", str(result.total_available))
    if dry_run:
        results_table.add_row(
            "Would Download:", f"[cyan]{result.total_available - result.skipped}[/cyan]"
        )
    else:
        results_table.add_row("Downloaded:", f"[green]{result.downloaded}[/green]")
    results_table.add_row("Skipped:", f"[yellow]{result.skipped}[/yellow]")
    if result.failed > 0:
        results_table.add_row("Failed:", f"[red]{result.failed}[/red]")
    if result.duplicates_skipped > 0:
        results_table.add_row(
            "Duplicates Skipped:", f"[magenta]{result.duplicates_skipped}[/magenta]"
        )
        if result.bytes_saved > 0:
            results_table.add_row(
                "Space Saved:",
                f"[magenta]{_format_bytes(result.bytes_saved)}[/magenta]",
            )

    title = "Download Results (Dry Run)" if dry_run else "Download Results"
    console.print(Panel(results_table, title=title, border_style="green"))

    # Display errors if any
    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for setup_id, error in result.errors:
            console.print(f"  [red]•[/red] Setup {setup_id}: {error}")


@list_app.command("gofast")
def list_gofast(
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GoFast bearer token (overrides env var)",
        envvar="GOFAST_TOKEN",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose logging",
    ),
) -> None:
    """List available setups from GoFast provider.

    Requires a GoFast bearer token for authentication.
    Token can be provided via --token flag or GOFAST_TOKEN environment variable.

    Example:
        iracing-setup-downloader list gofast --token "Bearer xxx"
    """
    setup_logging(verbose)

    try:
        # Load settings from config
        settings = get_settings()

        # Override settings with CLI arguments
        if token:
            settings.token = token

        # Validate token
        if not settings.token:
            console.print(
                "[red]Error:[/red] GoFast token is required. "
                "Provide via --token flag or GOFAST_TOKEN environment variable."
            )
            raise typer.Exit(code=1)

        # Ensure token has Bearer prefix
        if not settings.token.startswith("Bearer "):
            settings.token = f"Bearer {settings.token}"

        # Run async list
        asyncio.run(_list_gofast_async(settings.token))

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user.[/yellow]")
        raise typer.Exit(code=130) from None
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1) from e


async def _list_gofast_async(token: str) -> None:
    """Async implementation of GoFast list.

    Args:
        token: GoFast bearer token
    """
    provider = GoFastProvider(token=token)

    try:
        # Fetch setups
        console.print("[bold]Fetching setups from GoFast...[/bold]\n")
        setups = await provider.fetch_setups()

        if not setups:
            console.print("[yellow]No setups found.[/yellow]")
            return

        # Create table
        table = Table(
            title=f"Available GoFast Setups ({len(setups)} total)",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("ID", style="dim", width=8)
        table.add_column("Car", style="cyan", no_wrap=False)
        table.add_column("Track", style="green", no_wrap=False)
        table.add_column("Series", style="yellow")
        table.add_column("Season", style="magenta")
        table.add_column("Updated", style="blue")

        # Add rows
        for setup in setups:
            table.add_row(
                str(setup.id),
                setup.car or "N/A",
                setup.track or "N/A",
                setup.series,
                setup.season,
                setup.updated_date.strftime("%Y-%m-%d %H:%M"),
            )

        console.print(table)

    except GoFastAuthenticationError as e:
        console.print(f"[red]Authentication Error:[/red] {e}")
        console.print(
            "\n[yellow]Hint:[/yellow] Check that your GoFast token is valid and has the correct permissions."
        )
        raise typer.Exit(code=1) from e
    except GoFastProviderError as e:
        console.print(f"[red]Provider Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise
    finally:
        await provider.close()


@download_app.command("cda")
def download_cda(
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        "-s",
        help="CDA PHPSESSID cookie (overrides env var)",
        envvar="CDA_SESSION_ID",
    ),
    csrf_token: str | None = typer.Option(
        None,
        "--csrf-token",
        "-c",
        help="CDA x-elle-csrf-token header (overrides env var)",
        envvar="CDA_CSRF_TOKEN",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory path (overrides env var)",
        envvar="OUTPUT_PATH",
    ),
    max_concurrent: int | None = typer.Option(
        None,
        "--max-concurrent",
        help="Maximum number of parallel downloads",
        min=1,
        max=20,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be downloaded without downloading",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose logging",
    ),
) -> None:
    """Download setups from Coach Dave Academy (CDA) provider.

    Requires CDA authentication credentials:
    - PHPSESSID cookie (session ID)
    - x-elle-csrf-token header (CSRF token)

    Both can be obtained from browser developer tools while logged into CDA.

    Example:
        iracing-setup-downloader download cda --session-id abc123 --csrf-token xyz789
    """
    setup_logging(verbose)

    try:
        # Load settings from config
        settings = get_settings()

        # Override settings with CLI arguments
        if session_id:
            settings.cda_session_id = session_id
        if csrf_token:
            settings.cda_csrf_token = csrf_token
        if output:
            settings.output_path = output
        if max_concurrent is not None:
            settings.max_concurrent = max_concurrent

        # Validate credentials
        if not settings.cda_session_id:
            console.print(
                "[red]Error:[/red] CDA session ID is required. "
                "Provide via --session-id flag or CDA_SESSION_ID environment variable."
            )
            raise typer.Exit(code=1)

        if not settings.cda_csrf_token:
            console.print(
                "[red]Error:[/red] CDA CSRF token is required. "
                "Provide via --csrf-token flag or CDA_CSRF_TOKEN environment variable."
            )
            raise typer.Exit(code=1)

        # Display configuration
        config_table = Table(title="Configuration", show_header=False, box=None)
        config_table.add_row("Provider:", "[cyan]CDA (Coach Dave Academy)[/cyan]")
        config_table.add_row("Output Path:", str(settings.output_path))
        config_table.add_row("Max Concurrent:", str(settings.max_concurrent))
        config_table.add_row("Dry Run:", "[yellow]Yes[/yellow]" if dry_run else "No")
        console.print(config_table)
        console.print()

        # Initialize track matcher
        track_matcher = TrackMatcher(settings.tracks_data_path)
        try:
            track_matcher.load()
        except FileNotFoundError as e:
            console.print(f"[yellow]Warning:[/yellow] Could not load tracks data: {e}")
            console.print(
                "[yellow]Track-based folder organization will be disabled.[/yellow]"
            )
            track_matcher = None

        # Run async download
        asyncio.run(
            _download_cda_async(
                settings.cda_session_id,
                settings.cda_csrf_token,
                settings.output_path,
                settings.max_concurrent,
                settings.min_delay,
                settings.max_delay,
                settings.max_retries,
                dry_run,
                track_matcher,
            )
        )

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Download cancelled by user.[/yellow]")
        raise typer.Exit(code=130) from None
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1) from e


async def _download_cda_async(
    session_id: str,
    csrf_token: str,
    output_path: Path,
    max_concurrent: int,
    min_delay: float,
    max_delay: float,
    max_retries: int,
    dry_run: bool,
    track_matcher: TrackMatcher | None = None,
) -> None:
    """Async implementation of CDA download.

    Args:
        session_id: CDA PHPSESSID cookie
        csrf_token: CDA x-elle-csrf-token header
        output_path: Directory to save setups
        max_concurrent: Maximum parallel downloads
        min_delay: Minimum delay between downloads
        max_delay: Maximum delay between downloads
        max_retries: Maximum retry attempts
        dry_run: If True, don't actually download
        track_matcher: Optional TrackMatcher for track-based folder organization
    """
    # Initialize persistent hash cache
    hash_cache = FileHashCache()
    hash_cache.load()

    # Initialize duplicate detector with persistent cache and build index
    duplicate_detector = DuplicateDetector(hash_cache=hash_cache)
    if output_path.exists() and not dry_run:
        console.print("[bold]Building duplicate detection index...[/bold]")
        duplicate_detector.build_index(output_path)

    provider = CDAProvider(
        session_id=session_id,
        csrf_token=csrf_token,
        track_matcher=track_matcher,
        duplicate_detector=duplicate_detector if not dry_run else None,
    )

    try:
        # Create and load state
        state = DownloadState()
        state.load()

        # Create downloader
        downloader = SetupDownloader(
            provider=provider,
            state=state,
            max_concurrent=max_concurrent,
            min_delay=min_delay,
            max_delay=max_delay,
            max_retries=max_retries,
        )

        # Download all setups
        console.print("[bold]Starting download...[/bold]\n")
        result = await downloader.download_all(output_path, dry_run=dry_run)

        # Save state and hash cache
        if not dry_run:
            state.save()
            try:
                hash_cache.save()
            except OSError as e:
                console.print(
                    f"[yellow]Warning:[/yellow] Could not save hash cache: {e}"
                )

        # Display results
        console.print()
        _display_download_results(result, dry_run)

    except CDAAuthenticationError as e:
        console.print(f"[red]Authentication Error:[/red] {e}")
        console.print(
            "\n[yellow]Hint:[/yellow] Check that your CDA session ID and CSRF token are valid. "
            "You can obtain them from browser developer tools while logged into CDA."
        )
        raise typer.Exit(code=1) from e
    except CDAProviderError as e:
        console.print(f"[red]Provider Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise
    finally:
        await provider.close()


@list_app.command("cda")
def list_cda(
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        "-s",
        help="CDA PHPSESSID cookie (overrides env var)",
        envvar="CDA_SESSION_ID",
    ),
    csrf_token: str | None = typer.Option(
        None,
        "--csrf-token",
        "-c",
        help="CDA x-elle-csrf-token header (overrides env var)",
        envvar="CDA_CSRF_TOKEN",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose logging",
    ),
) -> None:
    """List available setups from Coach Dave Academy (CDA) provider.

    Requires CDA authentication credentials:
    - PHPSESSID cookie (session ID)
    - x-elle-csrf-token header (CSRF token)

    Example:
        iracing-setup-downloader list cda --session-id abc123 --csrf-token xyz789
    """
    setup_logging(verbose)

    try:
        # Load settings from config
        settings = get_settings()

        # Override settings with CLI arguments
        if session_id:
            settings.cda_session_id = session_id
        if csrf_token:
            settings.cda_csrf_token = csrf_token

        # Validate credentials
        if not settings.cda_session_id:
            console.print(
                "[red]Error:[/red] CDA session ID is required. "
                "Provide via --session-id flag or CDA_SESSION_ID environment variable."
            )
            raise typer.Exit(code=1)

        if not settings.cda_csrf_token:
            console.print(
                "[red]Error:[/red] CDA CSRF token is required. "
                "Provide via --csrf-token flag or CDA_CSRF_TOKEN environment variable."
            )
            raise typer.Exit(code=1)

        # Run async list
        asyncio.run(_list_cda_async(settings.cda_session_id, settings.cda_csrf_token))

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user.[/yellow]")
        raise typer.Exit(code=130) from None
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1) from e


async def _list_cda_async(session_id: str, csrf_token: str) -> None:
    """Async implementation of CDA list.

    Args:
        session_id: CDA PHPSESSID cookie
        csrf_token: CDA x-elle-csrf-token header
    """
    provider = CDAProvider(session_id=session_id, csrf_token=csrf_token)

    try:
        # Fetch setups
        console.print("[bold]Fetching setups from CDA...[/bold]\n")
        setups = await provider.fetch_setups()

        if not setups:
            console.print("[yellow]No setups found.[/yellow]")
            return

        # Create table
        table = Table(
            title=f"Available CDA Setups ({len(setups)} total)",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("ID", style="dim", width=10)
        table.add_column("Car", style="cyan", no_wrap=False)
        table.add_column("Track", style="green", no_wrap=False)
        table.add_column("Series", style="yellow")
        table.add_column("Season", style="magenta")

        # Add rows
        for setup in setups:
            table.add_row(
                str(setup.id),
                setup.car or "N/A",
                setup.track or "N/A",
                setup.series,
                setup.season,
            )

        console.print(table)

    except CDAAuthenticationError as e:
        console.print(f"[red]Authentication Error:[/red] {e}")
        console.print(
            "\n[yellow]Hint:[/yellow] Check that your CDA session ID and CSRF token are valid. "
            "You can obtain them from browser developer tools while logged into CDA."
        )
        raise typer.Exit(code=1) from e
    except CDAProviderError as e:
        console.print(f"[red]Provider Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise
    finally:
        await provider.close()


@download_app.command("tracktitan")
def download_tracktitan(
    access_token: str | None = typer.Option(
        None,
        "--access-token",
        "-t",
        help="Track Titan access token (overrides env var)",
        envvar="TT_ACCESS_TOKEN",
    ),
    user_id: str | None = typer.Option(
        None,
        "--user-id",
        "-u",
        help="Track Titan user UUID (overrides env var)",
        envvar="TT_USER_ID",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory path (overrides env var)",
        envvar="OUTPUT_PATH",
    ),
    max_concurrent: int | None = typer.Option(
        None,
        "--max-concurrent",
        help="Maximum number of parallel downloads",
        min=1,
        max=20,
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of new setups to download",
        min=1,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be downloaded without downloading",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose logging",
    ),
) -> None:
    """Download setups from Track Titan provider.

    Requires Track Titan authentication credentials:
    - Access token (AWS Cognito JWT)
    - User ID (UUID)

    Both can be obtained from browser developer tools while logged into Track Titan.

    Example:
        iracing-setup-downloader download tracktitan --access-token eyJ... --user-id abc-123
    """
    setup_logging(verbose)

    try:
        # Load settings from config
        settings = get_settings()

        # Override settings with CLI arguments
        if access_token:
            settings.tt_access_token = access_token
        if user_id:
            settings.tt_user_id = user_id
        if output:
            settings.output_path = output
        if max_concurrent is not None:
            settings.max_concurrent = max_concurrent

        # Validate credentials
        if not settings.tt_access_token:
            console.print(
                "[red]Error:[/red] Track Titan access token is required. "
                "Provide via --access-token flag or TT_ACCESS_TOKEN environment variable."
            )
            raise typer.Exit(code=1)

        if not settings.tt_user_id:
            console.print(
                "[red]Error:[/red] Track Titan user ID is required. "
                "Provide via --user-id flag or TT_USER_ID environment variable."
            )
            raise typer.Exit(code=1)

        # Display configuration
        config_table = Table(title="Configuration", show_header=False, box=None)
        config_table.add_row("Provider:", "[cyan]Track Titan[/cyan]")
        config_table.add_row("Output Path:", str(settings.output_path))
        config_table.add_row("Max Concurrent:", str(settings.max_concurrent))
        if limit is not None:
            config_table.add_row("Download Limit:", f"[magenta]{limit}[/magenta]")
        config_table.add_row("Dry Run:", "[yellow]Yes[/yellow]" if dry_run else "No")
        console.print(config_table)
        console.print()

        # Initialize track matcher
        track_matcher = TrackMatcher(settings.tracks_data_path)
        try:
            track_matcher.load()
        except FileNotFoundError as e:
            console.print(f"[yellow]Warning:[/yellow] Could not load tracks data: {e}")
            console.print(
                "[yellow]Track-based folder organization will be disabled.[/yellow]"
            )
            track_matcher = None

        # Run async download
        asyncio.run(
            _download_tracktitan_async(
                settings.tt_access_token,
                settings.tt_user_id,
                settings.output_path,
                settings.max_concurrent,
                settings.min_delay,
                settings.max_delay,
                settings.max_retries,
                dry_run,
                track_matcher,
                limit,
            )
        )

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Download cancelled by user.[/yellow]")
        raise typer.Exit(code=130) from None
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1) from e


async def _download_tracktitan_async(
    access_token: str,
    user_id: str,
    output_path: Path,
    max_concurrent: int,
    min_delay: float,
    max_delay: float,
    max_retries: int,
    dry_run: bool,
    track_matcher: TrackMatcher | None = None,
    limit: int | None = None,
) -> None:
    """Async implementation of Track Titan download.

    Args:
        access_token: Track Titan AWS Cognito access token
        user_id: Track Titan user UUID
        output_path: Directory to save setups
        max_concurrent: Maximum parallel downloads
        min_delay: Minimum delay between downloads
        max_delay: Maximum delay between downloads
        max_retries: Maximum retry attempts
        dry_run: If True, don't actually download
        track_matcher: Optional TrackMatcher for track-based folder organization
        limit: Maximum number of new setups to download
    """
    # Initialize persistent hash cache
    hash_cache = FileHashCache()
    hash_cache.load()

    # Initialize duplicate detector with persistent cache and build index
    duplicate_detector = DuplicateDetector(hash_cache=hash_cache)
    if output_path.exists() and not dry_run:
        console.print("[bold]Building duplicate detection index...[/bold]")
        duplicate_detector.build_index(output_path)

    provider = TracKTitanProvider(
        access_token=access_token,
        user_id=user_id,
        track_matcher=track_matcher,
        duplicate_detector=duplicate_detector if not dry_run else None,
    )

    try:
        # Create and load state
        state = DownloadState()
        state.load()

        # Create downloader
        downloader = SetupDownloader(
            provider=provider,
            state=state,
            max_concurrent=max_concurrent,
            min_delay=min_delay,
            max_delay=max_delay,
            max_retries=max_retries,
        )

        # Download all setups
        console.print("[bold]Starting download...[/bold]\n")
        result = await downloader.download_all(
            output_path, dry_run=dry_run, limit=limit
        )

        # Save state and hash cache
        if not dry_run:
            state.save()
            try:
                hash_cache.save()
            except OSError as e:
                console.print(
                    f"[yellow]Warning:[/yellow] Could not save hash cache: {e}"
                )

        # Display results
        console.print()
        _display_download_results(result, dry_run)

    except TracKTitanAuthenticationError as e:
        console.print(f"[red]Authentication Error:[/red] {e}")
        console.print(
            "\n[yellow]Hint:[/yellow] Check that your Track Titan access token and "
            "user ID are valid. You can obtain them from browser developer tools "
            "while logged into Track Titan."
        )
        raise typer.Exit(code=1) from e
    except TracKTitanProviderError as e:
        console.print(f"[red]Provider Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise
    finally:
        await provider.close()


@list_app.command("tracktitan")
def list_tracktitan(
    access_token: str | None = typer.Option(
        None,
        "--access-token",
        "-t",
        help="Track Titan access token (overrides env var)",
        envvar="TT_ACCESS_TOKEN",
    ),
    user_id: str | None = typer.Option(
        None,
        "--user-id",
        "-u",
        help="Track Titan user UUID (overrides env var)",
        envvar="TT_USER_ID",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose logging",
    ),
) -> None:
    """List available setups from Track Titan provider.

    Requires Track Titan authentication credentials:
    - Access token (AWS Cognito JWT)
    - User ID (UUID)

    Example:
        iracing-setup-downloader list tracktitan --access-token eyJ... --user-id abc-123
    """
    setup_logging(verbose)

    try:
        # Load settings from config
        settings = get_settings()

        # Override settings with CLI arguments
        if access_token:
            settings.tt_access_token = access_token
        if user_id:
            settings.tt_user_id = user_id

        # Validate credentials
        if not settings.tt_access_token:
            console.print(
                "[red]Error:[/red] Track Titan access token is required. "
                "Provide via --access-token flag or TT_ACCESS_TOKEN environment variable."
            )
            raise typer.Exit(code=1)

        if not settings.tt_user_id:
            console.print(
                "[red]Error:[/red] Track Titan user ID is required. "
                "Provide via --user-id flag or TT_USER_ID environment variable."
            )
            raise typer.Exit(code=1)

        # Run async list
        asyncio.run(
            _list_tracktitan_async(settings.tt_access_token, settings.tt_user_id)
        )

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user.[/yellow]")
        raise typer.Exit(code=130) from None
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1) from e


async def _list_tracktitan_async(access_token: str, user_id: str) -> None:
    """Async implementation of Track Titan list.

    Args:
        access_token: Track Titan AWS Cognito access token
        user_id: Track Titan user UUID
    """
    provider = TracKTitanProvider(access_token=access_token, user_id=user_id)

    try:
        # Fetch setups
        console.print("[bold]Fetching setups from Track Titan...[/bold]\n")
        setups = await provider.fetch_setups()

        if not setups:
            console.print("[yellow]No setups found.[/yellow]")
            return

        # Create table
        table = Table(
            title=f"Available Track Titan Setups ({len(setups)} total)",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("ID", style="dim", width=10)
        table.add_column("Car", style="cyan", no_wrap=False)
        table.add_column("Track", style="green", no_wrap=False)
        table.add_column("Series", style="yellow")
        table.add_column("Season", style="magenta")
        table.add_column("Updated", style="blue")

        # Add rows
        for setup in setups:
            table.add_row(
                str(setup.id),
                setup.car or "N/A",
                setup.track or "N/A",
                setup.series,
                setup.season,
                setup.updated_date.strftime("%Y-%m-%d %H:%M"),
            )

        console.print(table)

    except TracKTitanAuthenticationError as e:
        console.print(f"[red]Authentication Error:[/red] {e}")
        console.print(
            "\n[yellow]Hint:[/yellow] Check that your Track Titan access token and "
            "user ID are valid. You can obtain them from browser developer tools "
            "while logged into Track Titan."
        )
        raise typer.Exit(code=1) from e
    except TracKTitanProviderError as e:
        console.print(f"[red]Provider Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise
    finally:
        await provider.close()


@app.command("organize")
def organize_setups(
    source: Path = typer.Argument(
        ...,
        help="Directory containing setup files to organize",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (default: organize in place)",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without making changes",
    ),
    copy: bool = typer.Option(
        False,
        "--copy",
        help="Copy files instead of moving them",
    ),
    category: str | None = typer.Option(
        None,
        "--category",
        "-c",
        help="Category hint for track disambiguation (e.g., GT3, NASCAR)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose logging",
    ),
) -> None:
    """Organize existing setup files into iRacing's folder structure.

    Scans a directory for .sto files and reorganizes them into the correct
    iRacing track folder structure. The organizer extracts track information
    from filenames and folder paths, then uses intelligent matching to
    determine the correct iRacing folder location.

    By default, files are moved in place. Use --output to organize to a
    different directory, or --copy to preserve originals.

    Examples:
        # Preview changes without making them
        iracing-setup-downloader organize ~/Documents/iRacing/setups --dry-run

        # Organize files in place
        iracing-setup-downloader organize ~/Documents/iRacing/setups

        # Organize to a different directory (copies files)
        iracing-setup-downloader organize ~/old-setups --output ~/Documents/iRacing/setups

        # Copy files instead of moving
        iracing-setup-downloader organize ~/setups --copy

        # Provide category hint for better track matching
        iracing-setup-downloader organize ~/gt3-setups --category GT3
    """
    setup_logging(verbose)

    try:
        # Load settings
        settings = get_settings()

        # Initialize track matcher
        track_matcher = TrackMatcher(settings.tracks_data_path)
        try:
            track_matcher.load()
        except FileNotFoundError as e:
            console.print(f"[red]Error:[/red] Could not load tracks data: {e}")
            console.print("[yellow]Track data is required for organization.[/yellow]")
            raise typer.Exit(code=1) from e

        # Display configuration
        config_table = Table(
            title="Organization Configuration", show_header=False, box=None
        )
        config_table.add_row("Source:", str(source))
        config_table.add_row(
            "Output:", str(output) if output else "[dim]In place[/dim]"
        )
        config_table.add_row(
            "Mode:", "[cyan]Copy[/cyan]" if copy else "[cyan]Move[/cyan]"
        )
        config_table.add_row("Dry Run:", "[yellow]Yes[/yellow]" if dry_run else "No")
        if category:
            config_table.add_row("Category Hint:", f"[magenta]{category}[/magenta]")
        console.print(config_table)
        console.print()

        # Initialize persistent hash cache
        hash_cache = FileHashCache()
        hash_cache.load()

        # Initialize duplicate detector with persistent cache
        duplicate_detector = DuplicateDetector(hash_cache=hash_cache)

        # Create organizer and run
        organizer = SetupOrganizer(track_matcher, duplicate_detector=duplicate_detector)

        console.print("[bold]Scanning for setup files...[/bold]\n")
        result = organizer.organize(
            source_path=source,
            output_path=output,
            dry_run=dry_run,
            copy=copy,
            category_hint=category,
        )

        # Save hash cache if not dry run
        if not dry_run:
            try:
                hash_cache.save()
            except OSError as e:
                console.print(
                    f"[yellow]Warning:[/yellow] Could not save hash cache: {e}"
                )

        # Display results
        _display_organize_results(result, dry_run, verbose)

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Organization cancelled by user.[/yellow]")
        raise typer.Exit(code=130) from None
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1) from e


def _display_organize_results(
    result: OrganizeResult, dry_run: bool, verbose: bool = False
) -> None:
    """Display organization results.

    Args:
        result: OrganizeResult object
        dry_run: Whether this was a dry run
        verbose: Whether to show detailed file list
    """
    # Check for suspicious car folders
    suspicious_folders = {"setups", "setup", "downloads", "download", "backup", "old"}
    suspicious_actions = [
        a
        for a in result.actions
        if a.will_move and a.car_folder.lower() in suspicious_folders
    ]

    # Summary table
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Label", style="bold")
    summary_table.add_column("Value")

    summary_table.add_row("Total Files:", str(result.total_files))
    if dry_run:
        summary_table.add_row("Would Organize:", f"[cyan]{result.organized}[/cyan]")
    else:
        summary_table.add_row("Organized:", f"[green]{result.organized}[/green]")
    summary_table.add_row("Skipped:", f"[yellow]{result.skipped}[/yellow]")
    if result.failed > 0:
        summary_table.add_row("Failed:", f"[red]{result.failed}[/red]")
    if result.duplicates_found > 0:
        dup_label = "Duplicates Found:" if dry_run else "Duplicates Deleted:"
        dup_count = result.duplicates_found if dry_run else result.duplicates_deleted
        summary_table.add_row(dup_label, f"[magenta]{dup_count}[/magenta]")
        if result.bytes_saved > 0 and not dry_run:
            summary_table.add_row(
                "Space Saved:",
                f"[magenta]{_format_bytes(result.bytes_saved)}[/magenta]",
            )
    if result.companion_files_moved > 0:
        companion_label = "Companion Files:" if dry_run else "Companion Files Moved:"
        summary_table.add_row(
            companion_label, f"[blue]{result.companion_files_moved}[/blue]"
        )

    title = "Organization Results (Dry Run)" if dry_run else "Organization Results"
    console.print(Panel(summary_table, title=title, border_style="green"))

    # Warn about suspicious car folders
    if suspicious_actions:
        console.print()
        console.print(
            "[bold yellow]Warning:[/bold yellow] Detected suspicious car folder names "
            f"(e.g., '{suspicious_actions[0].car_folder}')"
        )
        console.print(
            "  Expected iRacing car folders like 'dalloradw12', 'ferrari296gt3', etc."
        )
        console.print(
            "  If files are not in proper car subfolders, try organizing the parent directory"
        )
        console.print("  or manually move files into correct car folders first.")

    # Show actions if verbose or dry run
    if (verbose or dry_run) and result.actions:
        console.print()

        # Actions that will/did happen
        moves = [a for a in result.actions if a.will_move]
        if moves:
            action_word = "Would move" if dry_run else "Moved"
            console.print(f"[bold]{action_word}:[/bold]")
            for action in moves[:20]:  # Limit to first 20 to avoid spam
                # Show source relative path (car_folder/filename)
                rel_src = f"{action.car_folder}/{action.source.name}"
                # Show destination relative path (car_folder/track/config/filename)
                track_path = action.track_dirpath.replace(chr(92), "/")
                rel_dst = f"{action.car_folder}/{track_path}/{action.source.name}"
                confidence_str = f"[dim]({action.confidence:.0%})[/dim]"
                console.print(
                    f"  [green]•[/green] {rel_src}\n"
                    f"       -> {rel_dst} {confidence_str}"
                )
            if len(moves) > 20:
                console.print(f"  [dim]... and {len(moves) - 20} more[/dim]")

        # Skipped files (only show if verbose)
        if verbose:
            skipped = [a for a in result.actions if a.skipped]
            if skipped:
                console.print()
                console.print("[bold yellow]Skipped:[/bold yellow]")
                for action in skipped[:10]:
                    console.print(
                        f"  [yellow]•[/yellow] {action.source.name}: {action.skip_reason}"
                    )
                if len(skipped) > 10:
                    console.print(f"  [dim]... and {len(skipped) - 10} more[/dim]")

    # Show errors
    errors = [a for a in result.actions if a.error]
    if errors:
        console.print()
        console.print("[bold red]Errors:[/bold red]")
        for action in errors:
            console.print(f"  [red]•[/red] {action.source.name}: {action.error}")


if __name__ == "__main__":
    app()
