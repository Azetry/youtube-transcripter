"""Tests for transcript merger (Unit D – Tasks 4.1–4.5).

Covers:
  - Global timeline mapping
  - Overlap deduplication (timestamps + text similarity)
  - Full merge orchestration (single & multi-chunk)
  - Lightweight consistency pass
  - Schema v3 merge-field persistence
"""

import json
import sqlite3

import pytest

from src.transcript.models import ChunkTranscript, MergedTranscript, Segment
from src.transcript.merger import (
    map_to_global_timeline,
    dedupe_overlap_segments,
    merge_chunks,
    consistency_pass,
    _normalize_text,
    _text_similarity,
    _timestamps_overlap,
    SIMILARITY_THRESHOLD,
    TIME_TOLERANCE,
)
from src.storage.schema import bootstrap, SCHEMA_VERSION


# ── Helpers ──────────────────────────────────────────────────────────


def _seg(start: float, end: float, text: str) -> Segment:
    """Shorthand segment constructor."""
    return Segment(start=start, end=end, text=text)


def _chunk(
    index: int,
    chunk_start: float,
    chunk_end: float,
    segments: list[Segment],
    raw: str = "",
    corrected: str = "",
) -> ChunkTranscript:
    return ChunkTranscript(
        chunk_index=index,
        chunk_start=chunk_start,
        chunk_end=chunk_end,
        segments=segments,
        raw_text=raw or " ".join(s.text for s in segments),
        corrected_text=corrected or " ".join(s.text for s in segments),
    )


# ── 4.1  Global timeline mapping ────────────────────────────────────


class TestMapToGlobalTimeline:
    def test_single_segment_offset(self):
        """Chunk-relative timestamps are shifted by chunk_start."""
        chunk = _chunk(
            0, chunk_start=100.0, chunk_end=200.0,
            segments=[_seg(0.0, 10.0, "hello")],
        )
        result = map_to_global_timeline(chunk)
        assert len(result) == 1
        assert result[0].start == 100.0
        assert result[0].end == 110.0
        assert result[0].text == "hello"

    def test_multiple_segments(self):
        chunk = _chunk(
            0, chunk_start=50.0, chunk_end=200.0,
            segments=[
                _seg(0.0, 5.0, "a"),
                _seg(5.0, 10.0, "b"),
                _seg(10.0, 15.0, "c"),
            ],
        )
        result = map_to_global_timeline(chunk)
        assert result[0].start == 50.0
        assert result[1].start == 55.0
        assert result[2].start == 60.0

    def test_zero_offset_chunk(self):
        """First chunk at time 0 — no shift."""
        chunk = _chunk(
            0, chunk_start=0.0, chunk_end=600.0,
            segments=[_seg(0.0, 5.0, "first")],
        )
        result = map_to_global_timeline(chunk)
        assert result[0].start == 0.0
        assert result[0].end == 5.0

    def test_segment_clamped_to_chunk_end(self):
        """Segment end beyond chunk boundary is clamped."""
        chunk = _chunk(
            0, chunk_start=100.0, chunk_end=110.0,
            segments=[_seg(0.0, 20.0, "long segment")],
        )
        result = map_to_global_timeline(chunk)
        assert result[0].end == 110.0  # clamped, not 120.0

    def test_empty_chunk(self):
        chunk = _chunk(0, chunk_start=0.0, chunk_end=600.0, segments=[])
        assert map_to_global_timeline(chunk) == []

    def test_preserves_text(self):
        chunk = _chunk(
            1, chunk_start=585.0, chunk_end=1185.0,
            segments=[_seg(0.0, 5.0, "中文測試")],
        )
        result = map_to_global_timeline(chunk)
        assert result[0].text == "中文測試"


# ── 4.2  Overlap deduplication ───────────────────────────────────────


