#!/usr/bin/env python3
"""
Full YouTube Podcast Pipeline
Downloads, transcribes, summarizes, generates TTS, and posts to MordeNews.
"""

import subprocess
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import re
import shutil

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", SCRIPT_DIR / "data"))
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
SUMMARY_DIR = DATA_DIR / "summaries"

# Tool paths — override with environment variables
KOKORO_CMD = os.environ.get("KOKORO_CMD", shutil.which("kokoro-mlx") or "kokoro-mlx")
YT_DLP = os.environ.get("YT_DLP_CMD", shutil.which("yt-dlp") or "yt-dlp")
PARAKEET = os.environ.get("PARAKEET_CMD", shutil.which("parakeet-mlx") or "parakeet-mlx")
WHISPER = os.environ.get("WHISPER_CMD", shutil.which("whisper") or "whisper")
FFMPEG = os.environ.get("FFMPEG_CMD", shutil.which("ffmpeg") or "ffmpeg")

# Supabase config (optional — only needed for publishing)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Load channels from config.json
CONFIG_FILE = SCRIPT_DIR / "config.json"
with open(CONFIG_FILE) as f:
    config = json.load(f)
CHANNELS = config.get("channels", {})

PROCESSED_FILE = DATA_DIR / "processed.json"


def load_processed():
    if PROCESSED_FILE.exists():
        return json.load(open(PROCESSED_FILE))
    return {"videos": {}}


