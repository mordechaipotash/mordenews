#!/usr/bin/env python3
"""
Lightweight YouTube Podcast Pipeline
Downloads new videos from favorite channels, transcribes, and prepares for MordeNews.
Use this for download + transcribe only (no TTS, no publishing).
"""

import json
import subprocess
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", SCRIPT_DIR / "data"))
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
CONFIG_FILE = SCRIPT_DIR / "config.json"
PROCESSED_FILE = DATA_DIR / "processed.json"

YT_DLP = os.environ.get("YT_DLP_CMD", shutil.which("yt-dlp") or "yt-dlp")
WHISPER = os.environ.get("WHISPER_CMD", shutil.which("whisper") or "whisper")


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_processed():
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE) as f:
            return json.load(f)
    return {"videos": {}}


def save_processed(data):
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def get_recent_videos(channel_id, max_videos=3, days_back=1):
    """Get recent videos from a channel."""
    cmd = [
        YT_DLP, "--flat-playlist",
        "--print", "%(id)s|%(title)s|%(upload_date)s|%(duration)s",
        f"https://www.youtube.com/channel/{channel_id}/videos",
        "--playlist-items", f"1-{max_videos}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    vid_id, title, upload_date = parts[0], parts[1], parts[2]
                    duration = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
                    videos.append({
                        "id": vid_id,
                        "title": title,
                        "upload_date": upload_date,
                        "duration": duration
                    })
        return videos
    except Exception as e:
        print(f"Error fetching videos: {e}")
        return []


def download_audio(video_id, output_dir):
    """Download audio from a YouTube video."""
    output_file = output_dir / f"{video_id}.mp3"
    if output_file.exists():
        return output_file

    cmd = [
        YT_DLP, "-x", "--audio-format", "mp3", "--audio-quality", "5",
        "-o", str(output_file),
        f"https://www.youtube.com/watch?v={video_id}"
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600)
        return output_file if output_file.exists() else None
    except Exception as e:
        print(f"Error downloading {video_id}: {e}")
        return None


def transcribe(audio_path, output_dir, model="tiny.en"):
    """Transcribe audio using Whisper."""
    transcript_file = output_dir / f"{audio_path.stem}.txt"
    if transcript_file.exists():
        return transcript_file

    cmd = [
        WHISPER, str(audio_path),
        "--model", model,
        "--language", "en",
        "--output_format", "txt",
        "--output_dir", str(output_dir)
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=1800)
        return transcript_file if transcript_file.exists() else None
    except Exception as e:
        print(f"Error transcribing {audio_path}: {e}")
        return None


def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    config = load_config()
    processed = load_processed()

    print(f"🎙️ YouTube Podcast Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    new_content = []

    for channel_name, channel_id in config["channels"].items():
        print(f"\n📺 {channel_name}")

        videos = get_recent_videos(
            channel_id,
            config.get("maxVideosPerChannel", 3),
            config.get("lookbackDays", 1)
        )

        for video in videos:
            vid_id = video["id"]

            if vid_id in processed["videos"]:
                print(f"   ⏭️  {video['title'][:50]}...")
                continue

            print(f"   🆕 {video['title'][:50]}...")

            # Download audio
            print(f"      ⬇️  Downloading...")
            audio_path = download_audio(vid_id, AUDIO_DIR)

            if audio_path:
                # Transcribe
                print(f"      🎤 Transcribing...")
                transcript_path = transcribe(
                    audio_path, TRANSCRIPT_DIR,
                    config.get("whisperModel", "tiny.en")
                )

                if transcript_path and transcript_path.exists():
                    transcript_text = transcript_path.read_text()[:5000]

                    processed["videos"][vid_id] = {
                        "channel": channel_name,
                        "title": video["title"],
                        "processed_at": datetime.now().isoformat(),
                        "transcript_path": str(transcript_path),
                        "duration": video.get("duration", 0)
                    }

                    new_content.append({
                        "channel": channel_name,
                        "title": video["title"],
                        "video_id": vid_id,
                        "transcript_preview": transcript_text[:1000],
                        "url": f"https://www.youtube.com/watch?v={vid_id}"
                    })

                    print(f"      ✅ Done")

    save_processed(processed)

    print("\n" + "=" * 50)
    print(f"✅ Complete! New videos: {len(new_content)}")

    if new_content:
        output_file = DATA_DIR / f"new_content_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(output_file, 'w') as f:
            json.dump(new_content, f, indent=2)
        print(f"📝 New content saved to: {output_file}")

    return new_content


if __name__ == "__main__":
    main()
