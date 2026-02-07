# CLI Usage Guide

This guide provides examples and documentation for using the iracing-setup-downloader CLI.

## Installation

The CLI is automatically installed when you install the package:

```bash
poetry install
```

## Basic Commands

### Version

Check the installed version:

```bash
iracing-setup-downloader --version
```

### Help

Get help for any command:

```bash
# General help
iracing-setup-downloader --help

# Download command help
iracing-setup-downloader download --help

# Provider-specific download help
iracing-setup-downloader download gofast --help
iracing-setup-downloader download cda --help
iracing-setup-downloader download tracktitan --help

# List command help
iracing-setup-downloader list --help

# Provider-specific list help
iracing-setup-downloader list gofast --help
iracing-setup-downloader list cda --help
iracing-setup-downloader list tracktitan --help
```

## Configuration

The CLI uses environment variables and `.env` files for configuration. Create a `.env` file in your project directory:

```env
# GoFast bearer token (required for GoFast provider)
GOFAST_TOKEN="Bearer your_token_here"

# Coach Dave Academy (CDA) credentials (required for CDA provider)
CDA_SESSION_ID=your_phpsessid_cookie
CDA_CSRF_TOKEN=your_csrf_token

# Track Titan credentials (required for Track Titan provider)
TT_ACCESS_TOKEN=your_cognito_access_token
TT_ID_TOKEN=your_cognito_id_token
TT_USER_ID=your_user_uuid

# Output directory for downloaded setups (optional)
OUTPUT_PATH="~/Documents/iRacing/setups"

# Maximum concurrent downloads (optional, default: 5)
MAX_CONCURRENT=5

# Delay range between downloads in seconds (optional)
MIN_DELAY=0.5
MAX_DELAY=1.5

# HTTP timeout in seconds (optional, default: 30)
TIMEOUT=30

# Maximum retry attempts (optional, default: 3)
MAX_RETRIES=3
```

## Download Commands

### GoFast

Basic usage:

```bash
iracing-setup-downloader download gofast
```

With explicit token:

```bash
iracing-setup-downloader download gofast --token "Bearer your_token_here"
```

With custom output directory:

```bash
iracing-setup-downloader download gofast --output ~/custom/path
```

With custom concurrency:

```bash
iracing-setup-downloader download gofast --max-concurrent 10
```

Complete example:

```bash
iracing-setup-downloader download gofast \
  --token "Bearer abc123..." \
  --output ~/Documents/iRacing/setups \
  --max-concurrent 8 \
  --verbose
```

### Coach Dave Academy (CDA)

Basic usage (reads credentials from `.env`):

```bash
iracing-setup-downloader download cda
```

With explicit credentials:

```bash
iracing-setup-downloader download cda \
  --session-id "your_phpsessid" \
  --csrf-token "your_csrf_token"
```

Complete example:

```bash
iracing-setup-downloader download cda \
  --session-id "abc123" \
  --csrf-token "xyz789" \
  --output ~/Documents/iRacing/setups \
  --max-concurrent 5 \
  --verbose
```

### Track Titan

Basic usage (reads credentials from `.env`):

```bash
iracing-setup-downloader download tracktitan
```

With explicit credentials:

```bash
iracing-setup-downloader download tracktitan \
  --access-token "eyJ..." \
  --id-token "eyJ..." \
  --user-id "896a9f9d-ee3e-40eb-b9b6-2279c8db7302"
```

With download limit (useful for testing or incremental downloads):

```bash
iracing-setup-downloader download tracktitan --limit 5
```

Complete example:

```bash
iracing-setup-downloader download tracktitan \
  --access-token "eyJ..." \
  --id-token "eyJ..." \
  --user-id "abc-123" \
  --output ~/Documents/iRacing/setups \
  --max-concurrent 5 \
  --limit 10 \
  --verbose
```

