# CLI Quick Reference

## Basic Commands

```bash
# Show version
iracing-setup-downloader --version

# Show help
iracing-setup-downloader --help
```

## Download Commands

### GoFast

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
```

### Coach Dave Academy (CDA)

```bash
# Download all setups
iracing-setup-downloader download cda

# Download with explicit credentials
iracing-setup-downloader download cda \
  --session-id "YOUR_PHPSESSID" \
  --csrf-token "YOUR_CSRF_TOKEN"

# Dry run
iracing-setup-downloader download cda --dry-run
```

### Track Titan

```bash
# Download all setups
iracing-setup-downloader download tracktitan

# Download with explicit credentials
iracing-setup-downloader download tracktitan \
  --access-token "eyJ..." \
  --id-token "eyJ..." \
  --user-id "YOUR_UUID"

# Limit number of new downloads
iracing-setup-downloader download tracktitan --limit 5

# Dry run
iracing-setup-downloader download tracktitan --dry-run
```

## List Commands

```bash
# List available setups by provider
iracing-setup-downloader list gofast
iracing-setup-downloader list cda
iracing-setup-downloader list tracktitan

# With explicit credentials
iracing-setup-downloader list gofast --token "Bearer YOUR_TOKEN"
iracing-setup-downloader list cda --session-id "ID" --csrf-token "TOKEN"
iracing-setup-downloader list tracktitan --access-token "eyJ..." --user-id "UUID"

# With verbose logging
iracing-setup-downloader list gofast --verbose
```

## Environment Variables

```bash
# GoFast
GOFAST_TOKEN="Bearer YOUR_TOKEN"

# Coach Dave Academy
CDA_SESSION_ID=your_phpsessid_cookie
CDA_CSRF_TOKEN=your_csrf_token

# Track Titan
TT_ACCESS_TOKEN=your_cognito_access_token
TT_ID_TOKEN=your_cognito_id_token
TT_USER_ID=your_user_uuid

# Shared settings
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
# 1. Copy and configure .env file
cp .env.example .env
# Edit .env with your credentials

# 2. List available setups
iracing-setup-downloader list gofast

# 3. Preview downloads
iracing-setup-downloader download gofast --dry-run

# 4. Download for real
iracing-setup-downloader download gofast
```

### Regular Updates
```bash
# Download new/updated setups (state tracking skips already-downloaded)
iracing-setup-downloader download gofast
iracing-setup-downloader download cda
iracing-setup-downloader download tracktitan
```

### Troubleshooting
```bash
# Enable verbose logging
iracing-setup-downloader download gofast --verbose

# Clear state (force re-download)
rm ~/.iracing-setup-downloader/state.json

# Test credentials
iracing-setup-downloader list gofast
iracing-setup-downloader list cda
iracing-setup-downloader list tracktitan
```

## Exit Codes

- `0`: Success
- `1`: General error (missing credentials, API error, etc.)
- `130`: Cancelled by user (Ctrl+C)

## Output Directory Structure

```
<output_path>/
├── <Car Name>/
│   └── <Track Name>/
│       └── <Provider>_<series>_<season>_<track>_<id>.<ext>
```

## State File Location

```
~/.iracing-setup-downloader/state.json
```
