#!/usr/bin/env python3
"""
Publish daily podcast to MordeNews
- Uploads to Supabase Storage
- Creates news entry
- Optionally posts to Discord
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", SCRIPT_DIR / "data"))
SUPERCUT_DIR = DATA_DIR / "supercuts"

# Supabase config from environment
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "podcast-audio")

# Optional Discord webhook
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

FFPROBE = shutil.which("ffprobe") or "ffprobe"


def get_duration(audio_path):
    """Get audio duration in minutes:seconds format."""
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, text=True
        )
        seconds = float(result.stdout.strip())
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}:{secs:02d}"
    except:
        return "~20:00"


def upload_to_supabase(file_path, filename):
    """Upload file to Supabase Storage."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("   ⚠️  Supabase not configured, skipping upload")
        return None

    import urllib.request

    url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{filename}"

    with open(file_path, 'rb') as f:
        data = f.read()

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "audio/mpeg",
        "x-upsert": "true",
    }

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        urllib.request.urlopen(req)
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{filename}"
        return public_url
    except Exception as e:
        # Try PUT (upsert)
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method='PUT')
            urllib.request.urlopen(req)
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{filename}"
            return public_url
        except Exception as e2:
            print(f"Upload failed: {e2}")
            return None


def create_news_entry(title, audio_url, script_path, duration):
    """Create a news entry in Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    import urllib.request

    script_content = ""
    if script_path.exists():
        script_content = script_path.read_text()[:2000]

    summary = f"""🎙️ Daily AI News Podcast

**Hosts:** Alex & Sarah discuss today's top AI stories

**Duration:** {duration}

*Auto-generated from AI YouTube channels*"""

    data = json.dumps({
        "title": title,
        "source": "MordeNews Daily Podcast",
        "url": audio_url,
        "summary": summary,
        "why_relevant": "Daily curated AI news in podcast format",
        "topic": "podcast",
        "audio_url": audio_url,
    }).encode('utf-8')

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/news",
            data=data, headers=headers, method='POST'
        )
        urllib.request.urlopen(req)
        return True
    except Exception as e:
        print(f"News entry error: {e}")
        return False


def post_to_discord(audio_url, duration, date_str):
    """Post notification to Discord via webhook."""
    if not DISCORD_WEBHOOK_URL:
        return False

    import urllib.request

    message = {
        "content": f"""🎙️ **MordeNews Daily Podcast** — {date_str}

🎧 **Duration:** {duration}
🤖 **Hosts:** Alex & Sarah

🔗 {audio_url}

*Auto-generated from AI YouTube channels*"""
    }

    data = json.dumps(message).encode('utf-8')
    headers = {"Content-Type": "application/json"}

    try:
        req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=data, headers=headers, method='POST')
        urllib.request.urlopen(req)
        return True
    except:
        return False


def main():
    today = datetime.now().strftime("%Y-%m-%d")

    podcast_file = SUPERCUT_DIR / f"mordenews_daily_{today}.mp3"
    script_file = SUPERCUT_DIR / f"{today}_script.txt"

    if not podcast_file.exists():
        print(f"❌ No podcast found for {today}")
        print(f"   Expected: {podcast_file}")
        return False

    print(f"📤 Publishing MordeNews Daily — {today}")
    print("=" * 50)

    # Get duration
    duration = get_duration(podcast_file)
    print(f"⏱️  Duration: {duration}")

    # Upload to Supabase Storage
    print("\n☁️  Uploading to Supabase Storage...")
    filename = f"daily_{today}.mp3"
    audio_url = upload_to_supabase(podcast_file, filename)

    if not audio_url:
        print("   ❌ Upload failed (or Supabase not configured)")
        print(f"   📁 Local file: {podcast_file}")
        return False

    print(f"   ✅ Uploaded: {audio_url}")

    # Create news entry
    print("\n📰 Creating news entry...")
    title = f"🎙️ MordeNews Daily — {today}"
    if create_news_entry(title, audio_url, script_file, duration):
        print("   ✅ News entry created")
    else:
        print("   ⚠️  News entry may have failed")

    # Post to Discord
    print("\n💬 Posting to Discord...")
    if post_to_discord(audio_url, duration, today):
        print("   ✅ Discord notification sent")
    else:
        print("   ⚠️  Discord post skipped (webhook not configured)")

    print("\n" + "=" * 50)
    print(f"🎉 Published! Listen at: {audio_url}")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
