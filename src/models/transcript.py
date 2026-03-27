"""Canonical transcript artifacts model."""

from dataclasses import dataclass, field
from typing import Optional

from src.youtube_extractor import VideoInfo


@dataclass
class TranscriptArtifacts:
    """Holds all outputs from a transcription job.

    This is the canonical result model shared by CLI and API.
    """
    video_info: VideoInfo
    original_text: str
    corrected_text: str
    language: str
    similarity_ratio: float = 0.0
    change_count: int = 0
    diff_inline: str = ""
    saved_files: Optional[dict[str, str]] = None

    # Merge metadata (populated only for long-video chunked pipeline)
    is_merged: bool = False
    chunk_count: int = 0
    segments_before_dedup: int = 0
    segments_after_dedup: int = 0
    consistency_text: str = ""

    # Speaker attribution metadata (populated only when attribution requested)
    speaker_attribution_enabled: bool = False
    speaker_strategy: str = ""
    speaker_count: int = 0
    speaker_segments: Optional[list[dict]] = None
