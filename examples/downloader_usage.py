"""Example usage of the SetupDownloader class.

This example demonstrates how to use the SetupDownloader to download
setups from a provider with proper state management and error handling.
"""

import asyncio
import logging

from iracing_setup_downloader.config import get_settings
from iracing_setup_downloader.downloader import SetupDownloader
from iracing_setup_downloader.providers.gofast import GoFastProvider
from iracing_setup_downloader.state import DownloadState


async def main() -> None:
    """Main example function."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load configuration
    settings = get_settings()

    # Initialize state manager
    state = DownloadState()
    state.load()

    # Initialize provider
    provider = GoFastProvider(token=settings.gofast_token)

    try:
        # Create downloader with custom settings
        downloader = SetupDownloader(
            provider=provider,
            state=state,
            max_concurrent=settings.max_concurrent,
            min_delay=settings.min_delay,
            max_delay=settings.max_delay,
            max_retries=settings.max_retries,
        )

        # Download all setups
        output_path = settings.output_path
        print(f"Downloading setups to {output_path}")

        # Perform dry run first to see what would be downloaded
        dry_result = await downloader.download_all(output_path, dry_run=True)
        print("\nDry run results:")
        print(f"  Total available: {dry_result.total_available}")
        print(f"  Already downloaded: {dry_result.skipped}")
        print(f"  To download: {dry_result.total_available - dry_result.skipped}")

        # Ask for confirmation
        if dry_result.total_available - dry_result.skipped > 0:
            response = input("\nProceed with download? (y/n): ")
            if response.lower() != "y":
                print("Download cancelled")
                return

            # Perform actual download
            result = await downloader.download_all(output_path)

            # Print results
            print("\nDownload completed!")
            print(result)

            # Save state
            state.save()

            # Print statistics
            stats = state.get_stats()
            print("\nTotal downloads by provider:")
            for provider_name, count in stats.items():
                print(f"  {provider_name}: {count}")

    except KeyboardInterrupt:
        print("\nDownload interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        raise
    finally:
        # Clean up provider resources
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
