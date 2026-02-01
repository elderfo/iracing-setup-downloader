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
from iracing_setup_downloader.downloader import SetupDownloader
from iracing_setup_downloader.providers import GoFastProvider
from iracing_setup_downloader.providers.gofast import (
    GoFastAuthenticationError,
    GoFastProviderError,
)
from iracing_setup_downloader.state import DownloadState

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
    """
    provider = GoFastProvider(token=token)

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

        # Save state
        if not dry_run:
            state.save()

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


if __name__ == "__main__":
    app()
