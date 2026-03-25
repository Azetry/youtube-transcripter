"""Deterministic audio chunking for long-video transcription.

Generates a chunk plan from audio duration, then produces chunk
audio files via ffmpeg. Default policy: 10-minute target chunks
with 15-second overlap between adjacent segments.
"""

import os
import subprocess
from dataclasses import dataclass
from typing import Optional


# Default chunking policy
DEFAULT_CHUNK_DURATION = 600  # 10 minutes in seconds
DEFAULT_OVERLAP = 15  # 15-second overlap between adjacent chunks

# Videos shorter than this are treated as single-chunk (no splitting needed)
MIN_DURATION_FOR_CHUNKING = DEFAULT_CHUNK_DURATION + 1


@dataclass(frozen=True)
class ChunkPlan:
    """A single planned chunk with time bounds.

    Attributes:
        index: Zero-based chunk index.
        start_time: Start time in seconds (inclusive).
        end_time: End time in seconds (exclusive / capped at duration).
        duration: Audio duration of this chunk in seconds.
        is_last: Whether this is the final chunk.
    """
    index: int
    start_time: float
    end_time: float
    duration: float
    is_last: bool


@dataclass
class ChunkArtifact:
    """A generated chunk audio file on disk.

    Attributes:
        index: Zero-based chunk index.
        start_time: Start time in seconds.
        end_time: End time in seconds.
        file_path: Path to the chunk audio file.
    """
    index: int
    start_time: float
    end_time: float
    file_path: str


def plan_chunks(
    total_duration: float,
    chunk_duration: int = DEFAULT_CHUNK_DURATION,
    overlap: int = DEFAULT_OVERLAP,
) -> list[ChunkPlan]:
    """Compute a deterministic chunk plan from audio duration.

    The plan divides the audio into segments of ``chunk_duration`` seconds,
    with each segment (except the first) starting ``overlap`` seconds before
    the previous segment's end. This ensures spoken content near boundaries
    is captured in at least two chunks for later deduplication.

    If the final chunk would be shorter than ``overlap``, it is merged into
    the previous chunk to avoid a degenerate tiny segment.

    Args:
        total_duration: Total audio length in seconds.
        chunk_duration: Target length per chunk in seconds.
        overlap: Overlap between adjacent chunks in seconds.

    Returns:
        List of ChunkPlan objects covering the full audio duration.
        For short audio (≤ chunk_duration), returns a single chunk.
    """
    if total_duration <= 0:
        raise ValueError(f"total_duration must be positive, got {total_duration}")
    if chunk_duration <= 0:
        raise ValueError(f"chunk_duration must be positive, got {chunk_duration}")
    if overlap < 0:
        raise ValueError(f"overlap must be non-negative, got {overlap}")
    if overlap >= chunk_duration:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_duration ({chunk_duration})"
        )

    # Short audio: single chunk, no splitting
    if total_duration <= chunk_duration:
        return [
            ChunkPlan(
                index=0,
                start_time=0.0,
                end_time=total_duration,
                duration=total_duration,
                is_last=True,
            )
        ]

    chunks: list[ChunkPlan] = []
    step = chunk_duration - overlap
    start = 0.0
    index = 0

    while start < total_duration:
        end = min(start + chunk_duration, total_duration)
        remaining_after = total_duration - end

        # If the leftover after this chunk is too small (< overlap),
        # extend this chunk to the end to avoid a degenerate final chunk.
        if 0 < remaining_after < overlap / 2:
            end = total_duration
            remaining_after = 0

        is_last = end >= total_duration
        chunks.append(
            ChunkPlan(
                index=index,
                start_time=start,
                end_time=end,
                duration=end - start,
                is_last=is_last,
            )
        )

        if is_last:
            break

        start += step
        index += 1

    return chunks


def needs_chunking(
    total_duration: float,
    chunk_duration: int = DEFAULT_CHUNK_DURATION,
) -> bool:
    """Check whether audio of the given duration requires chunking."""
    return total_duration > chunk_duration


def generate_chunk_files(
    audio_file: str,
    total_duration: float,
    output_dir: str,
    job_id: str,
    chunk_duration: int = DEFAULT_CHUNK_DURATION,
    overlap: int = DEFAULT_OVERLAP,
) -> list[ChunkArtifact]:
    """Plan chunks and extract each as a separate audio file via ffmpeg.

    Args:
        audio_file: Path to the source audio file.
        total_duration: Total audio duration in seconds.
        output_dir: Directory to write chunk files into.
        job_id: Job identifier used in chunk filenames.
        chunk_duration: Target chunk length in seconds.
        overlap: Overlap between adjacent chunks in seconds.

    Returns:
        List of ChunkArtifact with paths to the generated files.

    Raises:
        FileNotFoundError: If the source audio file does not exist.
        RuntimeError: If ffmpeg extraction fails.
    """
    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    os.makedirs(output_dir, exist_ok=True)

    plans = plan_chunks(total_duration, chunk_duration, overlap)

    # Single chunk: no need to run ffmpeg, just reference the original
    if len(plans) == 1:
        return [
            ChunkArtifact(
                index=0,
                start_time=0.0,
                end_time=total_duration,
                file_path=audio_file,
            )
        ]

    artifacts: list[ChunkArtifact] = []
    _, ext = os.path.splitext(audio_file)
    ext = ext or ".mp3"

    for plan in plans:
        chunk_path = os.path.join(
            output_dir, f"{job_id}_chunk_{plan.index:03d}{ext}"
        )

        cmd = [
            "ffmpeg",
            "-y",  # overwrite
            "-i", audio_file,
            "-ss", f"{plan.start_time:.3f}",
            "-t", f"{plan.duration:.3f}",
            "-c", "copy",  # stream copy, no re-encoding
            "-loglevel", "error",
            chunk_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed for chunk {plan.index}: {result.stderr.strip()}"
            )

        artifacts.append(
            ChunkArtifact(
                index=plan.index,
                start_time=plan.start_time,
                end_time=plan.end_time,
                file_path=chunk_path,
            )
        )

    return artifacts