def save_processed(data):
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def get_video_info(channel_id, max_videos=2):
    """Get latest videos with metadata."""
    cmd = [
        YT_DLP, "--flat-playlist",
        "--print", "%(id)s|%(title)s|%(view_count)s|%(upload_date)s|%(duration)s",
        f"https://www.youtube.com/channel/{channel_id}/videos",
        "--playlist-items", f"1-{max_videos}",
        "--socket-timeout", "30",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|")
                if len(parts) >= 4:
                    videos.append({
                        "id": parts[0],
                        "title": parts[1],
                        "view_count": int(parts[2]) if parts[2].isdigit() else 0,
                        "upload_date": parts[3] if parts[3] != "NA" else None,
                        "duration": int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
                    })
        return videos
    except Exception as e:
        print(f"Error: {e}")
        return []


def download_audio(video_id):
    """Download audio from YouTube."""
    output = AUDIO_DIR / f"{video_id}.mp3"
    if output.exists():
        return output

    # Clean up any leftover .webm from prior failed attempts
    webm = AUDIO_DIR / f"{video_id}.webm"

    # Use proper output template — let yt-dlp manage extensions
    output_template = str(AUDIO_DIR / f"{video_id}.%(ext)s")
    cmd = [YT_DLP, "-x", "--audio-format", "mp3", "--audio-quality", "5",
           "--socket-timeout", "30", "--retries", "3",
           "--ffmpeg-location", str(Path(FFMPEG).parent),
           "-o", output_template, f"https://www.youtube.com/watch?v={video_id}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if output.exists():
            return output

        # Fallback: if .webm exists but conversion failed, convert manually
        if webm.exists():
            print(f"      ⚠️  webm exists, converting manually...")
            conv = subprocess.run(
                [FFMPEG, "-y", "-i", str(webm), "-vn", "-acodec", "libmp3lame",
                 "-q:a", "5", str(output)],
                capture_output=True, text=True, timeout=120
            )
            if output.exists():
                webm.unlink()
                return output
            print(f"      ⚠️  Manual conversion failed: {conv.stderr[-200:]}")

        # Log the actual error
        if result.returncode != 0:
            stderr = result.stderr[-300:] if result.stderr else "(no stderr)"
            print(f"      ⚠️  yt-dlp error: {stderr}")
        return None
    except Exception as e:
        # Still try webm fallback on exception
        if webm.exists():
            try:
                subprocess.run(
                    [FFMPEG, "-y", "-i", str(webm), "-vn", "-acodec", "libmp3lame",
                     "-q:a", "5", str(output)],
                    capture_output=True, timeout=120
                )
                if output.exists():
                    webm.unlink()
                    return output
            except:
                pass
        print(f"      ⚠️  Download exception: {e}")
        return None


def transcribe(audio_path):
    """Transcribe with parakeet-mlx (fast, MLX-native) or Whisper fallback."""
    transcript = TRANSCRIPT_DIR / f"{audio_path.stem}.txt"
    if transcript.exists():
        return transcript

    env = os.environ.copy()

    # Try parakeet-mlx first (faster, better quality on Apple Silicon)
    try:
        cmd = [PARAKEET, str(audio_path), "--output-format", "txt",
               "--output-dir", str(TRANSCRIPT_DIR)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=env)
        if transcript.exists():
            return transcript
        err_info = result.stderr[-300:] if result.stderr else result.stdout[-300:] if result.stdout else '(no output)'
        print(f"      ⚠️  Parakeet failed (rc={result.returncode}): {err_info}")
    except Exception as e:
        print(f"      ⚠️  Parakeet exception: {e}")

    # Fallback to whisper
    cmd = [WHISPER, str(audio_path), "--model", "tiny.en", "--language", "en",
           "--output_format", "txt", "--output_dir", str(TRANSCRIPT_DIR)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=env)
        if transcript.exists():
            return transcript
        err_info = result.stderr[-300:] if result.stderr else result.stdout[-300:] if result.stdout else '(no output)'
        print(f"      ⚠️  Whisper failed (rc={result.returncode}): {err_info}")
        return None
    except Exception as e:
        print(f"      ⚠️  Whisper exception: {e}")
        return None


def create_summary(channel, title, views, duration, transcript_text):
    """Create a summary with intro/outro."""
    sentences = transcript_text.replace('\n', ' ').split('. ')

    intro_sentences = '. '.join(sentences[:5]) + '.'
    mid = len(sentences) // 2
    middle_sentences = '. '.join(sentences[mid:mid+5]) + '.'
    outro_sentences = '. '.join(sentences[-3:])

    duration_str = f"{duration // 60} minutes" if duration else "several minutes"
    views_str = f"{views:,}" if views else "many"

    summary = f"""From {channel}'s channel, with {views_str} views. Here's the summary.

{intro_sentences}

{middle_sentences}

The key takeaway: {outro_sentences}

That was {channel}. Original video is {duration_str}, link in the description."""

    words = summary.split()
    if len(words) > 350:
        summary = ' '.join(words[:350]) + '...'

    return summary


def generate_tts(text, output_path, voice="am_michael"):
    """Generate TTS with Kokoro."""
    cmd = [KOKORO_CMD, text, str(output_path), voice]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # Combine chunks if kokoro split the output
        base = Path(output_path)
        chunks = sorted(base.parent.glob(f"{base.stem}*.wav"))
        if len(chunks) > 1:
            concat_file = base.parent / f"{base.stem}_concat.txt"
            with open(concat_file, 'w') as f:
                for chunk in chunks:
                    if chunk.name != base.name.replace('.wav', '_complete.wav'):
                        f.write(f"file '{chunk.name}'\n")

            combined = base.parent / f"{base.stem}_complete.wav"
            subprocess.run([
                FFMPEG, "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_file), "-c", "copy", str(combined)
            ], capture_output=True)

            return combined if combined.exists() else None

        return output_path if Path(output_path).exists() else None
    except Exception as e:
        print(f"TTS error: {e}")
        return None


def post_to_supabase(episode_data):
    """Post episode to Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("      ⚠️  Supabase not configured, skipping publish")
        return False

    import urllib.request

    url = f"{SUPABASE_URL}/rest/v1/news_items"

    news_item = {
        "title": f"🎙️ {episode_data['channel']}: {episode_data['title'][:80]}",
        "source": f"YouTube - {episode_data['channel']}",
        "url": f"https://www.youtube.com/watch?v={episode_data['video_id']}",
        "summary": episode_data['summary'][:500],
        "why_relevant": f"AI/Tech podcast with {episode_data['views']:,} views. TTS summary available.",
        "topic": "podcast"
    }

    data = json.dumps(news_item).encode('utf-8')
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        urllib.request.urlopen(req)
        return True
    except Exception as e:
        print(f"Supabase error: {e}")
        return False


def process_channel(channel_name, channel_id, processed):
    """Process a single channel."""
    print(f"\n📺 {channel_name}")

    videos = get_video_info(channel_id, max_videos=1)
    results = []

    for video in videos:
        vid_id = video["id"]

        if vid_id in processed["videos"]:
            print(f"   ⏭️  Already processed: {video['title'][:40]}...")
            continue

        print(f"   🆕 {video['title'][:50]}...")

        # Download
        print("      ⬇️  Downloading...")
        audio = download_audio(vid_id)
        if not audio:
            print("      ❌ Download failed")
            continue

        # Transcribe
        print("      🎤 Transcribing...")
        transcript = transcribe(audio)
        if not transcript:
            print("      ❌ Transcription failed")
            continue

        transcript_text = transcript.read_text()

        # Summarize
        print("      📝 Summarizing...")
        summary = create_summary(
            channel_name, video["title"],
            video["view_count"], video["duration"],
            transcript_text
        )

        # Save summary text
        summary_text_path = SUMMARY_DIR / f"{vid_id}_summary.txt"
        summary_text_path.write_text(summary)

        # Generate TTS
        print("      🎙️ Generating TTS...")
        audio_path = SUMMARY_DIR / f"{vid_id}.wav"
        tts_result = generate_tts(summary, audio_path)

        # Post to MordeNews
        print("      📤 Posting to MordeNews...")
        episode_data = {
            "video_id": vid_id,
            "channel": channel_name,
            "title": video["title"],
            "views": video["view_count"],
            "summary": summary,
        }
        post_to_supabase(episode_data)

        # Mark processed
        processed["videos"][vid_id] = {
            "channel": channel_name,
            "title": video["title"],
            "processed_at": datetime.now().isoformat()
        }

        results.append({
            "channel": channel_name,
            "title": video["title"],
            "video_id": vid_id,
            "tts": str(tts_result) if tts_result else None
        })

        print("      ✅ Done!")

    return results


def main():
    for d in [DATA_DIR, AUDIO_DIR, TRANSCRIPT_DIR, SUMMARY_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    processed = load_processed()

    print(f"🎙️ YouTube Podcast Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Channels: {len(CHANNELS)}")
    print("=" * 50)

    all_results = []

    for channel_name, channel_id in CHANNELS.items():
        results = process_channel(channel_name, channel_id, processed)
        all_results.extend(results)
        save_processed(processed)

    print("\n" + "=" * 50)
    print(f"✅ Complete! Processed: {len(all_results)} new episodes")

    return all_results


if __name__ == "__main__":
    results = main()
    print(json.dumps(results, indent=2))
