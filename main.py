#!/usr/bin/env python3
"""
YouTube Transcripter - YouTube 影片逐字稿工具

功能：
1. 貼上 YouTube 網址擷取影片基本資料
2. 透過 OpenAI Whisper API 取得逐字稿
3. 自動校正功能
4. 比較原始轉譯與校正後差異
"""

import os
import json
import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from src.youtube_extractor import YouTubeExtractor
from src.whisper_transcriber import WhisperTranscriber
from src.text_corrector import TextCorrector
from src.diff_viewer import DiffViewer, print_colored_diff

# 載入環境變數
load_dotenv()

console = Console()


def format_duration(seconds: int) -> str:
    """格式化時間長度"""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def display_video_info(video_info) -> None:
    """顯示影片資訊"""
    table = Table(title="影片資訊", show_header=False, box=None)
    table.add_column("欄位", style="cyan")
    table.add_column("內容")

    table.add_row("標題", video_info.title)
    table.add_row("頻道", video_info.channel)
    table.add_row("時長", format_duration(video_info.duration))
    table.add_row("上傳日期", video_info.upload_date)
    table.add_row("觀看次數", f"{video_info.view_count:,}")
    table.add_row("影片 ID", video_info.video_id)

    console.print(table)


def save_transcript(
    video_info,
    original_text: str,
    corrected_text: str,
    output_dir: str = "./transcripts",
) -> dict[str, str]:
    """儲存逐字稿到檔案"""
    os.makedirs(output_dir, exist_ok=True)

    base_name = f"{video_info.video_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 儲存原始轉譯
    original_path = os.path.join(output_dir, f"{base_name}_original.txt")
    with open(original_path, 'w', encoding='utf-8') as f:
        f.write(original_text)

    # 儲存校正後
    corrected_path = os.path.join(output_dir, f"{base_name}_corrected.txt")
    with open(corrected_path, 'w', encoding='utf-8') as f:
        f.write(corrected_text)

    # 儲存完整資訊 (JSON)
    metadata_path = os.path.join(output_dir, f"{base_name}_metadata.json")
    metadata = {
        "video_id": video_info.video_id,
        "title": video_info.title,
        "channel": video_info.channel,
        "duration": video_info.duration,
        "upload_date": video_info.upload_date,
        "processed_at": datetime.now().isoformat(),
    }
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # 儲存 HTML 差異報告
    diff_viewer = DiffViewer()
    diff_result = diff_viewer.compare(original_text, corrected_text)
    diff_path = os.path.join(output_dir, f"{base_name}_diff.html")
    diff_viewer.save_html_diff(diff_result, diff_path)

    return {
        "original": original_path,
        "corrected": corrected_path,
        "metadata": metadata_path,
        "diff_html": diff_path,
    }