> **Note:** Track Titan uses two separate AWS Cognito tokens. The **access token** is used for API calls (listing setups), while the **ID token** is used for download requests. If the ID token is not provided, the access token is used for both.

### Common Options

These options are available for all `download` subcommands:

- `--output, -o PATH`: Output directory (overrides `OUTPUT_PATH` env var)
- `--max-concurrent INTEGER`: Max parallel downloads, 1-20 (default: 5)
- `--dry-run`: Preview what would be downloaded without downloading
- `--verbose`: Enable detailed logging

## List Commands

### List Setups from GoFast

```bash
iracing-setup-downloader list gofast
iracing-setup-downloader list gofast --token "Bearer your_token" --verbose
```

### List Setups from CDA

```bash
iracing-setup-downloader list cda
iracing-setup-downloader list cda --session-id "abc123" --csrf-token "xyz789"
```

### List Setups from Track Titan

```bash
iracing-setup-downloader list tracktitan
iracing-setup-downloader list tracktitan --access-token "eyJ..." --user-id "abc-123"
```

> **Note:** The `list tracktitan` command only uses the access token (v2 API); an ID token is not needed.

## Output Structure

Downloaded setups are organized in the following directory structure:

```
<output_path>/
├── <Car Name>/
│   └── <Track Name>/
│       ├── GoFast_IMSA_26S1W8_Watkins_123.sto
│       ├── CDA_IMSA_W8_watkins-glen.zip
│       ├── TrackTitan_mx5_cup_bathurst_abc123.zip
│       └── ...
└── ...
```

Where:
- `<Car Name>`: Extracted from the setup metadata
- `<Track Name>`: Extracted from the setup metadata
- Filename format varies by provider

## State Management

The CLI maintains download state in `~/.iracing-setup-downloader/state.json` to:
- Track which setups have been downloaded
- Detect when setups have been updated (re-download)
- Skip already-downloaded setups

You can safely delete this file to force a complete re-download.

## Error Handling

### Missing Credentials

Each provider requires specific credentials. If they are missing, the CLI will show an error with instructions:

```bash
$ iracing-setup-downloader download gofast
Error: GoFast token is required. Provide via --token flag or GOFAST_TOKEN environment variable.
```

### Authentication Failed

```
Authentication Error: Authentication failed: Invalid or expired token
```

Solution: Verify your credentials are correct and haven't expired.

### Network Errors

The CLI includes automatic retry logic with exponential backoff for network errors. You can configure the maximum number of retries with the `MAX_RETRIES` environment variable.

## Advanced Usage

### Using with Shell Scripts

```bash
#!/bin/bash
set -e

# Export credentials
export GOFAST_TOKEN="Bearer your_token_here"
export CDA_SESSION_ID="your_session_id"
export CDA_CSRF_TOKEN="your_csrf_token"
export TT_ACCESS_TOKEN="your_access_token"
export TT_ID_TOKEN="your_id_token"
export TT_USER_ID="your_user_id"

# Download from all providers
iracing-setup-downloader download gofast --output ~/Documents/iRacing/setups
iracing-setup-downloader download cda --output ~/Documents/iRacing/setups
iracing-setup-downloader download tracktitan --output ~/Documents/iRacing/setups

echo "All downloads completed!"
```

### Scheduled Downloads with Cron

Add to your crontab for daily downloads at 2 AM:

```cron
0 2 * * * cd /path/to/project && /path/to/poetry run iracing-setup-downloader download gofast
```

## Troubleshooting

### Check Version

```bash
iracing-setup-downloader --version
```

### Enable Verbose Logging

Add `--verbose` to any command to see detailed logs:

```bash
iracing-setup-downloader download gofast --verbose
```

### Clear State

If you suspect state corruption, delete the state file:

```bash
rm ~/.iracing-setup-downloader/state.json
```

### Test Connection

Use the list command to verify your credentials work:

```bash
iracing-setup-downloader list gofast
iracing-setup-downloader list cda
iracing-setup-downloader list tracktitan
```
