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

## Limitations

- Whisper API has a 25MB file size limit; audio quality is set to 64kbps to comply
- Transcription quality depends on audio clarity and Whisper model capabilities
- GPT corrections may alter original meaning; manual review is recommended

## License

MIT License - See [LICENSE](LICENSE) file for details

## Contributing

Issues and Pull Requests are welcome!

---

Developed and maintained by [Azetry](https://github.com/azetry)
