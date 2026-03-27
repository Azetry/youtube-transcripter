"""Speaker attribution via pause-based heuristic (v1).

This module assigns generic speaker labels (Speaker A, Speaker B, etc.)
to transcript segments by detecting speaker turns at significant pauses.

Strategy:
    - Gaps > PAUSE_THRESHOLD seconds between consecutive segments
      are treated as potential speaker changes.
    - Speaker labels alternate on each detected turn.
    - All attributions are marked as "predicted" with moderate
      confidence, since no real diarization is performed.
    - Single-segment gaps or very short utterances get lower confidence.

This is an intentionally low-accuracy heuristic.  The value is in
proving the full schema/pipeline/merge infrastructure end-to-end.
A real diarization engine (e.g. pyannote) can replace this function
without any schema or pipeline changes.
"""

from __future__ import annotations

import string

from src.transcript.models import Segment, SpeakerInfo

# Seconds of silence that suggest a speaker change
PAUSE_THRESHOLD = 2.0

# Base confidence for heuristic attributions
BASE_CONFIDENCE = 0.4

# Strategy identifier stored in artifact metadata
STRATEGY_ID = "pause_heuristic_v1"


def _speaker_label(index: int) -> str:
    """Generate a speaker label from an index (0 -> 'Speaker A', 1 -> 'Speaker B', ...)."""
    if index < 26:
        return f"Speaker {string.ascii_uppercase[index]}"
    return f"Speaker {index + 1}"


def attribute_speakers(
    segments: list[Segment],
    *,
    pause_threshold: float = PAUSE_THRESHOLD,
    base_confidence: float = BASE_CONFIDENCE,
    chunk_index: int | None = None,
) -> list[Segment]:
    """Assign speaker labels to segments using pause-based heuristic.

    Args:
        segments: Ordered list of Segment objects (chunk-relative or global).
        pause_threshold: Seconds of gap that triggers a speaker change.
        base_confidence: Baseline confidence for attributions.
        chunk_index: Optional chunk index to attach to each segment.

    Returns:
        New list of Segment objects with speaker metadata populated.
        Original segments are not mutated (Segment is frozen).
    """
    if not segments:
        return []

    attributed: list[Segment] = []
    current_speaker_idx = 0

    for i, seg in enumerate(segments):
        if i > 0:
            gap = seg.start - segments[i - 1].end
            if gap >= pause_threshold:
                current_speaker_idx += 1

        # Slightly vary confidence based on segment duration
        seg_duration = seg.end - seg.start
        confidence = base_confidence
        if seg_duration < 1.0:
            confidence = max(0.2, base_confidence - 0.1)
        elif seg_duration > 5.0:
            confidence = min(0.6, base_confidence + 0.1)

        speaker = SpeakerInfo(
            label=_speaker_label(current_speaker_idx),
            confidence=round(confidence, 2),
            attribution_mode="predicted",
        )

        attributed.append(Segment(
            start=seg.start,
            end=seg.end,
            text=seg.text,
            speaker=speaker,
            chunk_index=chunk_index,
        ))

    return attributed


def count_speakers(segments: list[Segment]) -> int:
    """Count distinct speaker labels in a list of segments."""
    labels = {seg.speaker.label for seg in segments if seg.speaker}
    return len(labels)


def segments_to_dicts(segments: list[Segment]) -> list[dict]:
    """Serialize speaker-aware segments to JSON-compatible dicts."""
    result = []
    for seg in segments:
        d: dict = {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        }
        if seg.speaker:
            d["speaker"] = seg.speaker.to_dict()
        if seg.chunk_index is not None:
            d["chunk_index"] = seg.chunk_index
        result.append(d)
    return result
