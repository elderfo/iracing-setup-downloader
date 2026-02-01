"""Example demonstrating CLI usage patterns.

This example shows how to use the CLI programmatically using subprocess,
as well as how to use the underlying modules directly for more control.
"""

import asyncio
import subprocess

from iracing_setup_downloader.config import get_settings
from iracing_setup_downloader.downloader import SetupDownloader
from iracing_setup_downloader.providers import GoFastProvider
from iracing_setup_downloader.state import DownloadState


def run_cli_command(command: list[str]) -> subprocess.CompletedProcess:
    """Run a CLI command and return the result.

    Args:
        command: List of command arguments

    Returns:
        CompletedProcess instance with the result
    """
    full_command = ["poetry", "run", "iracing-setup-downloader"] + command
    return subprocess.run(full_command, capture_output=True, text=True, check=False)


def example_cli_usage():
    """Demonstrate using the CLI via subprocess."""
    print("=== CLI Usage via Subprocess ===\n")

    # 1. Check version
    print("1. Checking version:")
    result = run_cli_command(["--version"])
    print(result.stdout)

    # 2. List setups (requires token)
    print("2. Listing setups (requires GOFAST_TOKEN env var):")
    result = run_cli_command(["list", "gofast"])
    print(result.stdout if result.returncode == 0 else result.stderr)

    # 3. Download with dry run
    print("\n3. Downloading with dry run (requires GOFAST_TOKEN env var):")
    result = run_cli_command(["download", "gofast", "--dry-run"])
    print(result.stdout if result.returncode == 0 else result.stderr)


async def example_programmatic_usage():
    """Demonstrate using the modules directly (more control)."""
    print("\n=== Programmatic Usage ===\n")

    # Load settings
    settings = get_settings()

    if not settings.token:
        print("Error: GOFAST_TOKEN environment variable not set")
        return

    # Ensure token has Bearer prefix
    if not settings.token.startswith("Bearer "):
        settings.token = f"Bearer {settings.token}"

    # Create provider
    provider = GoFastProvider(token=settings.token)

    try:
        # List available setups
        print("1. Fetching available setups:")
        setups = await provider.fetch_setups()
        print(f"   Found {len(setups)} setups")

        if setups:
            # Show first 5
            print("\n   First 5 setups:")
            for setup in setups[:5]:
                print(f"   - {setup.id}: {setup.car} @ {setup.track}")

        # Download with state management
        print("\n2. Downloading setups:")
        state = DownloadState()
        state.load()

        downloader = SetupDownloader(
            provider=provider,
            state=state,
            max_concurrent=settings.max_concurrent,
            min_delay=settings.min_delay,
            max_delay=settings.max_delay,
            max_retries=settings.max_retries,
        )

        # Dry run
        result = await downloader.download_all(settings.output_path, dry_run=True)
        print(f"   Would download {result.total_available - result.skipped} setups")
        print(f"   Would skip {result.skipped} already-downloaded setups")

        # Show state statistics
        stats = state.get_stats()
        print("\n3. State statistics:")
        for provider_name, count in stats.items():
            print(f"   {provider_name}: {count} downloaded")

    finally:
        await provider.close()


def main():
    """Run all examples."""
    # CLI examples
    example_cli_usage()

    # Programmatic examples
    print("\nRunning programmatic examples...")
    asyncio.run(example_programmatic_usage())

    print("\n=== Examples Complete ===")


if __name__ == "__main__":
    main()