class TestNormalizeText:
    def test_lowercase_and_strip(self):
        assert _normalize_text("  Hello World  ") == "hello world"

    def test_removes_punctuation(self):
        assert _normalize_text("你好，世界！") == "你好世界"

    def test_collapses_whitespace(self):
        assert _normalize_text("a   b  c") == "a b c"

    def test_empty(self):
        assert _normalize_text("") == ""


class TestTextSimilarity:
    def test_identical_strings(self):
        assert _text_similarity("hello world", "hello world") == 1.0

    def test_empty_strings(self):
        assert _text_similarity("", "") == 1.0

    def test_one_empty(self):
        assert _text_similarity("hello", "") == 0.0

    def test_similar_strings(self):
        sim = _text_similarity("hello world", "hello worl")
        assert sim > 0.8

    def test_different_strings(self):
        sim = _text_similarity("hello", "goodbye")
        assert sim < 0.5


class TestTimestampsOverlap:
    def test_overlapping(self):
        a = _seg(10.0, 15.0, "")
        b = _seg(13.0, 18.0, "")
        assert _timestamps_overlap(a, b) is True

    def test_non_overlapping(self):
        a = _seg(10.0, 15.0, "")
        b = _seg(20.0, 25.0, "")
        assert _timestamps_overlap(a, b) is False

    def test_within_tolerance(self):
        a = _seg(10.0, 15.0, "")
        b = _seg(16.5, 20.0, "")
        # Gap = 1.5s, default tolerance = 2.0s → overlap
        assert _timestamps_overlap(a, b, tolerance=2.0) is True

    def test_outside_tolerance(self):
        a = _seg(10.0, 15.0, "")
        b = _seg(18.0, 20.0, "")
        assert _timestamps_overlap(a, b, tolerance=2.0) is False


class TestDedupeOverlapSegments:
    def test_identical_overlap_segment_removed(self):
        """A segment in next that matches prev by time+text is removed."""
        prev = [
            _seg(580.0, 585.0, "before overlap"),
            _seg(585.0, 590.0, "overlap content"),
            _seg(590.0, 595.0, "more overlap"),
        ]
        next_ = [
            _seg(585.0, 590.0, "overlap content"),
            _seg(590.0, 595.0, "more overlap"),
            _seg(595.0, 600.0, "brand new unique content"),
        ]
        kept_prev, kept_next = dedupe_overlap_segments(
            prev, next_,
            overlap_start=585.0, overlap_end=600.0,
        )
        # prev keeps all
        assert len(kept_prev) == 3
        # next loses the two duplicates, keeps the one after overlap
        assert len(kept_next) == 1
        assert kept_next[0].text == "brand new unique content"

    def test_similar_but_not_identical_text(self):
        """Segments with similar (>threshold) text are still deduped."""
        prev = [_seg(585.0, 590.0, "這是重疊的內容")]
        next_ = [
            _seg(585.0, 590.0, "這是重疊的内容"),  # simplified char variant
            _seg(595.0, 600.0, "unique"),
        ]
        kept_prev, kept_next = dedupe_overlap_segments(
            prev, next_,
            overlap_start=585.0, overlap_end=600.0,
        )
        assert len(kept_next) == 1
        assert kept_next[0].text == "unique"

    def test_different_text_not_deduped(self):
        """Segments with different text are kept even if timestamps overlap."""
        prev = [_seg(585.0, 590.0, "apples")]
        next_ = [
            _seg(586.0, 591.0, "completely different topic here"),
            _seg(595.0, 600.0, "after"),
        ]
        kept_prev, kept_next = dedupe_overlap_segments(
            prev, next_,
            overlap_start=585.0, overlap_end=600.0,
        )
        # Both next segments kept — text too different
        assert len(kept_next) == 2

    def test_no_overlap_region(self):
        """When overlap region is empty, all segments are kept."""
        prev = [_seg(0.0, 5.0, "a")]
        next_ = [_seg(600.0, 605.0, "b")]
        kept_prev, kept_next = dedupe_overlap_segments(
            prev, next_,
            overlap_start=600.0, overlap_end=600.0,
        )
        assert len(kept_prev) == 1
        assert len(kept_next) == 1

    def test_segments_before_overlap_always_kept(self):
        """Prev segments before the overlap start are always kept."""
        prev = [
            _seg(0.0, 100.0, "early"),
            _seg(585.0, 590.0, "overlap"),
        ]
        next_ = [_seg(585.0, 590.0, "overlap")]
        kept_prev, kept_next = dedupe_overlap_segments(
            prev, next_,
            overlap_start=585.0, overlap_end=600.0,
        )
        assert len(kept_prev) == 2
        assert kept_prev[0].text == "early"


