# YouTube Transcripter

A powerful YouTube video transcription tool that integrates OpenAI Whisper API for speech-to-text and GPT for automatic transcript correction.

[繁體中文](README.zh.md)

## Features

- **Video Info Extraction** - Free YouTube video metadata extraction via yt-dlp (title, channel, duration, etc.)
- **Speech-to-Text** - High-quality transcription using OpenAI Whisper API (whisper-1 model)
- **Smart Correction** - Automatic transcript correction using GPT-4o-mini
- **Diff Comparison** - Visual diff view between original and corrected transcripts
- **Dual Interface** - Both CLI and Web interface available
- **Docker Deployment** - One-click deployment with Docker Compose
- **Long-video Pipeline** - Chunking, merge/dedupe, and long-video transcript processing support
- **Acquisition Hardening** - Structured acquisition diagnostics, fallback policy, and backup-service delegation foundation

## Architecture

```
youtube-transcripter/
├── src/                      # Core modules
│   ├── youtube_extractor.py  # YouTube extraction (yt-dlp)
│   ├── whisper_transcriber.py# Whisper speech-to-text
│   ├── text_corrector.py     # GPT text correction
│   └── diff_viewer.py        # Diff comparison display
├── api/                      # FastAPI backend
│   └── main.py
├── web/                      # Vue 3 frontend
│   ├── src/
│   │   └── App.vue
│   └── Dockerfile
├── main.py                   # CLI entry point
├── docker-compose.yml        # Docker deployment config
└── requirements.txt          # Python dependencies
```

## Quick Start

### Prerequisites

- Docker + Docker Compose
- OpenAI API Key

### Deployment

```bash
git clone https://github.com/azetry/youtube-transcripter.git
cd youtube-transcripter

# Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Start services
docker compose up -d
```

Open browser at http://localhost:3000

## Usage

### CLI

> Requires Python 3.11+ and FFmpeg

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Basic usage
python main.py https://youtube.com/watch?v=VIDEO_ID

# Interactive mode
python main.py -i

# More options
python main.py --help
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/video/info` | POST | Get video information |
| `/api/transcribe` | POST | Start transcription task |
| `/api/task/{id}` | GET | Get task status |
| `/delegate/health` | GET | Backup-service health check |
| `/delegate/transcribe` | POST | Backup-service delegated transcription |

## Documentation

- Acquisition reasoning / failure classes / fallback logic:
  - `docs/acquisition-runbook.md`
- A/B backup-service deployment and acceptance guide:
  - `docs/backup-service-deployment.md`
- Active OpenSpec changes:
  - `openspec/changes/upgrade-transcription-pipeline/`
  - `openspec/changes/harden-youtube-acquisition/`

## Tech Stack

### Backend
- **Python 3.11+**
- **FastAPI** - Modern high-performance web framework
- **yt-dlp** - YouTube video/audio download
- **OpenAI API** - Whisper transcription + GPT correction

### Frontend
- **Vue 3** - Frontend framework
- **Vite** - Build tool
- **Tailwind CSS** - CSS framework

### Deployment
- **Docker** + **Docker Compose**
- **Nginx** - Reverse proxy

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `BACKUP_SERVICE_URL` | Backup-service base URL for A→B delegation | No |
| `BACKUP_SERVICE_TOKEN` | Shared bearer token for backup-service delegation | No |
| `SERVICE_ROLE` | Service role marker (e.g. `backup`); reflected in health output | No |
| `YT_DLP_COOKIES_FILE` | Netscape-format cookies file for authenticated extraction | No |
| `YT_DLP_COOKIES_FROM_BROWSER` | Browser name for cookie extraction | No |

## Backup Deployment

To run this repo as a backup (B) service — backend only, no frontend:

```bash
export BACKUP_SERVICE_TOKEN=<shared-secret>
export OPENAI_API_KEY=<key>

docker compose -f docker-compose.yml -f docker-compose.backup.yml up -d
```

This publishes the backend on port 8000 with `SERVICE_ROLE=backup` and disables the frontend.
See `docs/backup-service-deployment.md` for the full A/B deployment and acceptance guide.

## Current Project State

This repo now contains two major implementation tracks:
1. upgraded long-video transcript pipeline
2. YouTube acquisition hardening + backup-service fallback MVP

OpenSpec changes remain active until final reconciliation/archive.

## Limitations

- Whisper API has a 25MB file size limit; audio quality is set to 64kbps to comply
- Transcription quality depends on audio clarity and Whisper model capabilities
- GPT corrections may alter original meaning; manual review is recommended
- YouTube acquisition reliability may still vary by host/network/IP reputation; see the acquisition runbook and backup-service deployment guide

## License

MIT License - See [LICENSE](LICENSE) file for details

## Contributing

Issues and Pull Requests are welcome!

---

Developed and maintained by [Azetry](https://github.com/azetry)
