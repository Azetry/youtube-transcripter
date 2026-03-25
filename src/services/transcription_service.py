"""Shared end-to-end transcription orchestration.

This service owns the transcription pipeline logic that was
previously duplicated between main.py (CLI) and api/main.py (API).
Both entry points now delegate to this single implementation.

Supports two flows:
  - Short video: single-pass transcribe → correct → diff
  - Long video: chunk → transcribe each → correct each → merge → consistency → diff
"""

import os
from typing import Callable, Optional

from src.youtube_extractor import YouTubeExtractor, VideoInfo
from src.whisper_transcriber import WhisperTranscriber
from src.text_corrector import TextCorrector
from src.diff_viewer import DiffViewer
from src.models.transcript import TranscriptArtifacts
from src.models.job import JobStatus
from src.media.chunker import needs_chunking, generate_chunk_files
from src.transcript.models import ChunkTranscript, Segment
from src.transcript.merger import merge_chunks, consistency_pass


# Type for an optional progress callback: (status, progress%, message)
ProgressCallback = Callable[[JobStatus, int, str], None]


class TranscriptionService:
    """Orchestrates the full transcription pipeline.

    Short-video stages:
    1. Download audio
    2. Transcribe with Whisper
    3. Correct with GPT (optional)
    4. Generate diff
    5. Clean up

    Long-video stages:
    1. Download audio
    2. Chunk audio
    3. Transcribe + correct each chunk
    4. Merge chunks (dedupe overlaps)
    5. Consistency pass
    6. Generate diff
    7. Clean up
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
        job_id: Optional[str] = None,
    ) -> TranscriptArtifacts:
        """Execute the full transcription pipeline.

        Args:
            url: YouTube video URL.
            language: Language code for Whisper (None = auto-detect).
            skip_correction: Skip GPT correction step.
            custom_terms: Terms to emphasize during correction.
            on_progress: Optional callback for progress updates.
            job_id: Optional job ID used for chunk file naming.

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

        chunk_files_to_clean: list[str] = []
        try:
            duration = video_info.duration

            if needs_chunking(duration):
                return self._run_long_video(
                    video_info=video_info,
                    language=language,
                    skip_correction=skip_correction,
                    custom_terms=custom_terms,
                    progress=progress,
                    job_id=job_id or "tmp",
                    chunk_files_to_clean=chunk_files_to_clean,
                )
            else:
                return self._run_short_video(
                    video_info=video_info,
                    language=language,
                    skip_correction=skip_correction,
                    custom_terms=custom_terms,
                    progress=progress,
                )

        finally:
            # Clean up audio file
            if video_info.audio_file and os.path.exists(video_info.audio_file):
                os.remove(video_info.audio_file)
            # Clean up chunk files
            for f in chunk_files_to_clean:
                if os.path.exists(f):
                    os.remove(f)

    def _run_short_video(
        self,
        video_info: VideoInfo,
        language: Optional[str],
        skip_correction: bool,
        custom_terms: Optional[list[str]],
        progress: Callable,
    ) -> TranscriptArtifacts:
        """Single-pass pipeline for short videos."""
        # Transcribe
        progress(JobStatus.TRANSCRIBING, 40, "Whisper 轉錄中...")
        transcript_result = self.transcriber.transcribe(
            video_info.audio_file,
            language=language,
            prompt=video_info.title,
        )
        original_text = transcript_result.text

        # Correct (optional)
        if skip_correction:
            corrected_text = original_text
        else:
            progress(JobStatus.CORRECTING, 70, "GPT 校正中...")
            corrected_text = self._correct_text(
                original_text, video_info, custom_terms
            )

        # Diff
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

    def _run_long_video(
        self,
        video_info: VideoInfo,
        language: Optional[str],
        skip_correction: bool,
        custom_terms: Optional[list[str]],
        progress: Callable,
        job_id: str,
        chunk_files_to_clean: list[str],
    ) -> TranscriptArtifacts:
        """Chunked pipeline for long videos."""
        # 2. Generate chunk files
        progress(JobStatus.TRANSCRIBING, 15, "分割音訊段落中...")
        chunk_dir = os.path.join(self.download_dir, f"{job_id}_chunks")
        os.makedirs(chunk_dir, exist_ok=True)

        chunk_artifacts = generate_chunk_files(
            audio_file=video_info.audio_file,
            total_duration=video_info.duration,
            output_dir=chunk_dir,
            job_id=job_id,
        )

        # Track chunk files for cleanup (skip original audio reference)
        for ca in chunk_artifacts:
            if ca.file_path != video_info.audio_file:
                chunk_files_to_clean.append(ca.file_path)

        total_chunks = len(chunk_artifacts)
        chunk_transcripts: list[ChunkTranscript] = []
        detected_language = language or ""

        # 3. Transcribe + correct each chunk
        for i, ca in enumerate(chunk_artifacts):
            chunk_pct = 20 + int(60 * i / total_chunks)
            progress(
                JobStatus.TRANSCRIBING,
                chunk_pct,
                f"轉錄段落 {i + 1}/{total_chunks}...",
            )

            # Transcribe with timestamps to get segments
            ts_result = self.transcriber.transcribe_with_timestamps(
                ca.file_path,
                language=language,
                prompt=video_info.title,
            )

            raw_text = ts_result["text"]
            segments = [
                Segment(start=s["start"], end=s["end"], text=s["text"])
                for s in ts_result.get("segments", [])
            ]

            # Use first chunk's detected language if auto-detecting
            if not detected_language and ts_result.get("language"):
                detected_language = ts_result["language"]

            # Correct chunk (optional)
            if skip_correction:
                corrected_text = raw_text
            else:
                progress(
                    JobStatus.CORRECTING,
                    chunk_pct + 5,
                    f"校正段落 {i + 1}/{total_chunks}...",
                )
                corrected_text = self._correct_text(
                    raw_text, video_info, custom_terms
                )

            chunk_transcripts.append(
                ChunkTranscript(
                    chunk_index=ca.index,
                    chunk_start=ca.start_time,
                    chunk_end=ca.end_time,
                    segments=segments,
                    raw_text=raw_text,
                    corrected_text=corrected_text,
                )
            )

        # 4. Merge chunks
        progress(JobStatus.MERGING, 82, "合併轉錄段落中...")
        merged = merge_chunks(chunk_transcripts)

        # 5. Consistency pass (skip when correction was skipped so
        #    corrected_text stays identical to the merged raw text)
        if skip_correction:
            final_corrected = merged.raw_text
        else:
            progress(JobStatus.MERGING, 85, "一致性校正中...")
            final_corrected = consistency_pass(merged.corrected_text)

        # 6. Diff (merged raw vs final corrected)
        progress(JobStatus.COMPLETED, 90, "產生差異比較...")
        diff_result = self.diff_viewer.compare(merged.raw_text, final_corrected)
        diff_inline = self.diff_viewer.get_inline_diff(merged.raw_text, final_corrected)

        return TranscriptArtifacts(
            video_info=video_info,
            original_text=merged.raw_text,
            corrected_text=final_corrected,
            language=detected_language,
            similarity_ratio=diff_result.similarity_ratio,
            change_count=diff_result.change_count,
            diff_inline=diff_inline,
            is_merged=True,
            chunk_count=merged.chunk_count,
            segments_before_dedup=merged.segments_before_dedup,
            segments_after_dedup=merged.segments_after_dedup,
            consistency_text=final_corrected,
        )

    def _correct_text(
        self,
        text: str,
        video_info: VideoInfo,
        custom_terms: Optional[list[str]],
    ) -> str:
        """Run GPT correction on text."""
        context = f"影片標題：{video_info.title}\n頻道：{video_info.channel}"
        if custom_terms:
            return self.corrector.correct_with_terms(
                text, terms=custom_terms, context=context
            )
        return self.corrector.correct(text, context=context)