# ── 4.3  Merge orchestration ────────────────────────────────────────


class TestMergeChunks:
    def test_empty_input(self):
        result = merge_chunks([])
        assert result.segments == []
        assert result.raw_text == ""
        assert result.chunk_count == 0

    def test_single_chunk(self):
        chunk = _chunk(
            0, chunk_start=0.0, chunk_end=300.0,
            segments=[_seg(0.0, 5.0, "hello"), _seg(5.0, 10.0, "world")],
            raw="hello world",
            corrected="Hello world.",
        )
        result = merge_chunks([chunk])
        assert result.chunk_count == 1
        assert result.overlap_regions_processed == 0
        assert len(result.segments) == 2
        assert result.segments[0].start == 0.0
        assert result.corrected_text == "Hello world."

    def test_two_chunks_with_overlap_dedup(self):
        """Two overlapping chunks: duplicate segments in overlap removed."""
        chunk0 = _chunk(
            0, chunk_start=0.0, chunk_end=600.0,
            segments=[
                _seg(0.0, 290.0, "beginning"),
                _seg(290.0, 585.0, "middle"),
                _seg(585.0, 600.0, "overlap part"),
            ],
            raw="beginning middle overlap part",
            corrected="Beginning. Middle. Overlap part.",
        )
        chunk1 = _chunk(
            1, chunk_start=585.0, chunk_end=1200.0,
            segments=[
                _seg(0.0, 15.0, "overlap part"),  # duplicate
                _seg(15.0, 300.0, "after overlap"),
                _seg(300.0, 615.0, "ending"),
            ],
            raw="overlap part after overlap ending",
            corrected="Overlap part. After overlap. Ending.",
        )
        result = merge_chunks([chunk0, chunk1])
        assert result.chunk_count == 2
        assert result.overlap_regions_processed == 1
        assert result.segments_before_dedup == 6
        # The "overlap part" from chunk1 should be deduped
        assert result.segments_after_dedup == 5
        # Check that global timestamps are correct
        # chunk1's "after overlap" starts at 585+15=600
        after_seg = [s for s in result.segments if s.text == "after overlap"]
        assert len(after_seg) == 1
        assert after_seg[0].start == 600.0

    def test_three_chunks(self):
        """Three chunks merge with two overlap boundaries."""
        chunk0 = _chunk(
            0, chunk_start=0.0, chunk_end=600.0,
            segments=[_seg(0.0, 590.0, "A"), _seg(590.0, 600.0, "overlap1")],
        )
        chunk1 = _chunk(
            1, chunk_start=585.0, chunk_end=1185.0,
            segments=[
                _seg(0.0, 15.0, "overlap1"),
                _seg(15.0, 590.0, "B"),
                _seg(590.0, 600.0, "overlap2"),
            ],
        )
        chunk2 = _chunk(
            2, chunk_start=1170.0, chunk_end=1800.0,
            segments=[
                _seg(0.0, 15.0, "overlap2"),
                _seg(15.0, 630.0, "C"),
            ],
        )
        result = merge_chunks([chunk0, chunk1, chunk2])
        assert result.chunk_count == 3
        assert result.overlap_regions_processed == 2
        # "overlap1" and "overlap2" from later chunks should be deduped
        texts = [s.text for s in result.segments]
        assert texts.count("overlap1") == 1
        assert texts.count("overlap2") == 1

    def test_unsorted_chunks_are_sorted(self):
        """Chunks passed out of order are sorted by index."""
        chunk1 = _chunk(
            1, chunk_start=585.0, chunk_end=1185.0,
            segments=[_seg(0.0, 5.0, "second")],
        )
        chunk0 = _chunk(
            0, chunk_start=0.0, chunk_end=600.0,
            segments=[_seg(0.0, 5.0, "first")],
        )
        result = merge_chunks([chunk1, chunk0])
        assert result.segments[0].text == "first"
        assert result.segments[1].text == "second"

    def test_no_overlap_between_chunks(self):
        """Adjacent chunks with no overlap — no dedup needed."""
        chunk0 = _chunk(
            0, chunk_start=0.0, chunk_end=600.0,
            segments=[_seg(0.0, 600.0, "A")],
        )
        chunk1 = _chunk(
            1, chunk_start=600.0, chunk_end=1200.0,
            segments=[_seg(0.0, 600.0, "B")],
        )
        result = merge_chunks([chunk0, chunk1])
        assert result.segments_before_dedup == 2
        assert result.segments_after_dedup == 2
        assert result.overlap_regions_processed == 0


