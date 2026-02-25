-- HEGEMON Agent State Store — Schema v1
-- SQLite WAL mode for concurrent multi-agent access
-- Location: ~/.hegemon/state.db

PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=10000;

-- Active Claude Code sessions (TTL managed by cleanup command)
CREATE TABLE IF NOT EXISTS sessions (
    instance_id  TEXT PRIMARY KEY,
    project      TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'interactive',
    ticket       TEXT,
    branch       TEXT,
    step         TEXT NOT NULL DEFAULT 'claimed',
    pr           INTEGER,
    host         TEXT,
    source       TEXT NOT NULL DEFAULT 'local',
    pid          INTEGER,
    started_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- Milestone history (append-only audit trail)
CREATE TABLE IF NOT EXISTS milestones (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket       TEXT NOT NULL,
    step         TEXT NOT NULL,
    instance_id  TEXT NOT NULL,
    project      TEXT NOT NULL,
    pr           INTEGER,
    sha          TEXT,
    detail       TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Phase/ticket claims (replaces .claude/claims/*.json)
CREATE TABLE IF NOT EXISTS claims (
    id           TEXT PRIMARY KEY,
    ticket       TEXT NOT NULL,
    phase        INTEGER,
    mega_id      TEXT,
    owner        TEXT,
    pid          INTEGER,
    host         TEXT,
    branch       TEXT,
    deps         TEXT,
    claimed_at   TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
CREATE INDEX IF NOT EXISTS idx_sessions_ticket ON sessions(ticket);
CREATE INDEX IF NOT EXISTS idx_milestones_ticket ON milestones(ticket);
CREATE INDEX IF NOT EXISTS idx_milestones_created ON milestones(created_at);
CREATE INDEX IF NOT EXISTS idx_claims_owner ON claims(owner);
CREATE INDEX IF NOT EXISTS idx_claims_mega ON claims(mega_id);
