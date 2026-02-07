# CLI Implementation Summary

## Overview

The CLI for iracing-setup-downloader is built with Typer and Rich, supporting three setup providers: GoFast, Coach Dave Academy (CDA), and Track Titan.

## File Structure

```
src/iracing_setup_downloader/
├── cli.py                 # Main CLI implementation
├── config.py              # Configuration management
├── deduplication.py       # Setup deduplication logic
├── downloader.py          # Download orchestration
├── models.py              # Data models (Setup, SetupRecord, CDASetupInfo, TracKTitanSetupInfo)
├── organizer.py           # File organization
├── state.py               # State management
├── track_matcher.py       # Track name matching
├── utils.py               # Shared utilities
└── providers/
    ├── __init__.py
    ├── base.py            # Provider interface
    ├── gofast.py          # GoFast provider
    ├── cda.py             # Coach Dave Academy provider
    └── tracktitan.py      # Track Titan provider

tests/
├── conftest.py            # Shared fixtures
├── test_cda_provider.py   # CDA provider tests
├── test_cli.py            # CLI tests
├── test_config.py         # Configuration tests
├── test_deduplication.py  # Deduplication tests
├── test_downloader.py     # Downloader tests
├── test_gofast_provider.py # GoFast provider tests
├── test_models.py         # Data model tests
├── test_organizer.py      # Organizer tests
├── test_state.py          # State management tests
├── test_track_matcher.py  # Track matcher tests
├── test_tracktitan_provider.py # Track Titan provider tests
└── test_utils.py          # Utility tests

docs/
├── CLI_USAGE.md           # User documentation
├── CLI_QUICK_REFERENCE.md # Quick reference card
├── CLI_IMPLEMENTATION.md  # This file
└── downloader.md          # Downloader module docs
```

## Commands

### Main Command
```bash
iracing-setup-downloader [OPTIONS] COMMAND
```
Options: `--version, -v` | `--help`

### Download Commands
```bash
iracing-setup-downloader download gofast [OPTIONS]
iracing-setup-downloader download cda [OPTIONS]
iracing-setup-downloader download tracktitan [OPTIONS]
```

#### GoFast Options
- `--token, -t TEXT`: GoFast bearer token [env: `GOFAST_TOKEN`]
- `--output, -o PATH`: Output directory [env: `OUTPUT_PATH`]
- `--max-concurrent, -c INTEGER`: Max parallel downloads (1-20)
- `--dry-run`: Preview without downloading
- `--verbose`: Enable verbose logging

#### CDA Options
- `--session-id, -s TEXT`: PHPSESSID cookie [env: `CDA_SESSION_ID`]
- `--csrf-token, -c TEXT`: x-elle-csrf-token header [env: `CDA_CSRF_TOKEN`]
- `--output, -o PATH`: Output directory [env: `OUTPUT_PATH`]
- `--max-concurrent INTEGER`: Max parallel downloads (1-20)
- `--dry-run`: Preview without downloading
- `--verbose`: Enable verbose logging

#### Track Titan Options
- `--access-token, -t TEXT`: AWS Cognito access token [env: `TT_ACCESS_TOKEN`]
- `--id-token TEXT`: AWS Cognito ID token for downloads [env: `TT_ID_TOKEN`]
- `--user-id, -u TEXT`: User UUID [env: `TT_USER_ID`]
- `--output, -o PATH`: Output directory [env: `OUTPUT_PATH`]
- `--max-concurrent INTEGER`: Max parallel downloads (1-20)
- `--limit, -l INTEGER`: Max number of new setups to download
- `--dry-run`: Preview without downloading
- `--verbose`: Enable verbose logging

### List Commands
```bash
iracing-setup-downloader list gofast [OPTIONS]
iracing-setup-downloader list cda [OPTIONS]
iracing-setup-downloader list tracktitan [OPTIONS]
```
Each list command accepts the same authentication options as its download counterpart (excluding download-specific options like `--output`, `--max-concurrent`, `--limit`, and `--dry-run`).

## Key Components

### Configuration (`config.py`)
- Environment variable support via `.env` files using Pydantic settings
- CLI argument overrides for all settings
- Alias support (e.g., `GOFAST_TOKEN` or `TOKEN`)
- Configuration priority: CLI args > env vars > `.env` file > defaults

### Providers (`providers/`)
Each provider implements the `SetupProvider` base class:
- **GoFast**: Token-based auth, downloads `.sto` setup files
- **CDA**: Session ID + CSRF token auth, downloads `.zip` bundles
- **Track Titan**: Dual AWS Cognito token auth (access token for API, ID token for downloads), downloads `.zip` files via pre-signed CloudFront URLs

### Download Features
- Concurrent downloads with configurable limits
- State tracking to skip already-downloaded setups
- Retry logic with exponential backoff
- Progress bars using Rich
- Dry run mode
- Deduplication across providers

### State Management (`state.py`)
- JSON file at `~/.iracing-setup-downloader/state.json`
- Tracks downloaded setups by provider and unique ID
- Detects updates via timestamps
- Safe to delete for a fresh re-download

## Testing

- **409 total tests** across all modules
- **Pytest** with async support (`pytest-asyncio`)
- **Mock-based testing** for external API dependencies
- **Pre-commit hooks**: ruff linting, ruff formatting, pytest

## Design Decisions

### Typer Framework
Modern, type-safe CLI framework with automatic help generation and built-in support for environment variable defaults.

### Rich for Output
Beautiful terminal output with tables, progress bars, panels, and colored text.

### Async/Await Pattern
Non-blocking I/O for efficient concurrent downloads using aiohttp.

### Dual-Token Auth (Track Titan)
Track Titan uses separate AWS Cognito tokens: an access token for v2 API calls and an ID token for v1 download calls. The ID token is optional and falls back to the access token for backward compatibility.

### Configuration Priority
1. CLI arguments (highest)
2. Environment variables
3. `.env` file
4. Default values (lowest)

## Adding New Providers

1. Create a provider class in `providers/` extending `SetupProvider`
2. Add a model in `models.py` if needed
3. Add download and list commands in `cli.py`
4. Add config fields in `config.py`
5. Add tests
6. Update documentation

## References

- [Typer Documentation](https://typer.tiangolo.com/)
- [Rich Documentation](https://rich.readthedocs.io/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [aiohttp Documentation](https://docs.aiohttp.org/)
