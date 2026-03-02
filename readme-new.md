# MordeNews

**Automated daily podcast from YouTube channels. Zero human involvement.**

https://github.com/mordechaipotash/mordenews/raw/main/assets/demo.mp4

---

Every morning at 6am, this pipeline:

1. Downloads latest videos from 21 AI/tech YouTube channels
2. Transcribes them locally (Parakeet MLX)
3. Summarizes with Gemini Flash
4. Speaks the summaries with neural TTS (Kokoro MLX)
5. Stitches into a two-host daily podcast
6. Publishes

You wake up. The podcast is ready. ~$0.01/day in API costs.

---

## Install

```bash
git clone https://github.com/mordechaipotash/mordenews
cd mordenews
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
```

## Run

```bash
python pipeline.py              # Run once
crontab -e                      # Add: 0 6 * * * cd ~/mordenews && python pipeline.py
```

---

## Pipeline

```
📺 YouTube Channels (21)
    ↓ yt-dlp
🎵 Audio Files
    ↓ parakeet-mlx (local)
📝 Transcripts
    ↓ Gemini Flash ($0.01)
📋 Summaries
    ↓ kokoro-mlx (local)
🔊 TTS Audio
    ↓ ffmpeg
🎙️ Daily Podcast (~15 min)
    ↓ Supabase
🌐 Published
```

---

## Channels

AI Explained · Fireship · Lex Fridman · Dwarkesh Patel · Two Minute Papers · Yannic Kilcher · AI Breakdown · Matt Wolfe · The AI Advantage · Wes Roth · David Shapiro · AI Jason · AssemblyAI · and more.

Channels are configurable in `config.yaml`.

---

## Features

- **Local STT** — Parakeet MLX on Apple Silicon, no API calls
- **Two-host format** — Alex (male) and Sarah (female) discuss top 5 stories
- **Deduplication** — Never re-processes a video
- **Fault-tolerant** — Fallbacks at every stage
- **Configurable** — Add/remove channels, adjust summary length

---

## Requirements

- Apple Silicon Mac (for local TTS/STT)
- Python 3.11+
- Gemini API key (or OpenRouter)
- ~2GB RAM

---

## Part of the ecosystem

[brain-mcp](https://github.com/mordechaipotash/brain-mcp) · [local-voice-ai](https://github.com/mordechaipotash/local-voice-ai) · [agent-memory-loop](https://github.com/mordechaipotash/agent-memory-loop) · [x-search](https://github.com/mordechaipotash/x-search) · [live-translate](https://github.com/mordechaipotash/live-translate)

## License

MIT