# ── 4.4  Consistency pass ────────────────────────────────────────────


class TestConsistencyPass:
    def test_collapses_excess_newlines(self):
        text = "para one\n\n\n\n\npara two"
        result = consistency_pass(text)
        assert result == "para one\n\npara two"

    def test_collapses_multiple_spaces(self):
        text = "hello    world"
        result = consistency_pass(text)
        assert result == "hello world"

    def test_removes_boundary_repeat(self):
        text = "First paragraph. The ending sentence.\n\nThe ending sentence. New content here."
        result = consistency_pass(text)
        assert "New content here" in result
        # The duplicated sentence should appear only once
        assert result.count("ending sentence") == 1

    def test_empty_input(self):
        assert consistency_pass("") == ""

    def test_single_paragraph_unchanged(self):
        text = "This is a single paragraph with no issues."
        assert consistency_pass(text) == text

    def test_strips_line_whitespace(self):
        text = "  hello  \n  world  "
        result = consistency_pass(text)
        assert result == "hello\nworld"

    def test_no_repeat_detection_with_different_sentences(self):
        text = "Para one ends here.\n\nPara two starts fresh."
        result = consistency_pass(text)
        assert "Para one ends here." in result
        assert "Para two starts fresh." in result


# ── 4.5  Schema v3 merge-field persistence ───────────────────────────


