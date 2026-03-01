#!/bin/bash
# MordeNews Daily Pipeline Runner
# Run this via cron: 0 6 * * * /path/to/mordenews/run_daily.sh >> /tmp/mordenews.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

echo "========================================"
echo "🎙️ MordeNews Daily Pipeline"
echo "$(date)"
echo "========================================"

# Stage 1: Download + Transcribe + Summarize individual videos
echo ""
echo "📥 Stage 1: Processing channels..."
python3 full_pipeline.py

# Stage 2: Generate daily supercut podcast
echo ""
echo "🎬 Stage 2: Creating daily supercut..."
python3 daily_supercut.py

# Stage 3: Publish
echo ""
echo "📤 Stage 3: Publishing..."
python3 publish_podcast.py

echo ""
echo "========================================"
echo "✅ Done! $(date)"
echo "========================================"
