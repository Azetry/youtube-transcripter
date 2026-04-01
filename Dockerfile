# Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴 (ffmpeg for yt-dlp)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴檔案
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 選用：說話者分段（pyannote）額外套件 — 與 requirements-speaker-{cpu,gpu}.txt 一致
# Build: --build-arg SPEAKER_PROFILE=none|cpu|gpu（預設 none，映像最小）
ARG SPEAKER_PROFILE=none
COPY requirements-speaker-cpu.txt requirements-speaker-gpu.txt ./
RUN set -eux; \
    case "$SPEAKER_PROFILE" in \
      none) \
        echo "SPEAKER_PROFILE=none: skipping PyTorch/pyannote speaker stack" ;; \
      cpu) \
        pip install --no-cache-dir -r requirements-speaker-cpu.txt ;; \
      gpu) \
        pip install --no-cache-dir -r requirements-speaker-gpu.txt ;; \
      *) \
        echo "SPEAKER_PROFILE must be none, cpu, or gpu (got: ${SPEAKER_PROFILE})" >&2; \
        exit 1 ;; \
    esac

ENV SPEAKER_PROFILE=${SPEAKER_PROFILE}

# 複製應用程式碼
COPY main.py ./
COPY src/ ./src/
COPY api/ ./api/
COPY tests/ ./tests/

# 建立下載和輸出目錄
RUN mkdir -p downloads transcripts

# 暴露端口
EXPOSE 8000

# 啟動命令
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
