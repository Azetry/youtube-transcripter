# Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴 (ffmpeg for yt-dlp)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴檔案
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

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
