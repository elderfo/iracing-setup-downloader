# CLI Quick Reference

## Basic Commands

```bash
# Show version
iracing-setup-downloader --version

# Show help
iracing-setup-downloader --help
```

## Download Commands

```bash
# Download all setups (uses .env or environment variables)
iracing-setup-downloader download gofast

# Download with explicit token
iracing-setup-downloader download gofast --token "Bearer YOUR_TOKEN"

# Download to custom directory
iracing-setup-downloader download gofast --output ~/custom/path

# Download with custom concurrency
iracing-setup-downloader download gofast --max-concurrent 10

# Dry run (preview without downloading)
iracing-setup-downloader download gofast --dry-run

# Verbose mode (detailed logging)
iracing-setup-downloader download gofast --verbose

# Complete example
iracing-setup-downloader download gofast \
  --token "Bearer YOUR_TOKEN" \
  --output ~/Documents/iRacing/setups \
  --max-concurrent 8 \
  --verbose
```

## List Commands

```bash
# List all available setups
iracing-setup-downloader list gofast

# List with explicit token
iracing-setup-downloader list gofast --token "Bearer YOUR_TOKEN"

# List with verbose logging
iracing-setup-downloader list gofast --verbose
```

## Environment Variables

```bash
# Set in .env file or export in shell
GOFAST_TOKEN="Bearer YOUR_TOKEN"
OUTPUT_PATH="~/Documents/iRacing/setups"
MAX_CONCURRENT=5
MIN_DELAY=0.5
MAX_DELAY=1.5
TIMEOUT=30
MAX_RETRIES=3
```

## Common Workflows

### First Time Setup
```bash
# 1. Create .env file with your token
echo 'GOFAST_TOKEN="Bearer YOUR_TOKEN"' > .env

# 2. List available setups
iracing-setup-downloader list gofast

# 3. Download with dry run to preview
iracing-setup-downloader download gofast --dry-run

# 4. Download for real
iracing-setup-downloader download gofast
```

### Regular Updates
```bash
# Download any new or updated setups
iracing-setup-downloader download gofast
```

### Troubleshooting
```bash
# Enable verbose logging
iracing-setup-downloader download gofast --verbose

# Clear state (force re-download)
rm ~/.iracing-setup-downloader/state.json

# Test token
iracing-setup-downloader list gofast
```

## Exit Codes

- `0`: Success
- `1`: General error (missing token, API error, etc.)
- `130`: Cancelled by user (Ctrl+C)

## Output Directory Structure

```
<output_path>/
├── <Car Name>/
│   └── <Track Name>/
│       └── GoFast_<series>_<season>_<track>_<id>.sto
```

## State File Location

```
~/.iracing-setup-downloader/state.json
```
