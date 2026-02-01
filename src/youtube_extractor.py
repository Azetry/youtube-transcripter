"""YouTube 影片資料擷取模組 - 使用 yt-dlp"""

import os
from dataclasses import dataclass
from typing import Optional
from yt_dlp import YoutubeDL


@dataclass
class VideoInfo:
    """YouTube 影片資訊"""
    video_id: str
    title: str
    description: str
    duration: int  # 秒
    upload_date: str
    channel: str
    channel_id: str
    view_count: int
    thumbnail_url: str
    audio_file: Optional[str] = None


class YouTubeExtractor:
    """YouTube 影片擷取器"""

    def __init__(self, output_dir: str = "./downloads"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def extract_info(self, url: str) -> VideoInfo:
        """僅擷取影片資訊（不下載）"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            return VideoInfo(
                video_id=info.get('id', ''),
                title=info.get('title', ''),
                description=info.get('description', ''),
                duration=info.get('duration', 0),
                upload_date=info.get('upload_date', ''),
                channel=info.get('uploader', ''),
                channel_id=info.get('channel_id', ''),
                view_count=info.get('view_count', 0),
                thumbnail_url=info.get('thumbnail', ''),
            )

    def download_audio(self, url: str, format: str = 'mp3', quality: str = '64') -> VideoInfo:
        """
        下載影片音訊並回傳完整資訊

        Args:
            url: YouTube 網址
            format: 音訊格式 (預設 mp3)
            quality: 音訊品質 kbps (預設 64，確保不超過 Whisper 25MB 限制)
        """
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format,
                'preferredquality': quality,  # 降低品質以符合 Whisper 25MB 限制
            }],
            'outtmpl': f'{self.output_dir}/%(id)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_file = f"{self.output_dir}/{info.get('id')}.{format}"

            return VideoInfo(
                video_id=info.get('id', ''),
                title=info.get('title', ''),
                description=info.get('description', ''),
                duration=info.get('duration', 0),
                upload_date=info.get('upload_date', ''),
                channel=info.get('uploader', ''),
                channel_id=info.get('channel_id', ''),
                view_count=info.get('view_count', 0),
                thumbnail_url=info.get('thumbnail', ''),
                audio_file=audio_file,
            )

    @staticmethod
    def is_valid_youtube_url(url: str) -> bool:
        """檢查是否為有效的 YouTube 網址"""
        youtube_patterns = [
            'youtube.com/watch',
            'youtu.be/',
            'youtube.com/shorts/',
        ]
        return any(pattern in url for pattern in youtube_patterns)


if __name__ == "__main__":
    # 測試用
    extractor = YouTubeExtractor()
    test_url = input("請輸入 YouTube 網址: ")

    if extractor.is_valid_youtube_url(test_url):
        print("擷取影片資訊中...")
        info = extractor.extract_info(test_url)
        print(f"標題: {info.title}")
        print(f"頻道: {info.channel}")
        print(f"時長: {info.duration // 60}分{info.duration % 60}秒")
    else:
        print("無效的 YouTube 網址")
