"""Tests for chunk metadata persistence (Unit C - Tasks 3.2/3.3/3.4).

Covers chunk insert, retrieval, status updates, and schema migration.
"""

import pytest

from src.models.job import Job, JobStatus
from src.storage.schema import bootstrap, SCHEMA_VERSION
from src.storage.sqlite_store import SQLiteStore


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


@pytest.fixture
def job_with_chunks(store):
    """Create a job and return its ID for chunk tests."""
    job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
    store.insert_job(job)
    return "j1"


class TestSchemaV2:
    def test_job_chunks_table_exists(self, conn):
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "job_chunks" in tables

    def test_schema_version_is_2(self, conn):
        cur = conn.execute("SELECT MAX(version) FROM schema_version")
        assert cur.fetchone()[0] == SCHEMA_VERSION
        assert SCHEMA_VERSION == 2


class TestChunkCRUD:
    def test_insert_and_get_chunks(self, store, job_with_chunks):
        chunks = [
            {
                "chunk_index": 0,
                "start_time": 0.0,
                "end_time": 600.0,
                "duration": 600.0,
                "audio_path": "/tmp/j1_chunk_000.mp3",
            },
            {
                "chunk_index": 1,
                "start_time": 585.0,
                "end_time": 1200.0,
                "duration": 615.0,
                "audio_path": "/tmp/j1_chunk_001.mp3",
            },
        ]
        store.insert_chunks(job_with_chunks, chunks)
        found = store.get_chunks(job_with_chunks)
        assert len(found) == 2
        assert found[0]["chunk_index"] == 0
        assert found[0]["start_time"] == 0.0
        assert found[0]["end_time"] == 600.0
        assert found[0]["audio_path"] == "/tmp/j1_chunk_000.mp3"
        assert found[1]["chunk_index"] == 1
        assert found[1]["start_time"] == 585.0

    def test_get_chunks_empty(self, store, job_with_chunks):
        found = store.get_chunks(job_with_chunks)
        assert found == []

    def test_get_chunks_ordered_by_index(self, store, job_with_chunks):
        # Insert out of order
        chunks = [
            {"chunk_index": 2, "start_time": 1170.0, "end_time": 1800.0, "duration": 630.0},
            {"chunk_index": 0, "start_time": 0.0, "end_time": 600.0, "duration": 600.0},
            {"chunk_index": 1, "start_time": 585.0, "end_time": 1185.0, "duration": 600.0},
        ]
        store.insert_chunks(job_with_chunks, chunks)
        found = store.get_chunks(job_with_chunks)
        assert [c["chunk_index"] for c in found] == [0, 1, 2]

    def test_chunk_default_status_is_planned(self, store, job_with_chunks):
        chunks = [{"chunk_index": 0, "start_time": 0.0, "end_time": 600.0, "duration": 600.0}]
        store.insert_chunks(job_with_chunks, chunks)
        found = store.get_chunks(job_with_chunks)
        assert found[0]["status"] == "planned"

    def test_update_chunk_status(self, store, job_with_chunks):
        chunks = [{"chunk_index": 0, "start_time": 0.0, "end_time": 600.0, "duration": 600.0}]
        store.insert_chunks(job_with_chunks, chunks)
        store.update_chunk_status(job_with_chunks, 0, "transcribed")
        found = store.get_chunks(job_with_chunks)
        assert found[0]["status"] == "transcribed"

    def test_update_chunk_with_artifact_paths(self, store, job_with_chunks):
        chunks = [{"chunk_index": 0, "start_time": 0.0, "end_time": 600.0, "duration": 600.0}]
        store.insert_chunks(job_with_chunks, chunks)
        store.update_chunk_status(
            job_with_chunks,
            0,
            "corrected",
            transcript_path="/tmp/chunk_0_transcript.txt",
            corrected_path="/tmp/chunk_0_corrected.txt",
        )
        found = store.get_chunks(job_with_chunks)
        assert found[0]["status"] == "corrected"
        assert found[0]["transcript_path"] == "/tmp/chunk_0_transcript.txt"
        assert found[0]["corrected_path"] == "/tmp/chunk_0_corrected.txt"

    def test_chunks_isolated_between_jobs(self, store):
        j1 = Job(job_id="j1", url="https://youtube.com/watch?v=a")
        j2 = Job(job_id="j2", url="https://youtube.com/watch?v=b")
        store.insert_job(j1)
        store.insert_job(j2)

        store.insert_chunks("j1", [
            {"chunk_index": 0, "start_time": 0.0, "end_time": 600.0, "duration": 600.0},
        ])
        store.insert_chunks("j2", [
            {"chunk_index": 0, "start_time": 0.0, "end_time": 600.0, "duration": 600.0},
            {"chunk_index": 1, "start_time": 585.0, "end_time": 1200.0, "duration": 615.0},
        ])

        assert len(store.get_chunks("j1")) == 1
        assert len(store.get_chunks("j2")) == 2

    def test_audio_path_optional(self, store, job_with_chunks):
        chunks = [{"chunk_index": 0, "start_time": 0.0, "end_time": 600.0, "duration": 600.0}]
        store.insert_chunks(job_with_chunks, chunks)
        found = store.get_chunks(job_with_chunks)
        assert found[0]["audio_path"] is None

    def test_chunks_survive_reconnect(self, db_path):
        """Chunk metadata persists across DB close/reopen."""
        conn1 = bootstrap(db_path)
        store1 = SQLiteStore(conn1)
        job = Job(job_id="j1", url="https://youtube.com/watch?v=abc")
        store1.insert_job(job)
        store1.insert_chunks("j1", [
            {"chunk_index": 0, "start_time": 0.0, "end_time": 600.0, "duration": 600.0,
             "audio_path": "/tmp/chunk.mp3"},
        ])
        store1.update_chunk_status("j1", 0, "transcribed", transcript_path="/tmp/t.txt")
        conn1.close()

        conn2 = bootstrap(db_path)
        store2 = SQLiteStore(conn2)
        found = store2.get_chunks("j1")
        assert len(found) == 1
        assert found[0]["status"] == "transcribed"
        assert found[0]["transcript_path"] == "/tmp/t.txt"
        conn2.close()
