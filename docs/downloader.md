# SetupDownloader Documentation

The `SetupDownloader` class provides robust orchestration for downloading iRacing setups from providers with advanced features including concurrency control, retry logic, state tracking, and progress visualization.

## Features

- **Concurrent Downloads**: Configurable concurrent download limits using asyncio semaphores
- **Random Delays**: Configurable random delays between downloads to avoid overwhelming servers
- **Retry Logic**: Exponential backoff retry mechanism for failed downloads
- **State Tracking**: Integration with `DownloadState` to avoid re-downloading existing setups
- **Progress Visualization**: Rich progress bars showing download status in real-time
- **Graceful Cancellation**: Proper handling of Ctrl+C and task cancellation
- **Dry Run Mode**: Preview what would be downloaded without actually downloading

## Classes

### DownloadResult

A Pydantic model representing the results of a download operation.

**Attributes:**
- `total_available` (int): Total number of setups available from the provider
- `skipped` (int): Number of setups skipped (already downloaded)
- `downloaded` (int): Number of setups successfully downloaded
- `failed` (int): Number of setups that failed to download
- `errors` (list[tuple[str, str]]): List of (setup_id, error_message) tuples for failed downloads

**Methods:**
- `__str__()`: Returns a human-readable summary of the download results

### SetupDownloader

Main orchestrator class for downloading setups.

**Constructor Parameters:**
- `provider` (SetupProvider): The setup provider to download from
- `state` (DownloadState): Download state tracker for avoiding duplicates
- `max_concurrent` (int, default=5): Maximum number of concurrent downloads
- `min_delay` (float, default=0.5): Minimum delay in seconds between downloads
- `max_delay` (float, default=1.5): Maximum delay in seconds between downloads
- `max_retries` (int, default=3): Maximum number of retry attempts for failed downloads

**Methods:**

#### `async download_all(output_path: Path, dry_run: bool = False) -> DownloadResult`

Download all available setups from the provider.

**Parameters:**
- `output_path` (Path): Base directory path for saving downloaded setups
- `dry_run` (bool, default=False): If True, only simulate downloads without actually downloading

**Returns:**
- `DownloadResult`: Object containing download statistics and any errors

**Raises:**
- `ValueError`: If state hasn't been loaded before calling this method
- `aiohttp.ClientError`: If provider communication fails
- `asyncio.CancelledError`: If the download is cancelled by the user

**Behavior:**
1. Fetches all available setups from the provider
2. Filters out already-downloaded setups using state
3. Downloads remaining setups with concurrency control
4. Updates state for successful downloads
5. Returns detailed results

#### `async download_one(setup: SetupRecord, output_path: Path) -> bool`

Download a single setup with retry logic.

**Parameters:**
- `setup` (SetupRecord): Setup to download
- `output_path` (Path): Base output directory

**Returns:**
- `bool`: True if download was successful, False otherwise

**Behavior:**
1. Attempts to download the setup
2. On failure, retries with exponential backoff (1s, 2s, 4s, ...)
3. On success, marks the setup as downloaded in state
4. Returns success/failure status

## Usage Examples

### Basic Usage

```python
import asyncio
from pathlib import Path

from iracing_setup_downloader.downloader import SetupDownloader
from iracing_setup_downloader.providers.gofast import GoFastProvider
from iracing_setup_downloader.state import DownloadState


async def main():
    # Initialize state
    state = DownloadState()
    state.load()

    # Initialize provider
    provider = GoFastProvider(token="your-api-token")

    try:
        # Create downloader
        downloader = SetupDownloader(
            provider=provider,
            state=state,
        )

        # Download all setups
        result = await downloader.download_all(Path("./setups"))

        # Print results
        print(f"Downloaded: {result.downloaded}")
        print(f"Skipped: {result.skipped}")
        print(f"Failed: {result.failed}")

        # Save state
        state.save()

    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
```

### Custom Configuration

```python
downloader = SetupDownloader(
    provider=provider,
    state=state,
    max_concurrent=3,      # Limit to 3 concurrent downloads
    min_delay=1.0,         # Wait at least 1 second between downloads
    max_delay=2.0,         # Wait at most 2 seconds between downloads
    max_retries=5,         # Retry failed downloads up to 5 times
)
```

### Dry Run Mode

```python
# Preview what would be downloaded
result = await downloader.download_all(
    Path("./setups"),
    dry_run=True
)

print(f"Would download {result.total_available - result.skipped} setups")
```

### Handling Cancellation

```python
try:
    result = await downloader.download_all(Path("./setups"))
except asyncio.CancelledError:
    print("Download was cancelled")
    # State is automatically saved for completed downloads
```

### Error Handling

```python
result = await downloader.download_all(Path("./setups"))

if result.failed > 0:
    print(f"\n{result.failed} downloads failed:")
    for setup_id, error in result.errors:
        print(f"  Setup {setup_id}: {error}")
```

## Implementation Details

### Concurrency Control

The downloader uses `asyncio.Semaphore` to limit concurrent downloads. This prevents overwhelming the provider's servers and manages local resource usage.

```python
semaphore = asyncio.Semaphore(max_concurrent)

async with semaphore:
    # Download happens here
    ...
```

### Random Delays

Random delays between `min_delay` and `max_delay` are applied before each download to distribute load and appear more natural to rate limiting systems.

```python
delay = random.uniform(min_delay, max_delay)
await asyncio.sleep(delay)
```

### Retry Logic

Failed downloads are retried with exponential backoff:
- Attempt 1: No delay
- Attempt 2: 1 second delay
- Attempt 3: 2 second delay
- Attempt 4: 4 second delay
- etc.

```python
backoff = 2 ** (retry_count - 1)
await asyncio.sleep(backoff)
```

### Progress Tracking

The downloader uses the `rich` library to display a real-time progress bar showing:
- Download task description
- Progress bar
- Completed/total count
- Transfer information
- Estimated time remaining

### State Management

The downloader integrates with `DownloadState` to:
1. Check if setups are already downloaded before fetching
2. Verify files still exist on disk
3. Check if setups have been updated since last download
4. Mark successful downloads to avoid re-downloading

## Performance Considerations

### Memory Usage

- Downloads are streamed and written directly to disk
- State is loaded once at startup and saved periodically
- Progress tracking uses minimal memory

### Network Usage

- Concurrent downloads are limited by `max_concurrent`
- Random delays prevent burst traffic
- Failed downloads are retried automatically
- Existing files are skipped to save bandwidth

### Disk I/O

- Output directories are created as needed
- Files are written atomically
- State file is written in JSON format with pretty printing

## Error Handling

The downloader handles several types of errors:

1. **Network Errors**: Automatically retried with backoff
2. **File System Errors**: Logged and reported in results
3. **Provider Errors**: Caught and included in error list
4. **Cancellation**: Gracefully stops and cleans up

## Testing

The downloader includes comprehensive tests covering:

- Successful downloads
- Skipping existing setups
- Dry run mode
- Retry logic
- Concurrency limits
- Cancellation handling
- State management
- Error scenarios

Run tests with:

```bash
poetry run pytest tests/test_downloader.py -v
```

Check coverage with:

```bash
poetry run pytest tests/test_downloader.py --cov=iracing_setup_downloader.downloader --cov-report=term-missing
```

## Future Enhancements

Potential improvements for future versions:

- [ ] Resume interrupted downloads
- [ ] Parallel verification of existing files
- [ ] Download prioritization
- [ ] Bandwidth throttling
- [ ] Download scheduling
- [ ] Webhook notifications on completion
- [ ] Metrics collection and reporting
- [ ] Custom retry strategies
