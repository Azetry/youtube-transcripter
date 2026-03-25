"""Merge chunk-level transcripts into a single global transcript.

Pipeline:
    1. map_to_global_timeline  – shift chunk-relative segment timestamps
    2. dedupe_overlap_segments – remove duplicates in overlap regions
    3. merge_chunks            – orchestrate (1) + (2) and build text
    4. consistency_pass        – lightweight final polish on merged text

Each step is a standalone, testable function.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

from src.transcript.models import ChunkTranscript, MergedTranscript, Segment


# ── 4.1  Global timeline mapping ─────────────────────────────────────


def map_to_global_timeline(chunk: ChunkTranscript) -> list[Segment]:
    """Convert chunk-relative segment timestamps to global timestamps.

    Each segment's start/end is offset by the chunk's global start time.
    Segments whose global end would exceed the chunk's global end are
    clamped to the chunk boundary.

    Returns a new list of Segment objects with global timestamps.
    """
    mapped: list[Segment] = []
    for seg in chunk.segments:
        global_start = chunk.chunk_start + seg.start
        global_end = chunk.chunk_start + seg.end
        # Clamp to chunk boundary
        global_end = min(global_end, chunk.chunk_end)
        mapped.append(Segment(start=global_start, end=global_end, text=seg.text))
    return mapped


# ── 4.2  Overlap deduplication ───────────────────────────────────────

# Segments with similarity >= this threshold are considered duplicates
SIMILARITY_THRESHOLD = 0.7

# Timestamps within this tolerance (seconds) are considered overlapping
TIME_TOLERANCE = 2.0


def _normalize_text(text: str) -> str:
    """Normalize text for similarity comparison.

    Lowercases, strips whitespace, removes punctuation, and collapses
    internal whitespace to single spaces.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    # Remove common punctuation
    text = re.sub("[，。！？、；：\u201c\u201d\u2018\u2019（）\\[\\]【】,.!?;:\"'()\\-\u2013\u2014\u2026]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _text_similarity(a: str, b: str) -> float:
    """Return 0.0–1.0 similarity ratio between two normalized strings."""
    na, nb = _normalize_text(a), _normalize_text(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _timestamps_overlap(seg_a: Segment, seg_b: Segment, tolerance: float = TIME_TOLERANCE) -> bool:
    """Check whether two segments overlap in time within tolerance."""
    return (
        seg_a.start <= seg_b.end + tolerance
        and seg_b.start <= seg_a.end + tolerance
    )


def dedupe_overlap_segments(
    prev_segments: list[Segment],
    next_segments: list[Segment],
    overlap_start: float,
    overlap_end: float,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    time_tolerance: float = TIME_TOLERANCE,
) -> tuple[list[Segment], list[Segment]]:
    """Remove duplicate segments in the overlap region between two chunks.

    Strategy:
        1. Identify segments from each chunk that fall within the overlap
           time window [overlap_start, overlap_end].
        2. For each next-chunk overlap segment, check if a matching
           prev-chunk overlap segment exists (timestamp overlap first,
           text similarity second).
        3. If a match is found the next-chunk segment is dropped
           (prev-chunk's version is kept).

    Returns:
        (kept_prev, kept_next) – filtered segment lists.  Non-overlap
        segments are always kept as-is.
    """
    # Partition prev segments into before-overlap and in-overlap
    prev_before: list[Segment] = []
    prev_overlap: list[Segment] = []
    for s in prev_segments:
        if s.end <= overlap_start:
            prev_before.append(s)
        else:
            prev_overlap.append(s)

    # Partition next segments into in-overlap and after-overlap
    next_overlap: list[Segment] = []
    next_after: list[Segment] = []
    for s in next_segments:
        if s.start < overlap_end:
            next_overlap.append(s)
        else:
            next_after.append(s)

    # Mark next-overlap segments matched by any prev-overlap segment
    matched_next: set[int] = set()
    for ni, ns in enumerate(next_overlap):
        for ps in prev_overlap:
            if _timestamps_overlap(ps, ns, time_tolerance):
                sim = _text_similarity(ps.text, ns.text)
                if sim >= similarity_threshold:
                    matched_next.add(ni)
                    break

    # Keep unmatched next-overlap segments
    surviving_next_overlap = [
        s for i, s in enumerate(next_overlap) if i not in matched_next
    ]

    kept_prev = prev_before + prev_overlap
    kept_next = surviving_next_overlap + next_after
    return kept_prev, kept_next


# ── 4.3  Merge orchestration ─────────────────────────────────────────


def merge_chunks(
    chunks: list[ChunkTranscript],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    time_tolerance: float = TIME_TOLERANCE,
) -> MergedTranscript:
    """Merge an ordered list of chunk transcripts into one global transcript.

    Steps:
        1. Map each chunk's segments to the global timeline.
        2. For each pair of adjacent chunks, deduplicate the overlap region.
        3. Concatenate the surviving segments and text.

    Args:
        chunks: ChunkTranscript objects sorted by chunk_index.
        similarity_threshold: Min similarity to consider segments duplicate.
        time_tolerance: Seconds of tolerance for timestamp overlap check.

    Returns:
        MergedTranscript with global segments and concatenated text.
    """
    if not chunks:
        return MergedTranscript(
            segments=[], raw_text="", corrected_text="",
            chunk_count=0, segments_before_dedup=0, segments_after_dedup=0,
        )

    # Sort by chunk_index for safety
    chunks = sorted(chunks, key=lambda c: c.chunk_index)

    # Single chunk: no merging needed
    if len(chunks) == 1:
        global_segs = map_to_global_timeline(chunks[0])
        return MergedTranscript(
            segments=global_segs,
            raw_text=chunks[0].raw_text,
            corrected_text=chunks[0].corrected_text,
            chunk_count=1,
            segments_before_dedup=len(global_segs),
            segments_after_dedup=len(global_segs),
            overlap_regions_processed=0,
        )

    # Map all chunks to global timeline
    global_segments_per_chunk: list[list[Segment]] = [
        map_to_global_timeline(c) for c in chunks
    ]

    total_before = sum(len(segs) for segs in global_segments_per_chunk)
    overlap_regions = 0

    # Pairwise dedup across adjacent chunks
    for i in range(len(chunks) - 1):
        curr_chunk = chunks[i]
        next_chunk = chunks[i + 1]

        # Overlap region: from next chunk's start to current chunk's end
        overlap_start = next_chunk.chunk_start
        overlap_end = curr_chunk.chunk_end

        if overlap_start < overlap_end:
            kept_prev, kept_next = dedupe_overlap_segments(
                global_segments_per_chunk[i],
                global_segments_per_chunk[i + 1],
                overlap_start,
                overlap_end,
                similarity_threshold,
                time_tolerance,
            )
            global_segments_per_chunk[i] = kept_prev
            global_segments_per_chunk[i + 1] = kept_next
            overlap_regions += 1

    # Flatten into one list
    all_segments: list[Segment] = []
    for segs in global_segments_per_chunk:
        all_segments.extend(segs)

    # Build merged text from segments
    merged_raw_parts: list[str] = []
    merged_corrected_parts: list[str] = []

    for i, chunk in enumerate(chunks):
        chunk_segs = global_segments_per_chunk[i]
        # Raw text: join segment texts for this chunk's surviving segments
        chunk_raw_text = " ".join(s.text for s in chunk_segs).strip()
        if chunk_raw_text:
            merged_raw_parts.append(chunk_raw_text)

        # For corrected text, we can't trivially map back to per-segment
        # corrected text since correction is done at chunk level.
        # Strategy: if dedup removed segments from the start of a non-first
        # chunk, we trim the corrected text proportionally using the
        # surviving segments as a guide. For simplicity and correctness,
        # use the chunk's corrected text but trim the overlap portion
        # that was already covered by the previous chunk.

    # For corrected text: use a simpler sentence-boundary approach
    merged_corrected = _merge_corrected_texts(chunks, global_segments_per_chunk)
    merged_raw = "\n\n".join(merged_raw_parts) if merged_raw_parts else ""

    return MergedTranscript(
        segments=all_segments,
        raw_text=merged_raw,
        corrected_text=merged_corrected,
        chunk_count=len(chunks),
        segments_before_dedup=total_before,
        segments_after_dedup=len(all_segments),
        overlap_regions_processed=overlap_regions,
    )


def _merge_corrected_texts(
    chunks: list[ChunkTranscript],
    surviving_segments: list[list[Segment]],
) -> str:
    """Merge corrected texts, trimming overlap portions from later chunks.

    For each chunk after the first, if some leading segments were deduped
    away, we estimate how much of the corrected text corresponds to the
    removed portion and skip it. This uses the ratio of surviving segments
    to total segments as a proxy.
    """
    parts: list[str] = []

    for i, chunk in enumerate(chunks):
        if i == 0:
            parts.append(chunk.corrected_text.strip())
            continue

        surviving = surviving_segments[i]
        original_count = len(chunk.segments)

        if not surviving:
            # All segments deduped — skip this chunk's corrected text
            continue

        if original_count == 0 or len(surviving) == original_count:
            # No dedup happened — use full text
            parts.append(chunk.corrected_text.strip())
            continue

        # Estimate fraction of text to skip (segments removed from the front)
        removed_count = original_count - len(surviving)
        skip_ratio = removed_count / original_count

        # Split corrected text into rough sentence boundaries and skip
        # the estimated front portion
        text = chunk.corrected_text.strip()
        sentences = _split_sentences(text)
        skip_count = max(1, round(len(sentences) * skip_ratio))
        remaining = sentences[skip_count:]
        if remaining:
            parts.append(" ".join(remaining).strip())
        # If nothing remains after trimming, the content was fully duplicated

    return "\n\n".join(parts) if parts else ""


def _split_sentences(text: str) -> list[str]:
    """Split text into rough sentence-level chunks."""
    # Split on Chinese/English sentence endings
    parts = re.split(r'(?<=[。！？.!?])\s*', text)
    return [p for p in parts if p.strip()]


# ── 4.4  Lightweight consistency pass ────────────────────────────────


def consistency_pass(
    merged_text: str,
    fix_whitespace: bool = True,
    fix_repeated_phrases: bool = True,
) -> str:
    """Run a lightweight consistency pass on merged corrected text.

    This does NOT call an LLM — it applies deterministic text cleanups
    that commonly arise from chunk merging:

        - Collapse excessive whitespace and blank lines.
        - Remove obviously repeated phrases at chunk join boundaries.
        - Normalize paragraph breaks.

    The pass is intentionally conservative to avoid rewriting meaning.
    """
    if not merged_text:
        return merged_text

    text = merged_text

    if fix_whitespace:
        # Collapse runs of 3+ newlines to double newline (paragraph break)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Collapse multiple spaces to single
        text = re.sub(r"[ \t]{2,}", " ", text)
        # Remove leading/trailing whitespace per line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

    if fix_repeated_phrases:
        text = _remove_boundary_repeats(text)

    return text.strip()


def _remove_boundary_repeats(text: str) -> str:
    """Remove short repeated phrases that appear at paragraph boundaries.

    When chunk corrected texts are joined, the last sentence of one chunk
    and the first sentence of the next may be near-identical.  This
    function detects and removes such duplicates.
    """
    paragraphs = text.split("\n\n")
    if len(paragraphs) < 2:
        return text

    cleaned: list[str] = [paragraphs[0]]
    for i in range(1, len(paragraphs)):
        prev = paragraphs[i - 1]
        curr = paragraphs[i]

        prev_sentences = _split_sentences(prev)
        curr_sentences = _split_sentences(curr)

        if prev_sentences and curr_sentences:
            last_prev = _normalize_text(prev_sentences[-1])
            first_curr = _normalize_text(curr_sentences[0])

            if last_prev and first_curr:
                sim = SequenceMatcher(None, last_prev, first_curr).ratio()
                if sim >= 0.8:
                    # Drop the duplicated first sentence of the current paragraph
                    remaining = curr_sentences[1:]
                    if remaining:
                        cleaned.append(" ".join(remaining))
                    continue

        cleaned.append(curr)

    return "\n\n".join(cleaned)