def process_video(
    url: str,
    language: str | None = None,
    skip_correction: bool = False,
    custom_terms: list[str] | None = None,
    output_dir: str = "./transcripts",
    download_dir: str = "./downloads",
) -> None:
    """處理單一影片的完整流程"""

    extractor = YouTubeExtractor(output_dir=download_dir)
    transcriber = WhisperTranscriber()
    corrector = TextCorrector()
    diff_viewer = DiffViewer()

    # 1. 驗證網址
    if not extractor.is_valid_youtube_url(url):
        console.print("[red]錯誤：無效的 YouTube 網址[/red]")
        return

    # 2. 擷取影片資訊並下載音訊
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # 下載音訊
        task = progress.add_task("下載影片音訊...", total=None)
        video_info = extractor.download_audio(url)
        progress.update(task, completed=True)

    console.print()
    display_video_info(video_info)
    console.print()

    # 3. Whisper 轉錄
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Whisper 轉錄中...", total=None)
        transcript_result = transcriber.transcribe(
            video_info.audio_file,
            language=language,
            prompt=video_info.title,  # 使用標題作為提示
        )
        progress.update(task, completed=True)

    console.print(f"[green]偵測語言: {transcript_result.language}[/green]")
    console.print()

    original_text = transcript_result.text

    # 4. 校正（如果需要）
    if skip_correction:
        corrected_text = original_text
        console.print("[yellow]跳過校正步驟[/yellow]")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("GPT 校正中...", total=None)

            context = f"影片標題：{video_info.title}\n頻道：{video_info.channel}"

            if custom_terms:
                corrected_text = corrector.correct_with_terms(
                    original_text,
                    terms=custom_terms,
                    context=context,
                )
            else:
                corrected_text = corrector.correct(original_text, context=context)

            progress.update(task, completed=True)

    # 5. 顯示差異
    if not skip_correction:
        diff_result = diff_viewer.compare(original_text, corrected_text)
        console.print()
        print_colored_diff(diff_result)

    # 6. 儲存結果
    saved_files = save_transcript(
        video_info,
        original_text,
        corrected_text,
        output_dir=output_dir,
    )

    console.print()
    console.print(Panel(
        f"原始轉譯: {saved_files['original']}\n"
        f"校正後: {saved_files['corrected']}\n"
        f"差異報告: {saved_files['diff_html']}\n"
        f"元資料: {saved_files['metadata']}",
        title="已儲存檔案",
        border_style="green",
    ))

    # 7. 清理暫存音訊（可選）
    if os.path.exists(video_info.audio_file):
        os.remove(video_info.audio_file)
        console.print(f"[dim]已清理暫存音訊: {video_info.audio_file}[/dim]")


def interactive_mode() -> None:
    """互動模式"""
    console.print(Panel(
        "YouTube Transcripter - 互動模式\n"
        "輸入 YouTube 網址開始處理，輸入 'quit' 或 'q' 離開",
        title="歡迎使用",
    ))

    while True:
        console.print()
        url = console.input("[cyan]YouTube 網址:[/cyan] ").strip()

        if url.lower() in ('quit', 'q', 'exit'):
            console.print("[yellow]再見！[/yellow]")
            break

        if not url:
            continue

        try:
            process_video(url)
        except KeyboardInterrupt:
            console.print("\n[yellow]已取消處理[/yellow]")
        except Exception as e:
            console.print(f"[red]錯誤: {e}[/red]")


def main():
    parser = argparse.ArgumentParser(
        description="YouTube Transcripter - YouTube 影片逐字稿工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python main.py https://youtube.com/watch?v=VIDEO_ID
  python main.py -l zh https://youtube.com/watch?v=VIDEO_ID
  python main.py --no-correct https://youtube.com/watch?v=VIDEO_ID
  python main.py -i  # 互動模式
        """,
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="YouTube 影片網址",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="啟動互動模式",
    )
    parser.add_argument(
        "-l", "--language",
        help="指定語言代碼 (如 zh, en, ja)，預設自動偵測",
    )
    parser.add_argument(
        "--no-correct",
        action="store_true",
        help="跳過 GPT 校正步驟",
    )
    parser.add_argument(
        "-t", "--terms",
        nargs="+",
        help="需要正確辨識的專有名詞列表",
    )
    parser.add_argument(
        "-o", "--output",
        default="./transcripts",
        help="輸出目錄 (預設: ./transcripts)",
    )

    args = parser.parse_args()

    # 檢查 API Key
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[red]錯誤: 請設定 OPENAI_API_KEY 環境變數[/red]")
        console.print("可以複製 .env.example 為 .env 並填入 API Key")
        return

    if args.interactive or not args.url:
        interactive_mode()
    else:
        try:
            process_video(
                args.url,
                language=args.language,
                skip_correction=args.no_correct,
                custom_terms=args.terms,
                output_dir=args.output,
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]已取消處理[/yellow]")
        except Exception as e:
            console.print(f"[red]錯誤: {e}[/red]")
            raise


if __name__ == "__main__":
    main()
