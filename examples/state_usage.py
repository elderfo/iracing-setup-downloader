#!/usr/bin/env python3
"""Example demonstrating how to use the DownloadState class."""

from datetime import datetime
from pathlib import Path

from iracing_setup_downloader.state import DownloadState


def basic_usage_example():
    """Demonstrate basic usage of DownloadState."""
    print("=== Basic Usage Example ===\n")

    # Create a state manager with a custom path (use temp for this example)
    state_file = Path("/tmp/example_state.json")
    state = DownloadState(state_file=state_file)

    # Load the state (creates empty state if file doesn't exist)
    state.load()

    # Check if a setup has been downloaded
    setup_id = 12345
    provider = "gofast"
    updated_date = datetime(2024, 1, 15, 10, 30, 0)
    file_path = Path("/tmp/example_setup.sto")

    if state.is_downloaded(provider, setup_id, updated_date, file_path):
        print(f"Setup {setup_id} is already downloaded")
    else:
        print(f"Setup {setup_id} needs to be downloaded")

        # Simulate downloading the file
        file_path.write_text("Example setup file content")

        # Mark it as downloaded
        state.mark_downloaded(provider, setup_id, updated_date, file_path)
        print(f"Marked setup {setup_id} as downloaded")

    # Save the state to disk
    state.save()

    # Get statistics
    stats = state.get_stats()
    print(f"\nDownload statistics: {stats}")

    # Cleanup
    state_file.unlink(missing_ok=True)
    file_path.unlink(missing_ok=True)


def context_manager_example():
    """Demonstrate using DownloadState as a context manager."""
    print("\n=== Context Manager Example ===\n")

    state_file = Path("/tmp/example_state_ctx.json")
    file_path = Path("/tmp/example_setup_ctx.sto")
    file_path.write_text("Example setup file content")

    # Using context manager automatically loads on enter and saves on exit
    with DownloadState(state_file=state_file) as state:
        state.mark_downloaded(
            provider="gofast",
            setup_id=54321,
            updated_date=datetime.now(),
            file_path=file_path,
        )
        print("Marked setup as downloaded (will auto-save on exit)")

    # State is automatically saved when exiting the context
    print("State saved automatically")

    # Verify the state persisted
    with DownloadState(state_file=state_file) as state:
        stats = state.get_stats()
        print(f"Download statistics: {stats}")

    # Cleanup
    state_file.unlink(missing_ok=True)
    file_path.unlink(missing_ok=True)


def auto_save_example():
    """Demonstrate auto-save feature."""
    print("\n=== Auto-Save Example ===\n")

    state_file = Path("/tmp/example_state_autosave.json")

    # Enable auto-save
    state = DownloadState(state_file=state_file, auto_save=True)
    state.load()

    file_path = Path("/tmp/example_setup_autosave.sto")
    file_path.write_text("Example setup file content")

    # With auto_save=True, each mark_downloaded automatically saves
    state.mark_downloaded(
        provider="gofast",
        setup_id=99999,
        updated_date=datetime.now(),
        file_path=file_path,
    )
    print("Setup marked as downloaded (automatically saved)")

    # No need to call save() manually
    print(f"State file exists: {state_file.exists()}")

    # Cleanup
    state_file.unlink(missing_ok=True)
    file_path.unlink(missing_ok=True)


def multiple_providers_example():
    """Demonstrate tracking downloads from multiple providers."""
    print("\n=== Multiple Providers Example ===\n")

    state_file = Path("/tmp/example_state_multi.json")

    with DownloadState(state_file=state_file) as state:
        # Add setups from different providers
        providers = ["gofast", "craigs", "coach-dave"]
        for i, provider in enumerate(providers):
            for setup_num in range(1, 4):  # Add 3 setups per provider
                file_path = Path(f"/tmp/{provider}_{setup_num}.sto")
                file_path.write_text(f"Setup {setup_num} from {provider}")

                state.mark_downloaded(
                    provider=provider,
                    setup_id=i * 1000 + setup_num,
                    updated_date=datetime.now(),
                    file_path=file_path,
                )

        # Get statistics per provider
        stats = state.get_stats()
        print("Download statistics by provider:")
        for provider, count in stats.items():
            print(f"  {provider}: {count} setups")

    # Cleanup
    state_file.unlink(missing_ok=True)
    for provider in providers:
        for setup_num in range(1, 4):
            file_path = Path(f"/tmp/{provider}_{setup_num}.sto")
            file_path.unlink(missing_ok=True)


def update_detection_example():
    """Demonstrate detecting when a setup has been updated."""
    print("\n=== Update Detection Example ===\n")

    state_file = Path("/tmp/example_state_update.json")
    file_path = Path("/tmp/example_setup_update.sto")
    file_path.write_text("Original setup content")

    with DownloadState(state_file=state_file) as state:
        # Download setup with original date
        original_date = datetime(2024, 1, 15, 10, 0, 0)
        state.mark_downloaded(
            provider="gofast",
            setup_id=777,
            updated_date=original_date,
            file_path=file_path,
        )
        print(f"Setup downloaded at {original_date}")

    # Check if setup needs re-download with newer date
    with DownloadState(state_file=state_file) as state:
        updated_date = datetime(2024, 1, 16, 12, 0, 0)

        if state.is_downloaded("gofast", 777, updated_date, file_path):
            print("Setup is up to date")
        else:
            print("Setup has been updated, needs re-download")
            # Re-download and update the state
            file_path.write_text("Updated setup content")
            state.mark_downloaded("gofast", 777, updated_date, file_path)
            print(f"Re-downloaded setup with new date {updated_date}")

    # Cleanup
    state_file.unlink(missing_ok=True)
    file_path.unlink(missing_ok=True)


if __name__ == "__main__":
    basic_usage_example()
    context_manager_example()
    auto_save_example()
    multiple_providers_example()
    update_detection_example()

    print("\n=== All examples completed successfully ===")
