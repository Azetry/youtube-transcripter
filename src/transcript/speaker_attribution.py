"""Speaker attribution — strategy-based speaker labeling for transcripts.

Strategy abstraction (v2):
    - ``SpeakerAttributionStrategy`` — protocol for attribution backends
    - ``AttributionResult`` — structured output from any strategy
    - ``PauseHeuristicStrategy`` — pause-based heuristic (default/fallback)
    - ``get_strategy`` / ``list_strategies`` — registry helpers
    - ``DEFAULT_STRATEGY`` — identifier of the default strategy

Backward-compatible helpers (v1 surface):
    - ``attribute_speakers`` — module-level function delegating to heuristic
    - ``count_speakers`` / ``segments_to_dicts`` — utility functions
    - ``STRATEGY_ID`` — alias for the heuristic strategy identifier

A real diarization engine (e.g. pyannote) can be added as a separate
strategy implementation without any schema or pipeline changes.
"""

from __future__ import annotations

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
    ) -> AttributionResult:
        """Run attribution on *segments* and return an ``AttributionResult``."""
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
# Strategy registry
# ---------------------------------------------------------------------------

DEFAULT_STRATEGY = STRATEGY_ID

_REGISTRY: dict[str, type[SpeakerAttributionStrategy]] = {
    STRATEGY_ID: PauseHeuristicStrategy,  # type: ignore[dict-item]
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
