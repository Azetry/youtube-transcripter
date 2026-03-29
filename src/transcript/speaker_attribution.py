"""Speaker attribution — strategy-based speaker labeling for transcripts.

Strategy abstraction (v2):
    - ``SpeakerAttributionStrategy`` — protocol for attribution backends
    - ``AttributionResult`` — structured output from any strategy
    - ``PauseHeuristicStrategy`` — pause-based heuristic (default/fallback)
    - ``PyannoteStrategy`` — real post-hoc diarization via pyannote.audio
    - ``get_strategy`` / ``list_strategies`` / ``describe_strategies`` — registry helpers
    - ``DEFAULT_STRATEGY`` — identifier of the default strategy

Backward-compatible helpers (v1 surface):
    - ``attribute_speakers`` — module-level function delegating to heuristic
    - ``count_speakers`` / ``segments_to_dicts`` — utility functions
    - ``STRATEGY_ID`` — alias for the heuristic strategy identifier
"""

from __future__ import annotations

import logging
import os
import string
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from src.transcript.models import Segment, SpeakerInfo

# ---------------------------------------------------------------------------
# Strategy protocol & result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttributionResult:
    """Output of a speaker attribution strategy.

    Attributes:
        segments: Segments with ``SpeakerInfo`` populated.
        strategy_id: Machine-readable identifier for the strategy that
            produced this result (e.g. ``"pause_heuristic_v1"``).
        speaker_count: Number of distinct speakers detected.
        metadata: Optional extra metadata the strategy wants to surface
            (e.g. model version, confidence stats).
    """

    segments: list[Segment]
    strategy_id: str
    speaker_count: int
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class SpeakerAttributionStrategy(Protocol):
    """Interface every speaker attribution backend must satisfy."""

    @property
    def strategy_id(self) -> str:
        """Stable machine-readable identifier (e.g. ``'pause_heuristic_v1'``)."""
        ...

    def attribute(
        self,
        segments: list[Segment],
        *,
        chunk_index: int | None = None,
        audio_file: str | None = None,
    ) -> AttributionResult:
        """Run attribution on *segments* and return an ``AttributionResult``.

        Args:
            segments: Ordered transcript segments to attribute.
            chunk_index: Optional chunk index to attach to output segments.
            audio_file: Path to the audio file.  Required by backends that
                perform real diarization (e.g. ``pyannote_v1``); ignored by
                text-only strategies like the pause heuristic.
        """
        ...


# ---------------------------------------------------------------------------
# Pause-based heuristic strategy (v1)
# ---------------------------------------------------------------------------

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


class PauseHeuristicStrategy:
    """Pause-based heuristic speaker attribution.

    Detects speaker turns at gaps exceeding ``pause_threshold`` seconds.
    All attributions are marked ``"predicted"`` with moderate confidence.

    This is the default / fallback strategy used when no real diarization
    backend is requested.
    """

    def __init__(
        self,
        *,
        pause_threshold: float = PAUSE_THRESHOLD,
        base_confidence: float = BASE_CONFIDENCE,
    ) -> None:
        self._pause_threshold = pause_threshold
        self._base_confidence = base_confidence

    @property
    def strategy_id(self) -> str:
        return STRATEGY_ID

    def attribute(
        self,
        segments: list[Segment],
        *,
        chunk_index: int | None = None,
        audio_file: str | None = None,
    ) -> AttributionResult:
        """Assign speaker labels using pause-based heuristic."""
        if not segments:
            return AttributionResult(
                segments=[],
                strategy_id=self.strategy_id,
                speaker_count=0,
            )

        attributed: list[Segment] = []
        current_speaker_idx = 0

        for i, seg in enumerate(segments):
            if i > 0:
                gap = seg.start - segments[i - 1].end
                if gap >= self._pause_threshold:
                    current_speaker_idx += 1

            # Slightly vary confidence based on segment duration
            seg_duration = seg.end - seg.start
            confidence = self._base_confidence
            if seg_duration < 1.0:
                confidence = max(0.2, self._base_confidence - 0.1)
            elif seg_duration > 5.0:
                confidence = min(0.6, self._base_confidence + 0.1)

            speaker = SpeakerInfo(
                label=_speaker_label(current_speaker_idx),
                confidence=round(confidence, 2),
                attribution_mode="predicted",
            )

            attributed.append(
                Segment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text,
                    speaker=speaker,
                    chunk_index=chunk_index,
                )
            )

        speaker_count = len({s.speaker.label for s in attributed if s.speaker})

        return AttributionResult(
            segments=attributed,
            strategy_id=self.strategy_id,
            speaker_count=speaker_count,
            metadata={
                "pause_threshold": self._pause_threshold,
                "base_confidence": self._base_confidence,
            },
        )


# ---------------------------------------------------------------------------
# Pyannote post-hoc diarization strategy
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

