#!/bin/bash
# YouTube Podcast Pipeline — Shell version
# Downloads new videos from favorite channels, transcribes, and queues for summarization
#
# Usage: ./fetch_podcasts.sh [config.json]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="${1:-$SCRIPT_DIR/config.json}"
DATA_DIR="${DATA_DIR:-$SCRIPT_DIR/data}"
AUDIO_DIR="$DATA_DIR/audio"
TRANSCRIPT_DIR="$DATA_DIR/transcripts"
SUMMARY_DIR="$DATA_DIR/summaries"

# Tool paths (auto-detect or use env vars)
YT_DLP="${YT_DLP_CMD:-$(which yt-dlp 2>/dev/null || echo yt-dlp)}"
WHISPER="${WHISPER_CMD:-$(which whisper 2>/dev/null || echo whisper)}"
PARAKEET="${PARAKEET_CMD:-$(which parakeet-mlx 2>/dev/null || echo parakeet-mlx)}"

mkdir -p "$AUDIO_DIR" "$TRANSCRIPT_DIR" "$SUMMARY_DIR"

# Parse channels from config.json
if ! command -v jq &>/dev/null; then
    echo "Error: jq is required (brew install jq)"
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file not found: $CONFIG_FILE"
    exit 1
fi

# Track processed videos
PROCESSED_FILE="$DATA_DIR/processed.txt"
touch "$PROCESSED_FILE"

# Date filter (last 24 hours)
DATE_AFTER=$(date -v-1d +%Y%m%d 2>/dev/null || date -d '1 day ago' +%Y%m%d)

echo "🎙️ YouTube Podcast Pipeline - $(date)"
echo "Config: $CONFIG_FILE"
echo "Checking for new videos since $DATE_AFTER"
echo "============================================"

# Read channels from config.json
jq -r '.channels | to_entries[] | "\(.key)|\(.value)"' "$CONFIG_FILE" | while IFS='|' read -r channel_name channel_id; do
    echo ""
    echo "📺 Checking: $channel_name"

    # Get latest videos from channel
    videos=$("$YT_DLP" --flat-playlist --print "%(id)s|%(title)s|%(upload_date)s" \
        "https://www.youtube.com/channel/$channel_id/videos" \
        --playlist-items 1-5 \
        --dateafter "$DATE_AFTER" 2>/dev/null || true)

    if [ -z "$videos" ]; then
        echo "   No new videos"
        continue
    fi

    echo "$videos" | while IFS='|' read -r video_id title upload_date; do
        # Skip if already processed
        if grep -q "^$video_id$" "$PROCESSED_FILE" 2>/dev/null; then
            echo "   ⏭️  Already processed: $title"
            continue
        fi

        echo "   🆕 New: $title ($video_id)"

        # Download audio
        audio_file="$AUDIO_DIR/${video_id}.mp3"
        if [ ! -f "$audio_file" ]; then
            echo "   ⬇️  Downloading audio..."
            "$YT_DLP" -x --audio-format mp3 --audio-quality 5 \
                -o "$audio_file" \
                "https://www.youtube.com/watch?v=$video_id" 2>/dev/null || true
        fi

        # Transcribe (try parakeet-mlx first, fall back to whisper)
        transcript_file="$TRANSCRIPT_DIR/${video_id}.txt"
        if [ -f "$audio_file" ] && [ ! -f "$transcript_file" ]; then
            echo "   🎤 Transcribing..."
            if command -v parakeet-mlx &>/dev/null; then
                "$PARAKEET" "$audio_file" --output-format txt \
                    --output-dir "$TRANSCRIPT_DIR" 2>/dev/null || \
                "$WHISPER" "$audio_file" --model tiny.en --language en \
                    --output_format txt --output_dir "$TRANSCRIPT_DIR" 2>/dev/null || true
            else
                "$WHISPER" "$audio_file" --model tiny.en --language en \
                    --output_format txt --output_dir "$TRANSCRIPT_DIR" 2>/dev/null || true
            fi
        fi

        # Mark as processed
        echo "$video_id" >> "$PROCESSED_FILE"

        # Queue for summary
        if [ -f "$transcript_file" ]; then
            echo "   ✅ Ready for summary"
            echo "$video_id|$channel_name|$title|$transcript_file" >> "$DATA_DIR/pending_summaries.txt"
        fi
    done
done

echo ""
echo "============================================"
echo "✅ Pipeline complete"

pending=$(wc -l < "$DATA_DIR/pending_summaries.txt" 2>/dev/null || echo "0")
echo "📝 Pending summaries: $pending"
