"""Shared end-to-end transcription orchestration.

This service owns the transcription pipeline logic that was
previously duplicated between main.py (CLI) and api/main.py (API).
Both entry points now delegate to this single implementation.
"""

import os
from typing import Callable, Optional

from src.youtube_extractor import YouTubeExtractor, VideoInfo
from src.whisper_transcriber import WhisperTranscriber
from src.text_corrector import TextCorrector
from src.diff_viewer import DiffViewer
from src.models.transcript import TranscriptArtifacts
from src.models.job import JobStatus


# Type for an optional progress callback: (status, progress%, message)
ProgressCallback = Callable[[JobStatus, int, str], None]


class TranscriptionService:
    """Orchestrates the full transcription pipeline.

    Stages:
    1. Validate URL
    2. Download audio
    3. Transcribe with Whisper
    4. Correct with GPT (optional)
    5. Generate diff
    6. Clean up audio file

    A progress callback allows callers (API job service, CLI progress bars)
    to observe pipeline progress without coupling to the service internals.
    """

    def __init__(
        self,
        download_dir: str = "./downloads",
        output_dir: str = "./transcripts",
    ) -> None:
        self.download_dir = download_dir
        self.output_dir = output_dir
        self.extractor = YouTubeExtractor(output_dir=download_dir)
        self.transcriber = WhisperTranscriber()
        self.corrector = TextCorrector()
        self.diff_viewer = DiffViewer()

    def validate_url(self, url: str) -> bool:
        """Check if the URL is a valid YouTube URL."""
        return self.extractor.is_valid_youtube_url(url)

    def run(
        self,
        url: str,
        language: Optional[str] = None,
        skip_correction: bool = False,
        custom_terms: Optional[list[str]] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> TranscriptArtifacts:
        """Execute the full transcription pipeline.

        Args:
            url: YouTube video URL.
            language: Language code for Whisper (None = auto-detect).
            skip_correction: Skip GPT correction step.
            custom_terms: Terms to emphasize during correction.
            on_progress: Optional callback for progress updates.

        Returns:
            TranscriptArtifacts with all pipeline outputs.

        Raises:
            ValueError: If the URL is invalid.
            Exception: Propagated from downstream services.
        """
        def progress(status: JobStatus, pct: int, msg: str) -> None:
            if on_progress:
                on_progress(status, pct, msg)

        # 1. Download audio
        progress(JobStatus.DOWNLOADING, 10, "下載影片音訊中...")
        video_info = self.extractor.download_audio(url)

        try:
            # 2. Transcribe
            progress(JobStatus.TRANSCRIBING, 40, "Whisper 轉錄中...")
            transcript_result = self.transcriber.transcribe(
                video_info.audio_file,
                language=language,
                prompt=video_info.title,
            )

            original_text = transcript_result.text

            # 3. Correct (optional)
            if skip_correction:
                corrected_text = original_text
            else:
                progress(JobStatus.CORRECTING, 70, "GPT 校正中...")
                context = f"影片標題：{video_info.title}\n頻道：{video_info.channel}"

                if custom_terms:
                    corrected_text = self.corrector.correct_with_terms(
                        original_text,
                        terms=custom_terms,
                        context=context,
                    )
                else:
                    corrected_text = self.corrector.correct(
                        original_text,
                        context=context,
                    )

            # 4. Generate diff
            progress(JobStatus.COMPLETED, 90, "產生差異比較...")
            diff_result = self.diff_viewer.compare(original_text, corrected_text)
            diff_inline = self.diff_viewer.get_inline_diff(original_text, corrected_text)

            return TranscriptArtifacts(
                video_info=video_info,
                original_text=original_text,
                corrected_text=corrected_text,
                language=transcript_result.language,
                similarity_ratio=diff_result.similarity_ratio,
                change_count=diff_result.change_count,
                diff_inline=diff_inline,
            )

        finally:
            # 5. Clean up audio file
            if video_info.audio_file and os.path.exists(video_info.audio_file):
                os.remove(video_info.audio_file)
