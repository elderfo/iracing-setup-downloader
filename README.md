# iRacing Setup Downloader

[![CI](https://github.com/elderfo/iracing-setup-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/elderfo/iracing-setup-downloader/actions/workflows/ci.yml)

A fast, efficient CLI tool for downloading iRacing setups from GoFast and Coach Dave Academy (CDA) with intelligent caching, concurrent downloads, and smart rate limiting. Automatically organizes setups by car and track, skips already-downloaded files, and provides rich progress visualization.

## Features

- **Asynchronous Concurrent Downloads** - Download multiple setups in parallel with configurable concurrency limits (1-20)
- **Smart Rate Limiting** - Configurable random delays between requests to avoid server overload
- **Incremental Updates** - Tracks downloaded setups and skips files that haven't changed
- **Binary Duplicate Detection** - SHA-256 based duplicate detection prevents storing identical files
- **iRacing-Native Folder Structure** - Automatically organizes setups into iRacing's track folder paths so they appear correctly in-game
- **Intelligent Track Matching** - Fuzzy matching with category awareness (GT3 prefers road configs, NASCAR prefers oval configs)
- **Rich Progress Bars** - Visual feedback with download speed, count, and estimated time remaining
- **Retry Logic** - Automatic exponential backoff retry strategy for failed downloads
- **Robust Error Handling** - Detailed error reporting for troubleshooting
- **State Tracking** - Persistent download history prevents redundant downloads across sessions

## Installation

### Prerequisites

- Python 3.11 or higher
- Poetry for package management

### Setup

Clone the repository and install dependencies:

```bash
# Clone the repository
git clone <repository-url>
cd iracing-setup-downloader

# Install dependencies with Poetry
poetry install

# (Optional) Install pre-commit hooks for development
poetry run pre-commit install
```

## Configuration

### Environment Variables

The tool reads configuration from environment variables and a `.env` file. Configuration priority (highest to lowest):

1. Environment variables
2. `.env` file
3. Default values

### Setting Up Configuration

Copy the example configuration file:

```bash
cp .env.example .env
```

Then edit `.env` with your settings:

```bash
# GoFast API Authentication Token (required for GoFast)
GOFAST_TOKEN=your_token_here

# Coach Dave Academy (CDA) Authentication (required for CDA)
CDA_SESSION_ID=your_phpsessid_cookie
CDA_CSRF_TOKEN=your_csrf_token

# Directory for downloaded setups (optional, defaults to ~/Documents/iRacing/setups)
IRACING_SETUPS_PATH=~/Documents/iRacing/setups

# Download concurrency settings (optional)
MAX_CONCURRENT=5        # Number of parallel downloads (1-20)
MIN_DELAY=0.5          # Minimum seconds between downloads
MAX_DELAY=1.5          # Maximum seconds between downloads

# HTTP settings (optional)
TIMEOUT=30             # Connection timeout in seconds
MAX_RETRIES=3          # Retry attempts for failed downloads
```

### Configuration Details

| Variable | Default | Range | Description |
|----------|---------|-------|-------------|
| `GOFAST_TOKEN` | Required for GoFast | - | GoFast API bearer token |
| `CDA_SESSION_ID` | Required for CDA | - | CDA PHPSESSID cookie |
| `CDA_CSRF_TOKEN` | Required for CDA | - | CDA x-elle-csrf-token header |
| `IRACING_SETUPS_PATH` | `~/Documents/iRacing/setups` | - | Directory to save setups |
| `MAX_CONCURRENT` | 5 | 1-20 | Parallel download limit |
| `MIN_DELAY` | 0.5 | >= 0 | Minimum delay between downloads (seconds) |
| `MAX_DELAY` | 1.5 | >= MIN_DELAY | Maximum delay between downloads (seconds) |
| `TIMEOUT` | 30 | >= 1 | HTTP request timeout (seconds) |
| `MAX_RETRIES` | 3 | >= 0 | Failed download retry attempts |
| `TRACKS_DATA_PATH` | (bundled) | - | Custom path to tracks.json for track matching |

### Getting Your GoFast Token

1. Visit GoFast in your browser
2. Open Developer Tools (F12 or Ctrl+Shift+I)
3. Navigate to the Network tab
4. Make a request to any GoFast API endpoint
5. Look for the Authorization header in the request headers
6. Copy the entire value (including "Bearer " prefix if present) to `GOFAST_TOKEN`

### Getting Your CDA Credentials

1. Visit Coach Dave Academy Delta (https://delta.coachdaveacademy.com) in your browser
2. Log in to your CDA account
3. Open Developer Tools (F12 or Ctrl+Shift+I)
4. Navigate to the Application tab (Chrome) or Storage tab (Firefox)
5. Find Cookies for delta.coachdaveacademy.com
6. Copy the `PHPSESSID` cookie value to `CDA_SESSION_ID`
7. Navigate to the Network tab and reload the page
8. Look for any API request and find the `x-elle-csrf-token` header
9. Copy that value to `CDA_CSRF_TOKEN`

**Note:** CDA credentials may expire and need to be refreshed periodically by logging in again.

## Usage

### List Available Setups

View all available setups without downloading:

```bash
# List GoFast setups
poetry run iracing-setup-downloader list gofast

# List CDA setups
poetry run iracing-setup-downloader list cda
```

This displays:
- Setup ID
- Car name
- Track name
- Setup version
- Series category
- Last updated date (GoFast only)

### Download All Setups

Download all available setups that haven't been previously downloaded:

```bash
# Download from GoFast
poetry run iracing-setup-downloader download gofast

# Download from Coach Dave Academy
poetry run iracing-setup-downloader download cda
```

The tool will:
1. Fetch all setups from the provider
2. Check local state to identify new setups
3. Skip setups already downloaded (unless updated)
4. Download new setups with progress visualization

### Dry Run (Preview Downloads)

Preview what would be downloaded without actually downloading:

```bash
# GoFast dry run
poetry run iracing-setup-downloader download gofast --dry-run

# CDA dry run
poetry run iracing-setup-downloader download cda --dry-run
```

Useful for:
- Testing authentication
- Verifying configuration
- Estimating download time
- Checking available setups

### Custom Output Directory

Specify a non-default download directory:

```bash
poetry run iracing-setup-downloader download gofast --output ./my-setups
poetry run iracing-setup-downloader download cda --output ~/Downloads/iRacing
```

### Organize Existing Setups

If you have existing setup files that aren't organized into iRacing's folder structure, you can reorganize them:

```bash
# Preview what would be organized (dry run)
poetry run iracing-setup-downloader organize ~/Documents/iRacing/setups --dry-run

# Organize files in place (moves files)
poetry run iracing-setup-downloader organize ~/Documents/iRacing/setups

# Organize to a different directory
poetry run iracing-setup-downloader organize ~/old-setups --output ~/Documents/iRacing/setups

# Copy files instead of moving
poetry run iracing-setup-downloader organize ~/setups --copy

# Provide category hint for better track matching (e.g., GT3, NASCAR)
poetry run iracing-setup-downloader organize ~/gt3-setups --category GT3
```

The organizer:
- Scans for `.sto` files recursively
- Extracts track information from filenames (supports GoFast naming format)
- Uses intelligent fuzzy matching to find the correct iRacing folder path
- **Moves companion files** - Automatically moves associated `.ld`, `.ldx`, `.olap`, `.blap`, and `.rpy` files with each setup
- **Detects and removes binary duplicates** - Uses SHA-256 hashing to identify files with identical content
- Preserves car folder structure
- Cleans up empty directories after moving files
- Skips files already in the correct location
- Reports space saved from duplicate removal and companion files moved

### View Help

```bash
poetry run iracing-setup-downloader --help
poetry run iracing-setup-downloader download gofast --help
poetry run iracing-setup-downloader download cda --help
poetry run iracing-setup-downloader list gofast --help
poetry run iracing-setup-downloader list cda --help
poetry run iracing-setup-downloader organize --help
```

## Output Structure

Downloaded setups are organized by car and track, matching iRacing's native folder structure:

```
~/Documents/iRacing/setups/
├── ferrari296gt3/
│   ├── jerez/                           # Track folder matching iRacing
│   │   └── moto/                        # Track configuration subfolder
│   │       └── GoFast_IMSA_26S1W8_JerezMoto_Race.sto
│   └── lemans24/
│       └── full/
│           └── GoFast_IMSA_26S1W8_LeMans_Race.sto
├── porsche911gt3r/
│   └── roadatlanta/
│       └── full/
│           └── GoFast_GT_WORLD_26S1W8_RoadAtlanta_Qualifying.sto
└── mclaren720sgt3/
    └── spa/
        └── gp/
            └── GoFast_IMSA_26S1W8_Spa_Race.sto
```

### Track-Based Organization

The downloader automatically matches provider track names to iRacing's internal folder structure using intelligent fuzzy matching. This means:

- **Setups appear in the correct location** - iRacing will find them automatically
- **Category-aware disambiguation** - GT3 setups go to road course configs, NASCAR setups go to oval configs
- **Handles variations** - "Spa-Francorchamps", "Spa", "SPA" all match correctly

If a track cannot be matched (rare), the setup falls back to a flat structure directly in the car folder.

### Duplicate Detection

Both the downloader and organizer include binary duplicate detection using SHA-256 hashing:

**During Downloads:**
- Before extracting a file from a ZIP, the downloader computes its SHA-256 hash
- If an identical file (by content, not name) already exists in the output directory, the file is skipped
- Statistics show how many duplicates were skipped and space saved

**During Organization:**
- Before moving a file, the organizer checks if an identical file exists at the destination or elsewhere in the target directory
- When moving (not copying), duplicate source files are deleted to save space
- The result shows duplicates found, deleted, and bytes saved

This ensures:
- **No redundant storage** - Only one copy of identical content is kept
- **Space efficiency** - Duplicate files are removed during organization
- **Safe operation** - Duplicates are only deleted after verifying an identical copy exists

### Companion Files

When organizing setups, the tool automatically handles companion files that are associated with each `.sto` setup file. These companion files share the same base name but have different extensions:

| Extension | Description |
|-----------|-------------|
| `.ld` | Telemetry/lap data |
| `.ldx` | Telemetry index |
| `.olap` | Lap comparison/overlap data |
| `.blap` | Best lap data |
| `.rpy` | Replay file |

**Behavior:**
- When a `.sto` file is moved, all companion files with matching names are moved to the same destination
- When a `.sto` file is copied, companion files are also copied
- When a duplicate `.sto` is deleted, its companion files are also deleted
- The results summary shows the total number of companion files processed

### Filename Format

**GoFast:** Setups are named: `GoFast_<series>_<season>_<track>_<setup_type>.sto`

**CDA:** Setups are named: `CDA_<series>_<season>_<track>_<setup_type>.sto`

- `series` - Racing series (IMSA, GT World Challenge, etc.)
- `season` - Season identifier (26S1W8 = Season 26, Week 1, Session 8)
- `track` - Track name with spaces replaced by underscores
- `setup_type` - Type of setup (Race, Qualifying, etc.)

## State Management

Downloaded setup information is tracked in:

```
~/.iracing-setup-downloader/state.json
```

This file stores:
- Provider name
- Setup ID
- Last update timestamp
- File path

The state file prevents re-downloading setups that haven't changed. If a setup is updated on GoFast, it will be re-downloaded automatically.

### Hash Cache

File hashes for duplicate detection are cached in:

```
~/.iracing-setup-downloader/hash_cache.json
```

This cache:
- Stores SHA-256 hashes with file modification time and size
- Persists across sessions for faster subsequent runs
- Automatically invalidates entries when files are modified
- Eliminates the need to rehash unchanged files on every run

On subsequent runs, only new or modified files need to be hashed, significantly improving startup time for large collections.

**Important:** Do not manually edit either state.json or hash_cache.json. The tool manages them automatically.

## Development

### Running Tests

Run the test suite:

```bash
poetry run pytest
```

Run tests with coverage report:

```bash
poetry run pytest --cov=iracing_setup_downloader --cov-report=term-missing
```

### Linting and Formatting

Check code style:

```bash
poetry run ruff check .
```

Format code:

```bash
poetry run ruff format .
```

The project includes pre-commit hooks that automatically run formatting and linting before commits.

### Project Structure

```
iracing-setup-downloader/
├── src/iracing_setup_downloader/
│   ├── __init__.py              # Version and metadata
│   ├── cli.py                   # Command-line interface
│   ├── config.py                # Configuration management
│   ├── models.py                # Data models
│   ├── state.py                 # Download state tracking
│   ├── downloader.py            # Download orchestration
│   ├── organizer.py             # Existing file reorganization
│   ├── deduplication.py         # Binary duplicate detection
│   ├── track_matcher.py         # Track name to iRacing path matching
│   ├── data/
│   │   └── tracks.json          # Bundled iRacing track data
│   └── providers/
│       ├── base.py              # Provider interface
│       ├── __init__.py
│       ├── gofast.py            # GoFast provider implementation
│       └── cda.py               # Coach Dave Academy provider
├── tests/                       # Test suite
├── pyproject.toml              # Poetry configuration
├── .env.example                # Configuration template
└── README.md                   # This file
```

### Architecture Overview

**CLI Layer** (`cli.py`) - Command-line interface using Typer

**Configuration** (`config.py`) - Settings management using Pydantic

**Models** (`models.py`) - Data structures for setups and API responses

**Track Matcher** (`track_matcher.py`) - Track name resolution
- Matches provider track names to iRacing folder paths
- Tiered matching: exact, substring, fuzzy (SequenceMatcher)
- Category-aware disambiguation (GT3 vs NASCAR)
- Prefers non-retired track configurations

**Organizer** (`organizer.py`) - Existing file reorganization
- Scans directories for setup files
- Extracts track info from filenames and paths
- Reorganizes files into correct iRacing folder structure
- Supports dry-run, copy, and move modes

**Providers** (`providers/`) - Pluggable provider implementations
- Base interface for consistent provider behavior
- GoFast provider for fetching and downloading setups
- CDA provider for Coach Dave Academy setups

**Downloader** (`downloader.py`) - Download orchestration
- Concurrent download management
- Retry logic with exponential backoff
- Progress visualization with Rich library

**State Management** (`state.py`) - Download history tracking
- Persistent storage of downloaded setups
- Prevents duplicate downloads
- Tracks file paths and modification dates

### Adding New Providers

To add support for another setup provider:

1. Create a new file in `src/iracing_setup_downloader/providers/`
2. Implement the `SetupProvider` base class
3. Override `fetch_setups()` and `download_setup()` methods
4. Add provider-specific configuration to `config.py`
5. Register the provider in the CLI

See `providers/gofast.py` for an example implementation.

## Troubleshooting

### GoFast Authentication Failed

**Error:** "Authentication failed: Invalid or expired token"

**Solution:**
- Verify `GOFAST_TOKEN` is correctly set in `.env`
- Ensure the token includes the "Bearer " prefix if required
- Check that the token hasn't expired
- Regenerate the token from GoFast and update `.env`

### CDA Authentication Failed

**Error:** "Authentication failed: Invalid or expired session"

**Solution:**
- Verify both `CDA_SESSION_ID` and `CDA_CSRF_TOKEN` are set in `.env`
- Log in to CDA Delta again to refresh your session
- Re-extract the PHPSESSID cookie and csrf-token header
- CDA sessions expire after inactivity, so you may need to refresh periodically

### Connection Timeout

**Error:** "Connection timeout" or "Network error while fetching setups"

**Solution:**
- Increase the `TIMEOUT` setting in `.env` (e.g., `TIMEOUT=60`)
- Check internet connection stability
- Try reducing `MAX_CONCURRENT` to lighten server load
- Retry the operation (built-in retry logic will help)

### Disk Space Issues

**Error:** "Failed to write setup file" or similar filesystem errors

**Solution:**
- Verify sufficient disk space available
- Check write permissions on `IRACING_SETUPS_PATH`
- Ensure the directory path is valid and accessible

### Permission Denied

**Error:** "Permission denied" when writing files

**Solution:**
```bash
# Check permissions on setups directory
ls -ld ~/Documents/iRacing/setups

# Grant write permissions if needed
chmod u+w ~/Documents/iRacing/setups
```

### Corrupted State File

**Error:** "Invalid JSON in state file" or state-related errors

**Solution:**
```bash
# Backup current state
cp ~/.iracing-setup-downloader/state.json ~/.iracing-setup-downloader/state.json.bak

# Remove corrupted state (will be recreated)
rm ~/.iracing-setup-downloader/state.json

# Re-run the downloader to rebuild state
poetry run iracing-setup-downloader download gofast
```

### Corrupted Hash Cache

**Error:** "Invalid JSON in cache file" or hash cache-related errors

**Solution:**
```bash
# Remove corrupted cache (will be rebuilt automatically)
rm ~/.iracing-setup-downloader/hash_cache.json

# The cache will be rebuilt on the next run
poetry run iracing-setup-downloader organize ~/Documents/iRacing/setups --dry-run
```

## Performance Tuning

### For Faster Downloads

Increase concurrency and reduce delays:

```bash
MAX_CONCURRENT=15
MIN_DELAY=0.1
MAX_DELAY=0.5
```

**Warning:** Server may rate-limit or block if requests are too aggressive.

### For Server-Friendly Behavior

Decrease concurrency and increase delays:

```bash
MAX_CONCURRENT=2
MIN_DELAY=2.0
MAX_DELAY=4.0
```

### Recommended Defaults

The default settings balance speed and server courtesy:
- `MAX_CONCURRENT=5` - Reasonable parallelism
- `MIN_DELAY=0.5` - Prevents thundering herd
- `MAX_DELAY=1.5` - Natural request spacing

## FAQ

**Q: Will this delete my existing setups?**
A: No. The downloader only adds new or updated setups. The organize command moves files but never deletes them.

**Q: How often should I run the downloader?**
A: Run it as needed to check for setup updates. New setups from your favorite teams are often shared within days.

**Q: Can I run multiple instances?**
A: Not recommended. Multiple instances could conflict on state updates. Run one at a time.

**Q: Are my setups backed up?**
A: Yes, if you store setups in a cloud-synced folder like Google Drive or Dropbox.

**Q: Can I use this on macOS or Linux?**
A: Yes, the tool is cross-platform. The default path uses `~/Documents/iRacing/setups` on all systems.

**Q: What if I interrupt the download?**
A: The downloader will resume from where it stopped on the next run. State tracking prevents duplicate downloads.

**Q: How do I organize setups I already downloaded?**
A: Use `iracing-setup-downloader organize ~/Documents/iRacing/setups --dry-run` to preview, then run without `--dry-run` to reorganize. Use `--copy` if you want to keep originals.

**Q: What happens to files the organizer can't recognize?**
A: They are skipped and left in place. Use `--verbose` to see which files were skipped and why.

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please:

1. Create a feature branch for your changes
2. Add tests for new functionality
3. Ensure linting and formatting pass (`poetry run ruff check .` and `poetry run ruff format --check .`)
4. Ensure all tests pass (`poetry run pytest`)
5. Submit a pull request

All pull requests are automatically validated by CI, which runs linting and tests across Python 3.11, 3.12, and 3.13.

## Support

For issues, questions, or suggestions, please:

1. Check this README and the Troubleshooting section
2. Review existing GitHub issues
3. Create a new issue with details about your problem

Include:
- Python version (`python --version`)
- OS and version
- Steps to reproduce
- Full error messages/logs
- Configuration details (without tokens)
