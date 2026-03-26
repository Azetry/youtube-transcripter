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

    @staticmethod
    def _build_auth_opts() -> dict:
        """Build yt-dlp authentication options from environment variables.

        Supported env vars (all optional — when absent, no auth is used):
          YT_DLP_COOKIES_FILE        – path to a Netscape-format cookies.txt
          YT_DLP_COOKIES_FROM_BROWSER – browser name for cookie extraction,
                                        e.g. "chrome", "firefox", "brave"
          YT_DLP_BROWSER_PROFILE     – browser profile name (used with
                                        cookies-from-browser)
          YT_DLP_BROWSER_CONTAINER   – browser container/keyring hint

        If both COOKIES_FILE and COOKIES_FROM_BROWSER are set, COOKIES_FILE
        takes precedence (yt-dlp only accepts one).
        """
        opts: dict = {}

        cookies_file = os.environ.get("YT_DLP_COOKIES_FILE")
        cookies_browser = os.environ.get("YT_DLP_COOKIES_FROM_BROWSER")

        if cookies_file:
            opts["cookiefile"] = cookies_file
        elif cookies_browser:
            # yt-dlp format: "browser:profile:container"
            browser_spec = cookies_browser
            profile = os.environ.get("YT_DLP_BROWSER_PROFILE")
            container = os.environ.get("YT_DLP_BROWSER_CONTAINER")
            if profile:
                browser_spec += f":{profile}"
                if container:
                    browser_spec += f":{container}"
            elif container:
                browser_spec += f"::{container}"
            opts["cookiesfrombrowser"] = (browser_spec,)

        return opts

    def extract_info(self, url: str) -> VideoInfo:
        """僅擷取影片資訊（不下載）"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            **self._build_auth_opts(),
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
            **self._build_auth_opts(),
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
