#!/usr/bin/env python3
"""
Daily Supercut Podcast Generator
Creates a ~20 min 2-speaker podcast from the day's AI news.
"""

import subprocess
import json
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import tempfile
import re

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", SCRIPT_DIR / "data"))
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
SUPERCUT_DIR = DATA_DIR / "supercuts"
SUPERCUT_DIR.mkdir(parents=True, exist_ok=True)

KOKORO_CMD = os.environ.get("KOKORO_CMD", shutil.which("kokoro-mlx") or "kokoro-mlx")
GEMINI_CMD = os.environ.get("GEMINI_CMD", shutil.which("gemini") or "gemini")
FFMPEG = os.environ.get("FFMPEG_CMD", shutil.which("ffmpeg") or "ffmpeg")

# Two hosts with different voices
HOSTS = {
    "Alex": os.environ.get("KOKORO_VOICE_ALEX", "am_michael"),   # Male voice
    "Sarah": os.environ.get("KOKORO_VOICE_SARAH", "af_heart"),   # Female voice
}

# Topics of interest for ranking stories
INTERESTS = [
    "AI agents", "autonomous systems", "coding automation",
    "Claude", "Anthropic", "OpenAI", "GPT",
    "local LLMs", "open source AI", "AI infrastructure", "MCP",
    "developer tools", "automation", "agentic workflows",
    "breakthrough research", "AGI", "reasoning models",
    "AI startups", "monetization", "indie hackers"
]


def get_recent_transcripts(hours=24):
    """Get all transcripts from the last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    transcripts = []

    for f in TRANSCRIPT_DIR.glob("*.txt"):
        if f.stat().st_mtime > cutoff.timestamp():
            content = f.read_text()
            video_id = f.stem
            transcripts.append({
                "id": video_id,
                "content": content[:15000],
                "file": f.name
            })

    return transcripts


def generate_podcast_script(transcripts):
    """Use Gemini to generate a 2-speaker podcast script."""
    combined = "\n\n---\n\n".join([
        f"VIDEO {i+1}:\n{t['content'][:5000]}"
        for i, t in enumerate(transcripts[:10])
    ])

    prompt = f"""You are creating a script for a 20-minute podcast called "MordeNews Daily".

Two hosts - Alex (male, analytical) and Sarah (female, enthusiastic) - discuss the day's AI news.

INTERESTS (rank topics by these):
{', '.join(INTERESTS)}

TODAY'S VIDEO TRANSCRIPTS:
{combined}

INSTRUCTIONS:
1. Identify the TOP 5 most interesting topics from these videos
2. Write a conversational podcast script (~4000 words = 20 min)
3. Format EXACTLY like this (one speaker per line):

ALEX: [opening line]
SARAH: [response]
ALEX: [next point]
...

REQUIREMENTS:
- Natural conversation, not scripted-sounding
- Include specific details, numbers, names from the videos
- Alex is more analytical, Sarah adds enthusiasm and asks good questions
- Cover each topic for ~4 minutes
- Include a brief intro and outro
- Make it engaging - like two friends geeking out about AI

Write the full script now:"""

    cmd = [GEMINI_CMD, "-m", "gemini-2.5-flash"]

    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=180)
        return result.stdout.strip()
    except Exception as e:
        print(f"Error generating script: {e}")
        return None


def parse_script(script_text):
    """Parse script into speaker segments."""
    segments = []

    # Match ALEX: or SARAH: at start of line
    pattern = r'^(ALEX|SARAH):\s*(.+?)(?=^(?:ALEX|SARAH):|$)'
    matches = re.findall(pattern, script_text, re.MULTILINE | re.DOTALL)

    for speaker, text in matches:
        text = text.strip()
        if text:
            segments.append({
                "speaker": speaker.capitalize(),
                "text": text,
                "voice": HOSTS.get(speaker.capitalize(), "af_heart")
            })

    # Fallback: simple line-by-line parsing
    if not segments:
        for line in script_text.split('\n'):
            line = line.strip()
            if line.startswith('ALEX:'):
                segments.append({
                    "speaker": "Alex",
                    "text": line[5:].strip(),
                    "voice": HOSTS["Alex"]
                })
            elif line.startswith('SARAH:'):
                segments.append({
                    "speaker": "Sarah",
                    "text": line[6:].strip(),
                    "voice": HOSTS["Sarah"]
                })

    return segments


def generate_audio_segment(text, voice, output_path):
    """Generate TTS audio for a segment."""
    cmd = [KOKORO_CMD, text, str(output_path), voice]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120)
        return output_path.exists()
    except Exception as e:
        print(f"TTS error: {e}")
        return False


def concatenate_audio(segment_files, output_path):
    """Concatenate audio files with ffmpeg."""
    list_file = Path(tempfile.mktemp(suffix='.txt'))
    with open(list_file, 'w') as f:
        for seg in segment_files:
            f.write(f"file '{seg}'\n")

    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:a", "libmp3lame", "-q:a", "2",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=600)
        list_file.unlink()
        return output_path.exists()
    except Exception as e:
        print(f"FFmpeg error: {e}")
        return False


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"🎙️ MordeNews Daily Supercut - {today}")
    print("=" * 50)

    # Get recent transcripts
    print("\n📄 Collecting transcripts...")
    transcripts = get_recent_transcripts(hours=24)
    print(f"   Found {len(transcripts)} transcripts")

    if len(transcripts) < 2:
        print("   ⚠️ Not enough new content for a supercut")
        return None

    # Generate script
    print("\n✍️ Generating podcast script...")
    script = generate_podcast_script(transcripts)
    if not script:
        print("   ❌ Failed to generate script")
        return None

    # Save script for reference
    script_file = SUPERCUT_DIR / f"{today}_script.txt"
    script_file.write_text(script)
    print(f"   📝 Script saved: {script_file.name}")

    # Parse into segments
    print("\n🎭 Parsing script...")
    segments = parse_script(script)
    print(f"   Found {len(segments)} speaker segments")

    if len(segments) < 5:
        print("   ⚠️ Script parsing failed, not enough segments")
        return None

    # Generate audio for each segment
    print("\n🔊 Generating audio segments...")
    temp_dir = Path(tempfile.mkdtemp())
    segment_files = []

    for i, seg in enumerate(segments):
        output = temp_dir / f"seg_{i:03d}.wav"
        print(f"   [{i+1}/{len(segments)}] {seg['speaker']}: {seg['text'][:50]}...")

        if generate_audio_segment(seg['text'], seg['voice'], output):
            segment_files.append(output)
        else:
            print(f"   ⚠️ Failed segment {i}")

    print(f"   Generated {len(segment_files)}/{len(segments)} segments")

    # Concatenate
    print("\n🎬 Creating final podcast...")
    output_file = SUPERCUT_DIR / f"mordenews_daily_{today}.mp3"

    if concatenate_audio(segment_files, output_file):
        # Get duration
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(output_file)],
            capture_output=True, text=True
        )
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0
        minutes = int(duration // 60)
        seconds = int(duration % 60)

        print(f"   ✅ Created: {output_file.name}")
        print(f"   ⏱️ Duration: {minutes}:{seconds:02d}")

        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)

        return str(output_file)
    else:
        print("   ❌ Failed to create final audio")
        return None


if __name__ == "__main__":
    result = main()
    if result:
        print(f"\n🎉 Podcast ready: {result}")
        # Auto-publish
        print("\n📤 Auto-publishing...")
        subprocess.run(["python3", str(SCRIPT_DIR / "publish_podcast.py")])
    else:
        print("\n❌ Podcast generation failed")