PYANNOTE_STRATEGY_ID = "pyannote_v1"
_PYANNOTE_MODEL = "pyannote/speaker-diarization-3.1"


class PyannoteStrategy:
    """Real post-hoc speaker diarization via pyannote.audio.

    Runs the pyannote speaker-diarization pipeline on the audio file,
    then aligns the resulting speaker turns with Whisper transcript
    segments using temporal overlap.

    Requires:
        - ``pyannote.audio`` installed (optional dependency).
        - A Hugging Face auth token with access to the pyannote model,
          passed via ``auth_token`` or the ``PYANNOTE_AUTH_TOKEN`` env var.
    """

    def __init__(self, *, auth_token: str | None = None) -> None:
        self._auth_token = auth_token or os.environ.get("PYANNOTE_AUTH_TOKEN")
        self._pipeline: object | None = None  # lazy-loaded

    @property
    def strategy_id(self) -> str:
        return PYANNOTE_STRATEGY_ID

    # -- lazy pipeline loading -----------------------------------------------

    def _get_pipeline(self) -> object:
        """Return the pyannote pipeline, loading it on first call."""
        if self._pipeline is not None:
            return self._pipeline

        try:
            from pyannote.audio import Pipeline  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "pyannote.audio is required for the pyannote_v1 strategy. "
                "Install with: pip install pyannote.audio"
            ) from exc

        if not self._auth_token:
            raise RuntimeError(
                "A Hugging Face auth token is required for pyannote. "
                "Set PYANNOTE_AUTH_TOKEN or pass auth_token to the constructor."
            )

        logger.info("Loading pyannote pipeline %s …", _PYANNOTE_MODEL)
        self._pipeline = Pipeline.from_pretrained(
            _PYANNOTE_MODEL,
            use_auth_token=self._auth_token,
        )
        return self._pipeline

    # -- core attribution ----------------------------------------------------

    def attribute(
        self,
        segments: list[Segment],
        *,
        chunk_index: int | None = None,
        audio_file: str | None = None,
    ) -> AttributionResult:
        """Run pyannote diarization and align with transcript segments."""
        if not segments:
            return AttributionResult(
                segments=[],
                strategy_id=self.strategy_id,
                speaker_count=0,
            )

        if not audio_file:
            raise ValueError(
                "PyannoteStrategy requires an audio_file path. "
                "Pass audio_file= when calling attribute()."
            )

        pipeline = self._get_pipeline()
        diarization = pipeline(audio_file)  # type: ignore[operator]

        # Collect speaker turns: [(start, end, label), ...]
        speaker_turns: list[tuple[float, float, str]] = [
            (turn.start, turn.end, speaker_label)
            for turn, _, speaker_label in diarization.itertracks(yield_label=True)
        ]

        # Deterministic label mapping: pyannote's SPEAKER_00 → Speaker A, etc.
        unique_speakers = sorted({t[2] for t in speaker_turns})
        label_map = {s: _speaker_label(i) for i, s in enumerate(unique_speakers)}

        attributed = _align_segments_to_turns(
            segments, speaker_turns, label_map, chunk_index
        )

        speaker_count = len({s.speaker.label for s in attributed if s.speaker})

        return AttributionResult(
            segments=attributed,
            strategy_id=self.strategy_id,
            speaker_count=speaker_count,
            metadata={
                "model": _PYANNOTE_MODEL,
                "diarization_turns": len(speaker_turns),
            },
        )


# Alignment policy constants
# Overlap ratio below this is treated as "unknown" — too weak to trust.
MIN_OVERLAP_RATIO = 0.15
# When the top-two overlapping turns are within this relative margin of each
# other, the assignment is ambiguous and confidence is capped at "predicted".
AMBIGUITY_MARGIN = 0.20


