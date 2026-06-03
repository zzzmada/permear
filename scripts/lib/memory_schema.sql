-- PERMEAR Organic Memory — v7.8 schema (English)
CREATE TABLE IF NOT EXISTS memory_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content       TEXT NOT NULL,
    kind          TEXT NOT NULL,    -- observation | pattern | user_fact | behavior_rule
    tier          TEXT NOT NULL DEFAULT 'ephemeral',  -- ephemeral | active | stable
    subject       TEXT,             -- for user_fact: which resident; NULL otherwise
    key           TEXT,             -- canonical key (type:entity_id) for deterministic reinforce; NULL for free text
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    mention_count INTEGER NOT NULL DEFAULT 1,
    source        TEXT,             -- daily | insight | engagement | wake | manual | config
    metadata      TEXT              -- free JSON for future extension
);

CREATE INDEX IF NOT EXISTS idx_tier ON memory_items(tier);
CREATE INDEX IF NOT EXISTS idx_kind ON memory_items(kind);
CREATE INDEX IF NOT EXISTS idx_last_seen ON memory_items(last_seen);
CREATE INDEX IF NOT EXISTS idx_subject ON memory_items(subject);
CREATE INDEX IF NOT EXISTS idx_key ON memory_items(key);

-- FTS5 for similarity (replaces Jaccard)
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    content,
    content_rowid=id,
    content=memory_items
);

-- SD5: system flags (daily_briefing_enviado, daily_boletim_disparado, etc.)
CREATE TABLE IF NOT EXISTS system_flags (
    name        TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- SD4: daily event staging (today only — cleaned up at midnight)
CREATE TABLE IF NOT EXISTS event_buffer (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    tipo       TEXT NOT NULL,
    detalhe    TEXT NOT NULL,
    entity_id  TEXT,
    canal      TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_buffer_ts ON event_buffer(ts);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_items BEGIN
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory_items BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory_items BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;