class TestSchemaV3MergeFields:
    @pytest.fixture
    def db(self, tmp_path):
        conn = bootstrap(tmp_path / "test.db")
        yield conn
        conn.close()

    def test_schema_version_is_3(self, db):
        cur = db.execute("SELECT MAX(version) FROM schema_version")
        assert cur.fetchone()[0] == SCHEMA_VERSION
        assert SCHEMA_VERSION == 4

    def test_merge_columns_exist(self, db):
        cur = db.execute("PRAGMA table_info(job_results)")
        columns = {row[1] for row in cur.fetchall()}
        assert "is_merged" in columns
        assert "chunk_count" in columns
        assert "merged_segments" in columns
        assert "merged_raw_path" in columns
        assert "merged_corrected_path" in columns
        assert "consistency_text" in columns
        assert "segments_before_dedup" in columns
        assert "segments_after_dedup" in columns

    def test_insert_and_read_merge_result(self, db):
        from src.storage.sqlite_store import SQLiteStore
        from src.models.job import Job, JobStatus

        store = SQLiteStore(db)

        job = Job(
            job_id="merge-test-1",
            url="https://youtube.com/watch?v=test",
            created_at="2026-01-01T00:00:00",
        )
        store.insert_job(job)
        store.insert_result("merge-test-1", {
            "video_id": "test",
            "title": "Test",
            "channel": "Ch",
            "duration": 1800,
            "original_text": "raw",
            "corrected_text": "corrected",
            "language": "zh",
            "similarity_ratio": 0.95,
            "change_count": 10,
            "diff_inline": "diff",
            "processed_at": "2026-01-01T00:00:00",
        })

        segments = [{"start": 0.0, "end": 5.0, "text": "hello"}]
        store.update_result_merge_fields("merge-test-1", {
            "is_merged": 1,
            "chunk_count": 3,
            "merged_segments": json.dumps(segments),
            "merged_raw_path": "/tmp/raw.txt",
            "merged_corrected_path": "/tmp/corrected.txt",
            "consistency_text": "polished text",
            "segments_before_dedup": 20,
            "segments_after_dedup": 15,
        })

        result = store.get_result("merge-test-1")
        assert result["is_merged"] == 1
        assert result["chunk_count"] == 3
        assert json.loads(result["merged_segments"]) == segments
        assert result["merged_raw_path"] == "/tmp/raw.txt"
        assert result["consistency_text"] == "polished text"
        assert result["segments_before_dedup"] == 20
        assert result["segments_after_dedup"] == 15

    def test_default_values_for_non_merged(self, db):
        """Non-merged results have sensible defaults."""
        from src.storage.sqlite_store import SQLiteStore
        from src.models.job import Job

        store = SQLiteStore(db)
        job = Job(
            job_id="single-1",
            url="https://youtube.com/watch?v=s",
            created_at="2026-01-01T00:00:00",
        )
        store.insert_job(job)
        store.insert_result("single-1", {
            "video_id": "s",
            "title": "Short",
            "channel": "Ch",
            "duration": 300,
            "original_text": "raw",
            "corrected_text": "corrected",
            "language": "en",
            "similarity_ratio": 0.99,
            "change_count": 2,
            "diff_inline": "",
            "processed_at": "2026-01-01T00:00:00",
        })
        result = store.get_result("single-1")
        assert result["is_merged"] == 0
        assert result["chunk_count"] == 1
        assert result["merged_segments"] is None


class TestSchemaMigrationV2ToV3:
    def test_migration_adds_columns(self, tmp_path):
        """A v2 database is migrated to v3 with new merge columns."""
        db_path = tmp_path / "migrate.db"

        # Create a v2 database manually (without merge columns)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
            CREATE TABLE schema_version (
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO schema_version (version) VALUES (2);

            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                error TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                language TEXT,
                skip_correction INTEGER NOT NULL DEFAULT 0,
                custom_terms TEXT,
                input_signature TEXT
            );

            CREATE TABLE job_results (
                job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                channel TEXT NOT NULL,
                duration INTEGER NOT NULL,
                original_text TEXT NOT NULL,
                corrected_text TEXT NOT NULL,
                language TEXT NOT NULL,
                similarity_ratio REAL NOT NULL DEFAULT 0.0,
                change_count INTEGER NOT NULL DEFAULT 0,
                diff_inline TEXT NOT NULL DEFAULT '',
                processed_at TEXT NOT NULL
            );

            CREATE TABLE job_chunks (
                job_id TEXT NOT NULL REFERENCES jobs(job_id),
                chunk_index INTEGER NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                duration REAL NOT NULL,
                audio_path TEXT,
                transcript_path TEXT,
                corrected_path TEXT,
                status TEXT NOT NULL DEFAULT 'planned',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (job_id, chunk_index)
            );
        """)
        conn.close()

        # Now bootstrap should migrate
        conn2 = bootstrap(db_path)
        cur = conn2.execute("PRAGMA table_info(job_results)")
        columns = {row[1] for row in cur.fetchall()}
        assert "is_merged" in columns
        assert "merged_segments" in columns
        assert "consistency_text" in columns

        # Check version bumped
        cur = conn2.execute("SELECT MAX(version) FROM schema_version")
        assert cur.fetchone()[0] == SCHEMA_VERSION
        conn2.close()
