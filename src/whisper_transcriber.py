"""OpenAI Whisper API 轉錄模組"""

import os
from dataclasses import dataclass
from typing import Optional
from openai import OpenAI


@dataclass
class TranscriptResult:
    """轉錄結果"""
    text: str
    language: str
    duration: float


class WhisperTranscriber:
    """使用 OpenAI Whisper API 進行語音轉文字"""

    # Whisper API 支援的最大檔案大小 (25MB)
    MAX_FILE_SIZE = 25 * 1024 * 1024

    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def transcribe(
        self,
        audio_file: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> TranscriptResult:
        """
        轉錄音訊檔案

        Args:
            audio_file: 音訊檔案路徑
            language: 指定語言代碼 (如 'zh', 'en', 'ja')，None 則自動偵測
            prompt: 提示詞，可改善特定術語或名稱的辨識

        Returns:
            TranscriptResult 包含轉錄文字
        """
        # 檢查檔案大小
        file_size = os.path.getsize(audio_file)
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"檔案大小 ({file_size / 1024 / 1024:.1f}MB) "
                f"超過 Whisper API 限制 (25MB)"
            )

        with open(audio_file, "rb") as f:
            # 建立 API 請求參數
            params = {
                "model": "whisper-1",
                "file": f,
                "response_format": "verbose_json",
            }

            if language:
                params["language"] = language
            if prompt:
                params["prompt"] = prompt

            response = self.client.audio.transcriptions.create(**params)

        return TranscriptResult(
            text=response.text,
            language=response.language,
            duration=response.duration,
        )

    def transcribe_with_timestamps(
        self,
        audio_file: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> dict:
        """
        轉錄音訊並取得時間戳記

        Returns:
            包含 segments（含時間戳）的完整回應
        """
        file_size = os.path.getsize(audio_file)
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"檔案大小 ({file_size / 1024 / 1024:.1f}MB) "
                f"超過 Whisper API 限制 (25MB)"
            )

        with open(audio_file, "rb") as f:
            params = {
                "model": "whisper-1",
                "file": f,
                "response_format": "verbose_json",
                "timestamp_granularities": ["segment"],
            }

            if language:
                params["language"] = language
            if prompt:
                params["prompt"] = prompt

            response = self.client.audio.transcriptions.create(**params)

        return {
            "text": response.text,
            "language": response.language,
            "duration": response.duration,
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                }
                for seg in response.segments
            ] if hasattr(response, 'segments') and response.segments else [],
        }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    transcriber = WhisperTranscriber()
    audio_path = input("請輸入音訊檔案路徑: ")

    if os.path.exists(audio_path):
        print("轉錄中...")
        result = transcriber.transcribe(audio_path)
        print(f"\n語言: {result.language}")
        print(f"時長: {result.duration:.1f} 秒")
        print(f"\n轉錄內容:\n{result.text}")
    else:
        print("檔案不存在")
