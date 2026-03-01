-- HEGEMON Agent State Store — Schema v1
-- SQLite WAL mode for concurrent multi-agent access
-- Location: ~/.hegemon/state.db

PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=10000;

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

CREATE TABLE IF NOT EXISTS tickets (
    id           TEXT PRIMARY KEY,     -- CAB-1350
    title        TEXT,
    status       TEXT,                 -- Todo, InProgress, Done, Blocked
    estimate     INTEGER,
    priority     INTEGER,
    component    TEXT,
    summary      TEXT,                 -- 1-2 lines (not full description)
    dod_items    TEXT,                 -- JSON array of DoD criteria
    parent_id    TEXT,                 -- MEGA parent (CAB-1290)
    cycle        TEXT,                 -- current, next, backlog
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS council_cache (
    ticket_id    TEXT PRIMARY KEY,
    score        REAL,
    verdict      TEXT,                 -- Go/Fix/Redo
    personas     TEXT,                 -- JSON {chucky: 8, oss_killer: 9, ...}
    ticket_hash  TEXT,                 -- sha256(title + description)
    evaluated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_cycle ON tickets(cycle);
CREATE INDEX IF NOT EXISTS idx_tickets_parent ON tickets(parent_id);

CREATE TABLE IF NOT EXISTS queue_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id     TEXT NOT NULL,
    title         TEXT DEFAULT '',
    priority      INTEGER NOT NULL DEFAULT 2,
    role          TEXT DEFAULT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    assigned_to   TEXT DEFAULT NULL,
    dispatched_at TEXT DEFAULT NULL,
    completed_at  TEXT DEFAULT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M','now')),
    error         TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_queue_priority ON queue_jobs(priority, status, created_at);
