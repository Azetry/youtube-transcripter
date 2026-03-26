"""Shared end-to-end transcription orchestration.

This service owns the transcription pipeline logic that was
previously duplicated between main.py (CLI) and api/main.py (API).
Both entry points now delegate to this single implementation.

Supports two flows:
  - Short video: single-pass transcribe → correct → diff
  - Long video: chunk → transcribe each → correct each → merge → consistency → diff

Unit H5: acquisition is now an explicit phase before transcript
processing.  The service delegates to ThisHostAcquisitionService (H2),
consults the fallback policy (H3), and produces an alternate-host
handoff request (H4 contract) when local acquisition is exhausted.
Actual remote transport is NOT implemented here.
"""

import logging
import os
from dataclasses import dataclass, field
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

from src.services.acquisition_service import (
    AcquisitionResult,
    ThisHostAcquisitionService,
)
from src.services.fallback_policy import (
    FallbackDecision,
    FallbackRoute,
    decide as decide_fallback,
)
from src.integrations.alternate_host import (
    AlternateHostRequest,
    build_request_from_decision,
)

logger = logging.getLogger(__name__)


# Type for an optional progress callback: (status, progress%, message)
ProgressCallback = Callable[[JobStatus, int, str], None]


# ---------------------------------------------------------------------------
# Acquisition-phase result — exposed to callers for diagnostics
# ---------------------------------------------------------------------------

class AcquisitionError(Exception):
    """Raised when audio acquisition fails after all local strategies.

    Attributes:
        acquisition_result: The H2 structured result with attempt history.
        fallback_decision: The H3 routing decision (if computed).
        alternate_host_request: The H4 handoff request (if the policy
            recommended delegating to an alternate host).
    """

    def __init__(
        self,
        message: str,
        *,
        acquisition_result: Optional[AcquisitionResult] = None,
        fallback_decision: Optional[FallbackDecision] = None,
        alternate_host_request: Optional[AlternateHostRequest] = None,
    ) -> None:
        super().__init__(message)
        self.acquisition_result = acquisition_result
        self.fallback_decision = fallback_decision
        self.alternate_host_request = alternate_host_request


@dataclass
class AcquisitionOutcome:
    """Structured result of the acquisition phase.

    On success, ``video_info`` is populated and the transcript pipeline
    continues.  On failure, ``fallback_decision`` and optionally
    ``alternate_host_request`` describe what the orchestrator recommends
    as the next step (but does not execute).
    """
    video_info: Optional[VideoInfo] = None
    success: bool = False
    acquisition_result: Optional[AcquisitionResult] = None
    fallback_decision: Optional[FallbackDecision] = None
    alternate_host_request: Optional[AlternateHostRequest] = None
    diagnostics: dict = field(default_factory=dict)


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
        *,
        originator: str = "",
    ) -> None:
        self.download_dir = download_dir
        self.output_dir = output_dir
        self.extractor = YouTubeExtractor(output_dir=download_dir)
        self.acquisition_service = ThisHostAcquisitionService(self.extractor)
        self.transcriber = WhisperTranscriber()
        self.corrector = TextCorrector()
        self.diff_viewer = DiffViewer()
        self._originator = originator

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

        # 1. Acquire audio via structured acquisition service (H2)
        progress(JobStatus.DOWNLOADING, 5, "音訊取得中...")
        outcome = self._acquire(url, progress)

        if not outcome.success:
            raise AcquisitionError(
                f"Acquisition failed: {outcome.fallback_decision.reason}"
                if outcome.fallback_decision
                else "Acquisition failed with no fallback decision.",
                acquisition_result=outcome.acquisition_result,
                fallback_decision=outcome.fallback_decision,
                alternate_host_request=outcome.alternate_host_request,
            )

        video_info = outcome.video_info
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

    # ------------------------------------------------------------------
    # Acquisition phase (H5 orchestration glue)
    # ------------------------------------------------------------------

    def _acquire(
        self,
        url: str,
        progress: Callable,
    ) -> AcquisitionOutcome:
        """Run the structured acquisition phase.

        1. Try this-host strategies via H2 ThisHostAcquisitionService.
        2. On failure, consult H3 fallback policy.
        3. If policy says DELEGATE_ALTERNATE_HOST, build H4 request
           (actual transport is out of scope).
        4. For local-retry routes (RETRY / ESCALATE / WAIT), do NOT
           re-attempt here — surface the decision so the caller or a
           future retry loop can act on it.
        """
        progress(JobStatus.DOWNLOADING, 8, "嘗試本機取得音訊...")
        acq_result = self.acquisition_service.acquire(url)

        outcome = AcquisitionOutcome(
            acquisition_result=acq_result,
            diagnostics=acq_result.diagnostics(),
        )

        if acq_result.success:
            outcome.video_info = acq_result.video_info
            outcome.success = True
            logger.info(
                "Acquisition succeeded locally (%d attempt(s)).",
                acq_result.strategy_count,
            )
            progress(JobStatus.DOWNLOADING, 10, "音訊取得完成")
            return outcome

        # Local acquisition failed — consult H3 fallback policy
        decision = decide_fallback(acq_result)
        outcome.fallback_decision = decision
        logger.warning(
            "Local acquisition failed [%s]: %s",
            decision.route.value,
            decision.reason,
        )

        if decision.route == FallbackRoute.DELEGATE_ALTERNATE_HOST:
            # Build H4 handoff request (transport NOT executed)
            request = build_request_from_decision(
                url,
                failure_category=decision.failure_category,
                exhausted_modes=decision.exhausted_modes,
                attempt_count=acq_result.strategy_count,
                reason=decision.reason,
                originator=self._originator,
            )
            outcome.alternate_host_request = request
            logger.info(
                "Alternate-host handoff request prepared for %s (originator=%s).",
                url,
                self._originator,
            )

        return outcome

    def acquire_only(self, url: str) -> AcquisitionOutcome:
        """Run acquisition phase without continuing to transcription.

        Useful for diagnostics, dry-runs, and testing the acquisition
        pipeline in isolation.
        """
        def _noop_progress(_s: JobStatus, _p: int, _m: str) -> None:
            pass

        return self._acquire(url, _noop_progress)

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
