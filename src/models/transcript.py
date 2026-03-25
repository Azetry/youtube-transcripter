"""Canonical transcript artifacts model."""

from dataclasses import dataclass
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
