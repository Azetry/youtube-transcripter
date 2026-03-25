"""
FastAPI Backend - YouTube Transcripter API
"""

import os
import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 導入現有模組
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.youtube_extractor import YouTubeExtractor
from src.diff_viewer import DiffViewer
from src.models.job import JobStatus
from src.services.transcription_service import TranscriptionService
from src.services.job_service import JobService
from src.storage.schema import bootstrap
from src.storage.sqlite_store import SQLiteStore


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


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending, downloading, transcribing, correcting, completed, failed
    progress: int  # 0-100
    message: str
    result: Optional[TranscribeResponse] = None


# ============== Shared Services ==============

_db_conn = bootstrap()
_store = SQLiteStore(_db_conn)
job_service = JobService(store=_store)
transcription_service = TranscriptionService()

# In-memory result cache for active session (supplement to DB persistence)
_task_results: dict[str, TranscribeResponse] = {}


# ============== Helper Functions ==============

def format_duration(seconds: int) -> str:
    """格式化時間長度"""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


async def process_transcription(job_id: str):
    """背景處理轉錄任務"""
    job = job_service.get_job(job_id)
    if not job:
        return

    try:
        def on_progress(status: JobStatus, pct: int, msg: str):
            job_service.update_job(job_id, status, pct, msg)

        artifacts = await asyncio.to_thread(
            transcription_service.run,
            url=job.url,
            language=job.language,
            skip_correction=job.skip_correction,
            custom_terms=job.custom_terms,
            on_progress=on_progress,
        )

        # Store result
        result_data = {
            "video_id": artifacts.video_info.video_id,
            "title": artifacts.video_info.title,
            "channel": artifacts.video_info.channel,
            "duration": artifacts.video_info.duration,
            "original_text": artifacts.original_text,
            "corrected_text": artifacts.corrected_text,
            "language": artifacts.language,
            "similarity_ratio": artifacts.similarity_ratio,
            "change_count": artifacts.change_count,
            "diff_inline": artifacts.diff_inline,
            "processed_at": datetime.now().isoformat(),
        }
        _task_results[job_id] = TranscribeResponse(**result_data)
        job_service.store_result(job_id, result_data)

        job_service.complete_job(job_id)

    except Exception as e:
        job_service.fail_job(job_id, str(e))


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
    if not transcription_service.validate_url(request.url):
        raise HTTPException(status_code=400, detail="無效的 YouTube 網址")

    # 建立任務 (via shared job service)
    job = job_service.create_job(
        url=request.url,
        language=request.language,
        skip_correction=request.skip_correction,
        custom_terms=request.custom_terms,
    )

    # 加入背景任務
    background_tasks.add_task(process_transcription, job.job_id)

    return {"task_id": job.job_id, "message": "任務已開始"}


@app.get("/api/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """取得任務狀態"""
    job = job_service.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="任務不存在")

    # Try in-memory cache first, then fall back to persisted result
    result = _task_results.get(task_id)
    if result is None and job.status == JobStatus.COMPLETED:
        db_result = job_service.get_result(task_id)
        if db_result:
            # Remove non-column keys if present (e.g. job_id from row)
            db_result.pop("job_id", None)
            result = TranscribeResponse(**db_result)
            _task_results[task_id] = result  # warm the cache

    return TaskStatusResponse(
        task_id=job.job_id,
        status=job.status.value,
        progress=job.progress,
        message=job.message,
        result=result,
    )


@app.post("/api/correct")
async def correct_text(text: str, context: Optional[str] = None):
    """單獨校正文字"""
    from src.text_corrector import TextCorrector
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
