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

# GoFast-specific download help
iracing-setup-downloader download gofast --help

# List command help
iracing-setup-downloader list --help

# GoFast-specific list help
iracing-setup-downloader list gofast --help
```

## Configuration

The CLI uses environment variables and `.env` files for configuration. Create a `.env` file in your project directory:

```env
# GoFast bearer token (required for GoFast provider)
GOFAST_TOKEN="Bearer your_token_here"

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

### Download All Setups from GoFast

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

### Dry Run

Preview what would be downloaded without actually downloading:

```bash
iracing-setup-downloader download gofast --dry-run
```

### Verbose Logging

Enable detailed logging for debugging:

```bash
iracing-setup-downloader download gofast --verbose
```

### Complete Example

```bash
iracing-setup-downloader download gofast \
  --token "Bearer abc123..." \
  --output ~/Documents/iRacing/setups \
  --max-concurrent 8 \
  --verbose
```

## List Commands

### List Available Setups from GoFast

Basic usage:

```bash
iracing-setup-downloader list gofast
```

With explicit token:

```bash
iracing-setup-downloader list gofast --token "Bearer your_token_here"
```

With verbose logging:

```bash
iracing-setup-downloader list gofast --verbose
```

## Output Structure

Downloaded setups are organized in the following directory structure:

```
<output_path>/
├── <Car Name>/
│   └── <Track Name>/
│       ├── GoFast_IMSA_26S1W8_Watkins_123.sto
│       ├── GoFast_IMSA_26S1W9_Road_456.sto
│       └── ...
└── ...
```

Where:
- `<Car Name>`: Extracted from the setup's download name
- `<Track Name>`: Extracted from the setup's download name
- Filename format: `GoFast_<series>_<season>_<track>_<id>.sto`

## State Management

The CLI maintains download state in `~/.iracing-setup-downloader/state.json` to:
- Track which setups have been downloaded
- Detect when setups have been updated (re-download)
- Skip already-downloaded setups

You can safely delete this file to force a complete re-download.

## Error Handling

### Missing Token

```bash
$ iracing-setup-downloader download gofast
Error: GoFast token is required. Provide via --token flag or GOFAST_TOKEN environment variable.
```

Solution: Provide a token via `--token` flag or set `GOFAST_TOKEN` environment variable.

### Authentication Failed

```
Authentication Error: Authentication failed: Invalid or expired token

Hint: Check that your GoFast token is valid and has the correct permissions.
```

Solution: Verify your token is correct and hasn't expired.

### Network Errors

The CLI includes automatic retry logic with exponential backoff for network errors. You can configure the maximum number of retries with the `MAX_RETRIES` environment variable.

## Advanced Usage

### Using with Shell Scripts

```bash
#!/bin/bash
set -e

# Export token
export GOFAST_TOKEN="Bearer your_token_here"

# Download setups
iracing-setup-downloader download gofast \
  --output ~/Documents/iRacing/setups \
  --max-concurrent 10

echo "Download completed successfully!"
```

### Scheduled Downloads with Cron

Add to your crontab for daily downloads at 2 AM:

```cron
0 2 * * * cd /path/to/project && /path/to/poetry run iracing-setup-downloader download gofast
```

### CI/CD Integration

```yaml
# Example GitHub Actions workflow
name: Download Setups

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:  # Manual trigger

jobs:
  download:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      
      - name: Download setups
        env:
          GOFAST_TOKEN: ${{ secrets.GOFAST_TOKEN }}
        run: |
          poetry run iracing-setup-downloader download gofast
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

Use the list command to verify your token works:

```bash
iracing-setup-downloader list gofast --token "Bearer your_token"
```
