"""Tests for SQLite persistence layer (Unit B).

Covers schema bootstrap, job CRUD, result persistence,
restart-safe lookup, and input signature reuse.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.models.job import Job, JobStatus
from src.storage.schema import bootstrap, SCHEMA_VERSION
from src.storage.sqlite_store import SQLiteStore
from src.storage.signatures import compute_input_signature


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path):
    c = bootstrap(db_path)
    yield c
    c.close()


@pytest.fixture
def store(conn):
    return SQLiteStore(conn)


# ── Schema bootstrap tests ────────────────────────────────────


class TestSchemaBootstrap:
    def test_creates_database_file(self, db_path):
        conn = bootstrap(db_path)
        assert db_path.exists()
        conn.close()

    def test_creates_parent_directories(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "test.db"
        conn = bootstrap(deep_path)
        assert deep_path.exists()
        conn.close()

    def test_schema_version_recorded(self, conn):
        cur = conn.execute("SELECT version FROM schema_version")
        row = cur.fetchone()
        assert row["version"] == SCHEMA_VERSION

    def test_tables_exist(self, conn):
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "jobs" in tables
        assert "job_results" in tables
        assert "schema_version" in tables

    def test_idempotent_bootstrap(self, db_path):
        conn1 = bootstrap(db_path)
        conn1.close()
        conn2 = bootstrap(db_path)
        cur = conn2.execute("SELECT COUNT(*) FROM schema_version")
        assert cur.fetchone()[0] == 1
        conn2.close()

    def test_wal_mode(self, conn):
        cur = conn.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0] == "wal"


# ── SQLiteStore job CRUD tests ─────────────────────────────────


class TestSQLiteStoreJobs:
    def test_insert_and_get_job(self, store):
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store.insert_job(job)
        found = store.get_job("j1")
        assert found is not None
        assert found.job_id == "j1"
        assert found.url == "https://youtube.com/watch?v=abc"
        assert found.status == JobStatus.PENDING

    def test_get_job_not_found(self, store):
        assert store.get_job("nonexistent") is None

    def test_update_job_status(self, store):
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store.insert_job(job)
        store.update_job_status("j1", JobStatus.TRANSCRIBING, 50, "halfway")
        found = store.get_job("j1")
        assert found.status == JobStatus.TRANSCRIBING
        assert found.progress == 50
        assert found.message == "halfway"

    def test_complete_job(self, store):
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store.insert_job(job)
        store.complete_job("j1", "2025-01-01T00:00:00")
        found = store.get_job("j1")
        assert found.status == JobStatus.COMPLETED
        assert found.progress == 100
        assert found.completed_at == "2025-01-01T00:00:00"

    def test_fail_job(self, store):
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store.insert_job(job)
        store.fail_job("j1", "timeout")
        found = store.get_job("j1")
        assert found.status == JobStatus.FAILED
        assert found.error == "timeout"

    def test_custom_terms_roundtrip(self, store):
        job = Job(
            job_id="j1",
            url="https://youtube.com/watch?v=abc",
            custom_terms=["GPT", "Whisper"],
        )
        store.insert_job(job)
        found = store.get_job("j1")
        assert found.custom_terms == ["GPT", "Whisper"]

    def test_skip_correction_roundtrip(self, store):
        job = Job(
            job_id="j1",
            url="https://youtube.com/watch?v=abc",
            skip_correction=True,
        )
        store.insert_job(job)
        found = store.get_job("j1")
        assert found.skip_correction is True

    def test_multiple_jobs_isolated(self, store):
        j1 = Job(job_id="j1", url="https://youtube.com/watch?v=a")
        j2 = Job(job_id="j2", url="https://youtube.com/watch?v=b")
        store.insert_job(j1)
        store.insert_job(j2)
        store.complete_job("j1", "2025-01-01T00:00:00")
        assert store.get_job("j1").status == JobStatus.COMPLETED
        assert store.get_job("j2").status == JobStatus.PENDING


# ── Result persistence tests ──────────────────────────────────


class TestSQLiteStoreResults:
    def _make_result(self):
        return {
            "video_id": "abc",
            "title": "Test Video",
            "channel": "TestChannel",
            "duration": 120,
            "original_text": "hello",
            "corrected_text": "Hello.",
            "language": "en",
            "similarity_ratio": 0.95,
            "change_count": 1,
            "diff_inline": "[-hello-][+Hello.+]",
            "processed_at": "2025-01-01T00:00:00",
        }

    def test_insert_and_get_result(self, store):
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store.insert_job(job)
        result = self._make_result()
        store.insert_result("j1", result)
        found = store.get_result("j1")
        assert found is not None
        assert found["video_id"] == "abc"
        assert found["original_text"] == "hello"
        assert found["similarity_ratio"] == 0.95

    def test_get_result_not_found(self, store):
        assert store.get_result("nonexistent") is None

    def test_result_survives_reconnect(self, db_path):
        """Simulate restart: close and reopen DB, verify result persists."""
        conn1 = bootstrap(db_path)
        store1 = SQLiteStore(conn1)
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store1.insert_job(job)
        store1.complete_job("j1", "2025-01-01T00:00:00")
        store1.insert_result("j1", self._make_result())
        conn1.close()

        # Reopen - simulates process restart
        conn2 = bootstrap(db_path)
        store2 = SQLiteStore(conn2)
        found_job = store2.get_job("j1")
        assert found_job is not None
        assert found_job.status == JobStatus.COMPLETED
        found_result = store2.get_result("j1")
        assert found_result is not None
        assert found_result["video_id"] == "abc"
        conn2.close()


# ── Input signature tests ─────────────────────────────────────


class TestInputSignatures:
    def test_deterministic(self):
        sig1 = compute_input_signature("https://youtube.com/watch?v=abc", "zh")
        sig2 = compute_input_signature("https://youtube.com/watch?v=abc", "zh")
        assert sig1 == sig2

    def test_different_urls(self):
        sig1 = compute_input_signature("https://youtube.com/watch?v=abc")
        sig2 = compute_input_signature("https://youtube.com/watch?v=xyz")
        assert sig1 != sig2

    def test_different_language(self):
        sig1 = compute_input_signature("https://youtube.com/watch?v=abc", "zh")
        sig2 = compute_input_signature("https://youtube.com/watch?v=abc", "en")
        assert sig1 != sig2

    def test_skip_correction_matters(self):
        sig1 = compute_input_signature("https://youtube.com/watch?v=abc", skip_correction=False)
        sig2 = compute_input_signature("https://youtube.com/watch?v=abc", skip_correction=True)
        assert sig1 != sig2

    def test_custom_terms_order_invariant(self):
        sig1 = compute_input_signature(
            "https://youtube.com/watch?v=abc", custom_terms=["GPT", "Whisper"]
        )
        sig2 = compute_input_signature(
            "https://youtube.com/watch?v=abc", custom_terms=["Whisper", "GPT"]
        )
        assert sig1 == sig2

    def test_whitespace_normalization(self):
        sig1 = compute_input_signature("https://youtube.com/watch?v=abc")
        sig2 = compute_input_signature("  https://youtube.com/watch?v=abc  ")
        assert sig1 == sig2


# ── Reuse lookup tests ────────────────────────────────────────


class TestReuseLookup:
    def test_find_completed_by_signature(self, store):
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store.insert_job(job)
        sig = compute_input_signature("https://youtube.com/watch?v=abc")
        store.set_input_signature("j1", sig)
        store.complete_job("j1", "2025-01-01T00:00:00")

        found = store.find_completed_by_signature(sig)
        assert found is not None
        assert found.job_id == "j1"

    def test_no_match_for_pending_job(self, store):
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store.insert_job(job)
        sig = compute_input_signature("https://youtube.com/watch?v=abc")
        store.set_input_signature("j1", sig)
        # Job is still pending, not completed
        assert store.find_completed_by_signature(sig) is None

    def test_no_match_for_different_signature(self, store):
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store.insert_job(job)
        store.set_input_signature(
            "j1", compute_input_signature("https://youtube.com/watch?v=abc")
        )
        store.complete_job("j1", "2025-01-01T00:00:00")

        other_sig = compute_input_signature("https://youtube.com/watch?v=xyz")
        assert store.find_completed_by_signature(other_sig) is None

    def test_returns_most_recent_completed(self, store):
        # Insert two completed jobs with same signature
        for jid, ts in [("j1", "2025-01-01T00:00:00"), ("j2", "2025-01-02T00:00:00")]:
            job = Job(job_id=jid, url="https://youtube.com/watch?v=abc")
            store.insert_job(job)
            sig = compute_input_signature("https://youtube.com/watch?v=abc")
            store.set_input_signature(jid, sig)
            store.complete_job(jid, ts)

        sig = compute_input_signature("https://youtube.com/watch?v=abc")
        found = store.find_completed_by_signature(sig)
        assert found.job_id == "j2"


# ── JobService with SQLite backend tests ──────────────────────


class TestJobServiceWithStore:
    @pytest.fixture
    def svc(self, store):
        from src.services.job_service import JobService
        return JobService(store=store)

    def test_create_job_persisted(self, svc, store):
        job = svc.create_job(url="https://youtube.com/watch?v=abc")
        found = store.get_job(job.job_id)
        assert found is not None
        assert found.url == "https://youtube.com/watch?v=abc"

    def test_update_job_persisted(self, svc, store):
        job = svc.create_job(url="https://youtube.com/watch?v=abc")
        svc.update_job(job.job_id, JobStatus.TRANSCRIBING, 50, "working")
        found = store.get_job(job.job_id)
        assert found.status == JobStatus.TRANSCRIBING
        assert found.progress == 50

    def test_complete_job_persisted(self, svc, store):
        job = svc.create_job(url="https://youtube.com/watch?v=abc")
        svc.complete_job(job.job_id)
        found = store.get_job(job.job_id)
        assert found.status == JobStatus.COMPLETED
        assert found.completed_at is not None

    def test_fail_job_persisted(self, svc, store):
        job = svc.create_job(url="https://youtube.com/watch?v=abc")
        svc.fail_job(job.job_id, "boom")
        found = store.get_job(job.job_id)
        assert found.status == JobStatus.FAILED
        assert found.error == "boom"

    def test_store_and_get_result(self, svc):
        job = svc.create_job(url="https://youtube.com/watch?v=abc")
        result = {
            "video_id": "abc",
            "title": "Test",
            "channel": "Ch",
            "duration": 60,
            "original_text": "hi",
            "corrected_text": "Hi.",
            "language": "en",
            "similarity_ratio": 0.9,
            "change_count": 1,
            "diff_inline": "",
            "processed_at": "2025-01-01T00:00:00",
        }
        svc.store_result(job.job_id, result)
        found = svc.get_result(job.job_id)
        assert found is not None
        assert found["video_id"] == "abc"

    def test_find_reusable_job(self, svc):
        job = svc.create_job(
            url="https://youtube.com/watch?v=abc", language="zh"
        )
        svc.complete_job(job.job_id)
        reusable = svc.find_reusable_job(
            url="https://youtube.com/watch?v=abc", language="zh"
        )
        assert reusable is not None
        assert reusable.job_id == job.job_id

    def test_no_reusable_when_not_completed(self, svc):
        svc.create_job(url="https://youtube.com/watch?v=abc")
        reusable = svc.find_reusable_job(url="https://youtube.com/watch?v=abc")
        assert reusable is None

    def test_persistent_property(self, svc):
        assert svc.persistent is True

    def test_in_memory_fallback(self):
        from src.services.job_service import JobService
        svc = JobService()  # no store
        assert svc.persistent is False
        job = svc.create_job(url="https://youtube.com/watch?v=abc")
        assert svc.get_job(job.job_id) is not None
