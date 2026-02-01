#!/bin/bash
# Example script demonstrating CLI usage

set -e

echo "=== iRacing Setup Downloader CLI Examples ==="
echo

# 1. Check version
echo "1. Checking version..."
poetry run iracing-setup-downloader --version
echo

# 2. Show help
echo "2. Showing help..."
poetry run iracing-setup-downloader --help
echo

# 3. List available setups (dry run - requires token)
echo "3. Listing available setups..."
echo "   Note: This requires a valid GoFast token"
echo "   Example: poetry run iracing-setup-downloader list gofast --token 'Bearer YOUR_TOKEN'"
echo

# 4. Download setups with dry run
echo "4. Downloading setups (dry run)..."
echo "   Note: This requires a valid GoFast token"
echo "   Example: poetry run iracing-setup-downloader download gofast --token 'Bearer YOUR_TOKEN' --dry-run"
echo

# 5. Download with custom settings
echo "5. Downloading with custom settings..."
echo "   Example: poetry run iracing-setup-downloader download gofast \\"
echo "              --token 'Bearer YOUR_TOKEN' \\"
echo "              --output ~/Documents/iRacing/setups \\"
echo "              --max-concurrent 10 \\"
echo "              --verbose"
echo

echo "=== Configuration via Environment Variables ==="
echo
echo "You can also set configuration via .env file or environment variables:"
echo
echo "export GOFAST_TOKEN='Bearer YOUR_TOKEN'"
echo "export OUTPUT_PATH='~/Documents/iRacing/setups'"
echo "export MAX_CONCURRENT=5"
echo
echo "Then run:"
echo "poetry run iracing-setup-downloader download gofast"
echo

echo "=== Done ==="
