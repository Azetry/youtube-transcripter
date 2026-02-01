"""
FastAPI Backend - YouTube Transcripter API
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 導入現有模組
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.youtube_extractor import YouTubeExtractor, VideoInfo
from src.whisper_transcriber import WhisperTranscriber
from src.text_corrector import TextCorrector
from src.diff_viewer import DiffViewer


# ============== Pydantic Models ==============

class VideoURLRequest(BaseModel):
    url: str


class VideoInfoResponse(BaseModel):
    video_id: str
    title: str
    description: str
    duration: int
    duration_formatted: str
    upload_date: str
    channel: str
    channel_id: str
    view_count: int
    thumbnail_url: str


class TranscribeRequest(BaseModel):
    url: str
    language: Optional[str] = None
    skip_correction: bool = False
    custom_terms: Optional[list[str]] = None


class TranscribeResponse(BaseModel):
    video_id: str
    title: str
    channel: str
    duration: int
    original_text: str
    corrected_text: str
    language: str
    similarity_ratio: float
    change_count: int
    diff_inline: str
    processed_at: str


class TaskStatus(BaseModel):
    task_id: str
    status: str  # pending, processing, completed, failed
    progress: int  # 0-100
    message: str
    result: Optional[TranscribeResponse] = None


# ============== 全域狀態 ==============

# 任務狀態儲存 (實際應用建議用 Redis)
tasks: dict[str, TaskStatus] = {}


# ============== Helper Functions ==============

def format_duration(seconds: int) -> str:
    """格式化時間長度"""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


async def process_transcription(
    task_id: str,
    url: str,
    language: Optional[str],
    skip_correction: bool,
    custom_terms: Optional[list[str]],
):
    """背景處理轉錄任務"""
    try:
        tasks[task_id].status = "processing"
        tasks[task_id].progress = 10
        tasks[task_id].message = "下載影片音訊中..."

        # 1. 下載音訊
        extractor = YouTubeExtractor(output_dir="./downloads")
        video_info = await asyncio.to_thread(extractor.download_audio, url)

        tasks[task_id].progress = 40
        tasks[task_id].message = "Whisper 轉錄中..."

        # 2. Whisper 轉錄
        transcriber = WhisperTranscriber()
        transcript_result = await asyncio.to_thread(
            transcriber.transcribe,
            video_info.audio_file,
            language,
            video_info.title,
        )

        original_text = transcript_result.text
        tasks[task_id].progress = 70
        tasks[task_id].message = "GPT 校正中..."

        # 3. 校正
        if skip_correction:
            corrected_text = original_text
        else:
            corrector = TextCorrector()
            context = f"影片標題：{video_info.title}\n頻道：{video_info.channel}"

            if custom_terms:
                corrected_text = await asyncio.to_thread(
                    corrector.correct_with_terms,
                    original_text,
                    custom_terms,
                    context,
                )
            else:
                corrected_text = await asyncio.to_thread(
                    corrector.correct,
                    original_text,
                    context,
                )

        tasks[task_id].progress = 90
        tasks[task_id].message = "產生差異比較..."

        # 4. 差異比較
        diff_viewer = DiffViewer()
        diff_result = diff_viewer.compare(original_text, corrected_text)

        # 5. 清理暫存檔案
        if os.path.exists(video_info.audio_file):
            os.remove(video_info.audio_file)

        # 6. 完成
        tasks[task_id].progress = 100
        tasks[task_id].status = "completed"
        tasks[task_id].message = "處理完成"
        tasks[task_id].result = TranscribeResponse(
            video_id=video_info.video_id,
            title=video_info.title,
            channel=video_info.channel,
            duration=video_info.duration,
            original_text=original_text,
            corrected_text=corrected_text,
            language=transcript_result.language,
            similarity_ratio=diff_result.similarity_ratio,
            change_count=diff_result.change_count,
            diff_inline=diff_viewer.get_inline_diff(original_text, corrected_text),
            processed_at=datetime.now().isoformat(),
        )

    except Exception as e:
        tasks[task_id].status = "failed"
        tasks[task_id].message = f"錯誤: {str(e)}"


# ============== FastAPI App ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時
    os.makedirs("./downloads", exist_ok=True)
    os.makedirs("./transcripts", exist_ok=True)
    yield
    # 關閉時清理


app = FastAPI(
    title="YouTube Transcripter API",
    description="YouTube 影片逐字稿工具 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== API Endpoints ==============

@app.get("/")
async def root():
    return {"message": "YouTube Transcripter API", "version": "1.0.0"}


@app.post("/api/video/info", response_model=VideoInfoResponse)
async def get_video_info(request: VideoURLRequest):
    """取得 YouTube 影片資訊"""
    extractor = YouTubeExtractor()

    if not extractor.is_valid_youtube_url(request.url):
        raise HTTPException(status_code=400, detail="無效的 YouTube 網址")

    try:
        info = await asyncio.to_thread(extractor.extract_info, request.url)
        return VideoInfoResponse(
            video_id=info.video_id,
            title=info.title,
            description=info.description,
            duration=info.duration,
            duration_formatted=format_duration(info.duration),
            upload_date=info.upload_date,
            channel=info.channel,
            channel_id=info.channel_id,
            view_count=info.view_count,
            thumbnail_url=info.thumbnail_url,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"擷取失敗: {str(e)}")


@app.post("/api/transcribe")
async def start_transcription(
    request: TranscribeRequest,
    background_tasks: BackgroundTasks,
):
    """開始轉錄任務（背景處理）"""
    extractor = YouTubeExtractor()

    if not extractor.is_valid_youtube_url(request.url):
        raise HTTPException(status_code=400, detail="無效的 YouTube 網址")

    # 建立任務
    task_id = f"task_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    tasks[task_id] = TaskStatus(
        task_id=task_id,
        status="pending",
        progress=0,
        message="任務已建立，等待處理...",
    )

    # 加入背景任務
    background_tasks.add_task(
        process_transcription,
        task_id,
        request.url,
        request.language,
        request.skip_correction,
        request.custom_terms,
    )

    return {"task_id": task_id, "message": "任務已開始"}


@app.get("/api/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """取得任務狀態"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    return tasks[task_id]


@app.post("/api/correct")
async def correct_text(text: str, context: Optional[str] = None):
    """單獨校正文字"""
    corrector = TextCorrector()
    corrected = await asyncio.to_thread(corrector.correct, text, context)

    diff_viewer = DiffViewer()
    diff_result = diff_viewer.compare(text, corrected)

    return {
        "original": text,
        "corrected": corrected,
        "similarity_ratio": diff_result.similarity_ratio,
        "change_count": diff_result.change_count,
        "diff_inline": diff_viewer.get_inline_diff(text, corrected),
    }


@app.get("/api/health")
async def health_check():
    """健康檢查"""
    return {
        "status": "healthy",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