def _align_segments_to_turns(
    segments: list[Segment],
    speaker_turns: list[tuple[float, float, str]],
    label_map: dict[str, str],
    chunk_index: int | None,
) -> list[Segment]:
    """Align transcript segments to diarization speaker turns by overlap.

    For each segment, the speaker turn with the largest temporal overlap
    is selected.  Conservative policy:

    * **No overlap** → ``"unknown"`` with confidence 0.1.
    * **Overlap ratio < MIN_OVERLAP_RATIO** → ``"unknown"`` — the overlap
      is too small to be meaningful.
    * **Two turns with near-equal overlap** (within ``AMBIGUITY_MARGIN``)
      → confidence capped and mode forced to ``"predicted"`` even if the
      best overlap ratio exceeds 0.5.
    * Otherwise → ``"confident"`` (ratio > 0.5) or ``"predicted"``.
    """
    attributed: list[Segment] = []

    for seg in segments:
        best_speaker: str | None = None
        best_overlap = 0.0
        second_best_overlap = 0.0

        for turn_start, turn_end, speaker_label in speaker_turns:
            overlap = min(seg.end, turn_end) - max(seg.start, turn_start)
            if overlap > best_overlap:
                second_best_overlap = best_overlap
                best_overlap = overlap
                best_speaker = speaker_label
            elif overlap > second_best_overlap:
                second_best_overlap = overlap

        seg_duration = seg.end - seg.start
        overlap_ratio = (
            best_overlap / seg_duration
            if best_speaker is not None and best_overlap > 0 and seg_duration > 0
            else 0.0
        )

        if best_speaker is not None and best_overlap > 0 and overlap_ratio >= MIN_OVERLAP_RATIO:
            # Detect multi-turn ambiguity: top-two overlaps are close
            ambiguous = (
                second_best_overlap > 0
                and best_overlap > 0
                and (best_overlap - second_best_overlap) / best_overlap <= AMBIGUITY_MARGIN
            )

            # Scale confidence: 0.6 base + up to 0.35 from overlap ratio
            confidence = round(min(0.95, 0.6 + 0.35 * overlap_ratio), 2)

            if ambiguous:
                # Cap confidence and force "predicted" — we can't reliably
                # choose between two nearly-equal turns.
                confidence = round(min(confidence, 0.65), 2)
                mode = "predicted"
            else:
                mode = "confident" if overlap_ratio > 0.5 else "predicted"

            speaker_info = SpeakerInfo(
                label=label_map[best_speaker],
                confidence=confidence,
                attribution_mode=mode,
            )
        else:
            speaker_info = SpeakerInfo(
                label="Speaker ?",
                confidence=0.1,
                attribution_mode="unknown",
            )

        attributed.append(
            Segment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                speaker=speaker_info,
                chunk_index=chunk_index,
            )
        )

    return attributed


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

DEFAULT_STRATEGY = STRATEGY_ID

_REGISTRY: dict[str, type[SpeakerAttributionStrategy]] = {
    STRATEGY_ID: PauseHeuristicStrategy,  # type: ignore[dict-item]
    PYANNOTE_STRATEGY_ID: PyannoteStrategy,  # type: ignore[dict-item]
}

_STRATEGY_DESCRIPTIONS: dict[str, str] = {
    STRATEGY_ID: (
        "Pause-based heuristic. Detects speaker changes at silence gaps >= 2s. "
        "Fast, no extra dependencies. Accuracy: low (best-effort labels). "
        "Use for: quick speaker segmentation when diarization quality is not critical."
    ),
    PYANNOTE_STRATEGY_ID: (
        "Real diarization via pyannote.audio (model: pyannote/speaker-diarization-3.1). "
        "Requires: pip install pyannote.audio + PYANNOTE_AUTH_TOKEN env var "
        "(Hugging Face token with model access). "
        "Accuracy: high for 2-3 speaker interviews/podcasts. Slower than heuristic."
    ),
}


def get_strategy(name: str | None = None) -> SpeakerAttributionStrategy:
    """Return a strategy instance by name.

    Args:
        name: Strategy identifier. ``None`` or empty string selects the
            default (``pause_heuristic_v1``).

    Raises:
        ValueError: If *name* is not a registered strategy.
    """
    key = name or DEFAULT_STRATEGY
    factory = _REGISTRY.get(key)
    if factory is None:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown speaker attribution strategy {key!r}. "
            f"Available: {available}"
        )
    return factory()


def list_strategies() -> list[str]:
    """Return sorted list of registered strategy identifiers."""
    return sorted(_REGISTRY)


def describe_strategies() -> dict[str, str]:
    """Return a mapping of strategy id to human-readable description."""
    return dict(_STRATEGY_DESCRIPTIONS)


# ---------------------------------------------------------------------------
# Module-level convenience functions (backward compatibility)
# ---------------------------------------------------------------------------


def attribute_speakers(
    segments: list[Segment],
    *,
    pause_threshold: float = PAUSE_THRESHOLD,
    base_confidence: float = BASE_CONFIDENCE,
    chunk_index: int | None = None,
) -> list[Segment]:
    """Assign speaker labels to segments using pause-based heuristic.

    This is a backward-compatible wrapper around ``PauseHeuristicStrategy``.

    Args:
        segments: Ordered list of Segment objects (chunk-relative or global).
        pause_threshold: Seconds of gap that triggers a speaker change.
        base_confidence: Baseline confidence for attributions.
        chunk_index: Optional chunk index to attach to each segment.

    Returns:
        New list of Segment objects with speaker metadata populated.
        Original segments are not mutated (Segment is frozen).
    """
    strategy = PauseHeuristicStrategy(
        pause_threshold=pause_threshold,
        base_confidence=base_confidence,
    )
    result = strategy.attribute(segments, chunk_index=chunk_index)
    return result.segments


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
