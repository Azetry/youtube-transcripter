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

from src.diff_viewer import DiffViewer, print_colored_diff
from src.models.transcript import TranscriptArtifacts
from src.services.transcription_service import TranscriptionService

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
    artifacts: TranscriptArtifacts | None = None,
) -> dict[str, str]:
    """儲存逐字稿到檔案。

    回傳路徑字典，鍵至少包含：original、corrected、metadata、diff_html；
    若有說話人分段檔則另含 speaker_segments。
    """
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

    # Include speaker attribution metadata when available
    if artifacts and artifacts.speaker_attribution_enabled:
        metadata["speaker_attribution"] = {
            "enabled": True,
            "strategy": artifacts.speaker_strategy,
            "detected_speaker_count": artifacts.speaker_count,
            "speaker_segments_file": os.path.join(
                output_dir, f"{base_name}_speaker_segments.json"
            ) if artifacts.speaker_segments else None,
        }

    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    saved = {
        "original": original_path,
        "corrected": corrected_path,
        "metadata": metadata_path,
    }

    # Save speaker segments as separate JSON when present
    if artifacts and artifacts.speaker_attribution_enabled and artifacts.speaker_segments:
        segments_path = os.path.join(output_dir, f"{base_name}_speaker_segments.json")
        with open(segments_path, 'w', encoding='utf-8') as f:
            json.dump(artifacts.speaker_segments, f, ensure_ascii=False, indent=2)
        saved["speaker_segments"] = segments_path

    # 儲存 HTML 差異報告
    diff_viewer = DiffViewer()
    diff_result = diff_viewer.compare(original_text, corrected_text)
    diff_path = os.path.join(output_dir, f"{base_name}_diff.html")
    diff_viewer.save_html_diff(diff_result, diff_path)
    saved["diff_html"] = diff_path

    return saved


def format_speaker_attribution_summary(
    artifacts: TranscriptArtifacts,
    saved_files: dict[str, str],
) -> str | None:
    """組出「Speaker Attribution」面板的內文；未啟用說話人時回傳 None。"""
    if not artifacts.speaker_attribution_enabled:
        return None
    lines = [
        f"Strategy: {artifacts.speaker_strategy}",
        f"Detected speakers: {artifacts.speaker_count}",
    ]
    seg_path = saved_files.get("speaker_segments")
    if seg_path:
        lines.append(f"Segments file: {seg_path}")
    return "\n".join(lines)


def process_video(
    url: str,
    language: str | None = None,
    skip_correction: bool = False,
    custom_terms: list[str] | None = None,
    speaker_attribution: bool = False,
    speaker_strategy: str | None = None,
    output_dir: str = "./transcripts",
    download_dir: str = "./downloads",
) -> None:
    """處理單一影片的完整流程"""

    service = TranscriptionService(
        download_dir=download_dir,
        output_dir=output_dir,
    )

    # 1. 驗證網址
    if not service.validate_url(url):
        console.print("[red]錯誤：無效的 YouTube 網址[/red]")
        return

    # 2. 執行轉錄管線（透過共用服務層）
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        current_task = progress.add_task("處理中...", total=None)

        def on_progress(status, pct, message):
            progress.update(current_task, description=message)

        artifacts = service.run(
            url=url,
            language=language,
            skip_correction=skip_correction,
            custom_terms=custom_terms,
            speaker_attribution=speaker_attribution,
            speaker_strategy=speaker_strategy,
            on_progress=on_progress,
        )

    # 3. 顯示影片資訊
    console.print()
    display_video_info(artifacts.video_info)
    console.print()

    console.print(f"[green]偵測語言: {artifacts.language}[/green]")
    console.print()

    # 4. 顯示差異
    if not skip_correction:
        diff_viewer = DiffViewer()
        diff_result = diff_viewer.compare(artifacts.original_text, artifacts.corrected_text)
        console.print()
        print_colored_diff(diff_result)

    # 5. 儲存結果
    saved_files = save_transcript(
        artifacts.video_info,
        artifacts.original_text,
        artifacts.corrected_text,
        output_dir=output_dir,
        artifacts=artifacts,
    )

    # 6. Speaker attribution summary
    speaker_summary = format_speaker_attribution_summary(artifacts, saved_files)
    if speaker_summary is not None:
        console.print()
        console.print(Panel(
            speaker_summary,
            title="Speaker Attribution",
            border_style="magenta",
        ))

    console.print()
    file_lines = (
        f"原始轉譯: {saved_files['original']}\n"
        f"校正後: {saved_files['corrected']}\n"
        f"差異報告: {saved_files['diff_html']}\n"
        f"元資料: {saved_files['metadata']}"
    )
    if saved_files.get("speaker_segments"):
        file_lines += f"\n說話者分段: {saved_files['speaker_segments']}"
    console.print(Panel(
        file_lines,
        title="已儲存檔案",
        border_style="green",
    ))


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
        "--speaker-attribution",
        "--speakers",
        action="store_true",
        dest="speaker_attribution",
        help="Enable speaker attribution (experimental). Assigns generic labels "
        "(Speaker A/B/C) to transcript segments using the default pause-based "
        "heuristic. For real diarization, use --speaker-strategy instead.",
    )
    parser.add_argument(
        "--speaker-strategy",
        default=None,
        dest="speaker_strategy",
        help="Select a speaker attribution strategy (implies --speaker-attribution). "
        "Options: 'pause_heuristic_v1' — fast, text-only, detects turns at "
        "silence gaps (default); 'pyannote_v1' — real audio diarization, higher "
        "accuracy, requires pyannote.audio and PYANNOTE_AUTH_TOKEN env var. "
        "Use --list-speaker-strategies for details.",
    )
    parser.add_argument(
        "--list-speaker-strategies",
        action="store_true",
        dest="list_speaker_strategies",
        help="Print available speaker attribution strategies with descriptions "
        "and exit.",
    )
    parser.add_argument(
        "-o", "--output",
        default="./transcripts",
        help="輸出目錄 (預設: ./transcripts)",
    )

    args = parser.parse_args()

    # --list-speaker-strategies: print and exit
    if args.list_speaker_strategies:
        from src.transcript.speaker_attribution import (
            DEFAULT_STRATEGY,
            describe_strategies,
        )
        descriptions = describe_strategies()
        console.print("[bold]Available speaker attribution strategies:[/bold]\n")
        for sid, desc in sorted(descriptions.items()):
            default_tag = " [dim](default)[/dim]" if sid == DEFAULT_STRATEGY else ""
            console.print(f"  [cyan]{sid}[/cyan]{default_tag}")
            console.print(f"    {desc}\n")
        return

    # 檢查 API Key
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[red]錯誤: 請設定 OPENAI_API_KEY 環境變數[/red]")
        console.print("可以複製 .env.example 為 .env 並填入 API Key")
        return

    # --speaker-strategy implies --speaker-attribution
    speaker_attribution = args.speaker_attribution or bool(args.speaker_strategy)

    if args.interactive or not args.url:
        interactive_mode()
    else:
        try:
            process_video(
                args.url,
                language=args.language,
                skip_correction=args.no_correct,
                custom_terms=args.terms,
                speaker_attribution=speaker_attribution,
                speaker_strategy=args.speaker_strategy,
                output_dir=args.output,
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]已取消處理[/yellow]")
        except Exception as e:
            console.print(f"[red]錯誤: {e}[/red]")
            raise


if __name__ == "__main__":
    main()
