#!/usr/bin/env python3
"""
Summarize transcript and generate TTS audio.
Takes a transcript, summarizes to ~3 min read, generates Kokoro TTS.
"""

import subprocess
import sys
import json
import os
import shutil
from pathlib import Path

KOKORO_CMD = os.environ.get("KOKORO_CMD", shutil.which("kokoro-mlx") or "kokoro-mlx")
GEMINI_CMD = os.environ.get("GEMINI_CMD", shutil.which("gemini") or "gemini")

SUMMARY_PROMPT = """Summarize this YouTube video transcript into a compelling 3-minute audio briefing (about 400-500 words).

Requirements:
- Start with a hook: "Here's what you need to know about [topic]..."
- Cover the key insights, news, or arguments
- Include specific details, names, numbers when relevant
- End with the main takeaway
- Write in a natural, conversational tone for audio
- NO bullet points or formatting - just flowing prose for TTS

Transcript:
{transcript}

Write the summary now:"""


def summarize_with_gemini(transcript: str) -> str:
    """Use Gemini CLI to summarize."""
    prompt = SUMMARY_PROMPT.format(transcript=transcript[:15000])

    cmd = [GEMINI_CMD, "-m", "gemini-2.5-flash"]

    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            output = result.stdout.strip()
            if "text" in output.lower():
                lines = output.split('\n')
                summary_lines = []
                capture = False
                for line in lines:
                    if "Here's what" in line or capture:
                        capture = True
                        summary_lines.append(line)
                if summary_lines:
                    return '\n'.join(summary_lines)
            return output
    except Exception as e:
        print(f"Gemini error: {e}")

    return None


def summarize_extractive(transcript: str) -> str:
    """Fallback: simple extractive summary."""
    sentences = transcript.replace('\n', ' ').split('. ')

    intro = '. '.join(sentences[:3]) + '.'
    mid_start = len(sentences) // 3
    middle = '. '.join(sentences[mid_start:mid_start+5]) + '.'
    conclusion = '. '.join(sentences[-5:])

    summary = f"Here's what you need to know from this video. {intro}\n\n{middle}\n\nThe key takeaway: {conclusion}"

    words = summary.split()
    if len(words) > 500:
        summary = ' '.join(words[:500]) + '...'

    return summary


def generate_tts(text: str, output_path: str, voice: str = "am_michael") -> bool:
    """Generate TTS with Kokoro MLX."""
    cmd = [KOKORO_CMD, text, output_path, voice]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return Path(output_path).exists()
    except Exception as e:
        print(f"TTS error: {e}")
        return False


def process_transcript(transcript_path: str, output_dir: str = None, voice: str = "am_michael"):
    """Full pipeline: transcript -> summary -> TTS."""
    transcript_path = Path(transcript_path)

    if not transcript_path.exists():
        print(f"Error: {transcript_path} not found")
        return None

    transcript = transcript_path.read_text()
    video_id = transcript_path.stem

    print(f"📄 Processing: {video_id}")
    print(f"   Transcript: {len(transcript)} chars")

    # Summarize
    print("   🤖 Summarizing...")
    summary = summarize_with_gemini(transcript)

    if not summary:
        print("   ⚠️  Gemini failed, using extractive summary")
        summary = summarize_extractive(transcript)

    print(f"   Summary: {len(summary.split())} words")

    # Setup output
    if output_dir:
        output_dir = Path(output_dir)
    else:
        output_dir = transcript_path.parent.parent / "summaries"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save summary text
    summary_text_path = output_dir / f"{video_id}_summary.txt"
    summary_text_path.write_text(summary)
    print(f"   💾 Saved: {summary_text_path}")

    # Generate TTS
    print(f"   🎙️ Generating TTS ({voice})...")
    audio_path = output_dir / f"{video_id}_summary.wav"

    if generate_tts(summary, str(audio_path), voice):
        print(f"   🔊 Audio: {audio_path}")
        return {
            "video_id": video_id,
            "summary_text": str(summary_text_path),
            "summary_audio": str(audio_path),
            "word_count": len(summary.split())
        }
    else:
        print("   ❌ TTS failed")
        return {
            "video_id": video_id,
            "summary_text": str(summary_text_path),
            "summary_audio": None,
            "word_count": len(summary.split())
        }


def main():
    if len(sys.argv) < 2:
        print("Usage: summarize_and_speak.py <transcript.txt> [output_dir] [voice]")
        print("Voices: am_michael (male), am_fenrir (male), af_heart (female)")
        sys.exit(1)

    transcript_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    voice = sys.argv[3] if len(sys.argv) > 3 else "am_michael"

    result = process_transcript(transcript_path, output_dir, voice)

    if result:
        print("\n✅ Complete!")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
