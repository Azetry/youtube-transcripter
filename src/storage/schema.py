"""SQLite schema definition and bootstrap logic.

Manages database creation and schema migrations for the
transcription job persistence layer.
"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

# Default database location (relative to project root)
DEFAULT_DB_PATH = "data/transcripter.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    -- Input parameters
    language TEXT,
    skip_correction INTEGER NOT NULL DEFAULT 0,
    custom_terms TEXT,  -- JSON array stored as text
    -- Input signature for exact-match reuse
    input_signature TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_input_signature ON jobs(input_signature);

CREATE TABLE IF NOT EXISTS job_results (
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

CREATE TABLE IF NOT EXISTS job_chunks (
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

CREATE INDEX IF NOT EXISTS idx_job_chunks_job_id ON job_chunks(job_id);
"""


def bootstrap(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Create or open the database file and ensure schema is applied.

    Returns an open connection with WAL mode and foreign keys enabled.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Apply schema
    conn.executescript(SCHEMA_SQL)

    # Track version and apply migrations
    cur = conn.execute("SELECT COUNT(*) FROM schema_version")
    if cur.fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()
    else:
        cur = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        )
        current_version = cur.fetchone()[0]
        if current_version < SCHEMA_VERSION:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            conn.commit()

    return conn
