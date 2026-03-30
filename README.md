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
- **Speaker Attribution** - Generic speaker labels (Speaker A/B/…): default **pause heuristic**, or optional **pyannote** post-hoc diarization (`pyannote_v1`); not named-speaker recognition
- **Acquisition Hardening** - Structured acquisition diagnostics and fallback policy (local host only; no remote delegation)

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

The default backend image installs **only** `requirements.txt` (Whisper API path, no PyTorch/pyannote).

### Docker speaker profiles

Optional **`SPEAKER_PROFILE`** build argument layers the same files used for local CLI installs: `requirements-speaker-cpu.txt` or `requirements-speaker-gpu.txt`. Default is **`none`** (smallest image, fastest build).

| Profile | Meaning |
|---------|---------|
| `none` | Base `requirements.txt` only (default for `docker compose build`). |
| `cpu` | Adds CPU PyTorch + `pyannote.audio` (large image; long first build). |
| `gpu` | Adds CUDA-oriented PyTorch + `pyannote.audio`. Adjust index URLs in `requirements-speaker-gpu.txt` if your CUDA stack differs. Run with NVIDIA Container Toolkit / `--gpus` as appropriate. |

**Compose:** set in `.env` (see `.env.example`), then rebuild:

```bash
# Example: CPU speaker stack inside the backend container
export SPEAKER_PROFILE=cpu
docker compose build --no-cache backend
docker compose up -d
```

**Plain Docker:**

```bash
docker build --build-arg SPEAKER_PROFILE=cpu -t yt-backend-cpu .
```

For **`pyannote_v1`** in containers, set **`PYANNOTE_AUTH_TOKEN`** in `.env` (and accept gated models on Hugging Face). The token is passed through to the backend container automatically via `docker-compose.yml`.

#### Running each mode

| Mode | Build | Run |
|------|-------|-----|
| **Base** (default) | `docker compose build backend` | `docker compose up -d` |
| **Speaker CPU** | `SPEAKER_PROFILE=cpu docker compose build --no-cache backend` | `docker compose up -d` |
| **Speaker GPU** | `SPEAKER_PROFILE=gpu docker compose build --no-cache backend` | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d` |

The GPU override file (`docker-compose.gpu.yml`) reserves an NVIDIA GPU device for the backend container. It requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) on the host.

**GPU check** (after building with `SPEAKER_PROFILE=gpu` and running with GPU access):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm backend python -c "import torch; print('cuda:', torch.cuda.is_available())"
```

## Speaker attribution

Assigns **generic** labels (Speaker A/B/…), not real names.

| Strategy | CLI `--speaker-strategy` | Extra Python deps | Notes |
|----------|------------------------|-------------------|--------|
| Pause-based heuristic (default) | `pause_heuristic_v1` | None beyond base `requirements.txt` | Fast; low accuracy |
| **pyannote** diarization | `pyannote_v1` | PyTorch stack + `pyannote.audio` | Higher quality; requires HF token and **gated model access** |

### Prerequisites (pyannote / `pyannote_v1`)

1. **Python 3.11+** and **FFmpeg** on the host (FFmpeg is also used to normalize lossy audio before diarization).
2. Install **one** of the speaker stacks (CPU or GPU — see `requirements-speaker-cpu.txt` / `requirements-speaker-gpu.txt`):
   ```bash
   pip install -r requirements.txt -r requirements-speaker-cpu.txt
   ```
   Adjust the GPU file’s PyTorch index if your CUDA version differs.
3. **Hugging Face**
   - Create a **read** token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
   - Set `PYANNOTE_AUTH_TOKEN` in `.env` (see `.env.example`).
   - For each **gated** model the pipeline needs, open the model page and click **Agree and access** (at minimum: `pyannote/speaker-diarization-3.1` and dependencies such as `pyannote/speaker-diarization-community-1`). Access can take a few minutes to propagate.

### CLI examples

```bash
# List strategies and descriptions
python main.py --list-speaker-strategies

# Heuristic only (no pyannote)
python main.py --speaker-attribution https://youtube.com/watch?v=VIDEO_ID

# Real diarization (requires pyannote install + PYANNOTE_AUTH_TOKEN)
python main.py --speaker-strategy pyannote_v1 "https://www.youtube.com/watch?v=VIDEO_ID"
```

Artifacts include `*_speaker_segments.json` and metadata when attribution is enabled.

## Usage

### CLI

> Requires Python 3.11+ and FFmpeg

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Basic usage
python main.py https://youtube.com/watch?v=VIDEO_ID

# Speaker attribution (see "Speaker attribution" section above)
python main.py --speaker-attribution https://youtube.com/watch?v=VIDEO_ID
python main.py --speaker-strategy pyannote_v1 https://youtube.com/watch?v=VIDEO_ID

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

## Documentation

- Acquisition reasoning / failure classes / fallback logic:
  - `docs/acquisition-runbook.md`
- Removed backup HTTP delegation (historical):
  - `docs/backup-delegation-removed.md`
- Consolidated OpenSpec **specs** (after archiving completed changes):
  - `openspec/specs/`
- Remaining active OpenSpec **change** (if any):
  - `openspec/changes/harden-youtube-acquisition/` (when still present)
- Archived proposals:
  - `openspec/changes/archive/`

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
| `PYANNOTE_AUTH_TOKEN` | Hugging Face token for `pyannote_v1` (gated models) | Only for pyannote strategy |
| `HF_TOKEN` | Optional; some Hugging Face tooling also reads this | No |
| `SERVICE_ROLE` | Optional marker; reflected in `/api/health` | No |
| `YT_DLP_COOKIES_FILE` | Netscape-format cookies file for authenticated extraction | No |
| `YT_DLP_COOKIES_FROM_BROWSER` | Browser name for cookie extraction | No |

Copy `.env.example` to `.env` and edit; never commit real secrets.

### Running tests

The suite under `tests/` constructs `TranscriptionService`, which initializes the OpenAI client during `WhisperTranscriber` setup. **Set `OPENAI_API_KEY` in the environment** before `pytest` (a placeholder such as `test` is enough for unit tests; network calls are mocked).

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=test
python -m pytest tests/
```

## Current Project State

This repo includes: long-video transcript pipeline, speaker attribution (heuristic + optional pyannote), and YouTube acquisition hardening. Completed OpenSpec changes are under `openspec/changes/archive/` with merged specs in `openspec/specs/`.

## Limitations

- Whisper API has a 25MB file size limit; audio quality is set to 64kbps to comply
- Transcription quality depends on audio clarity and Whisper model capabilities
- GPT corrections may alter original meaning; manual review is recommended
- YouTube acquisition reliability may still vary by host/network/IP reputation; see the acquisition runbook

## License

MIT License - See [LICENSE](LICENSE) file for details

## Contributing

Issues and Pull Requests are welcome!

---

Developed and maintained by [Azetry](https://github.com/azetry)
