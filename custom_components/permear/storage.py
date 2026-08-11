"""SQLite DAL for PERMEAR Organic Memory.

In-process replacement for scripts/lib/memory_db.py: event dual write (v8.8),
Heartbeat context + reinforce (v8.9), and — since v8.10 — the full memory
maintenance owned by the cycles: tier transitions, the tiers→priority loop
with bidirectional decay (v8.8-fix), engagement-based priority learning, and
the weekly/recent reads Sleep and Systems consume. Tier logic lives ONLY here.

Threading model: every SQLite call runs in an executor thread via
hass.async_add_executor_job — never on the event loop. A single connection
(check_same_thread=False) is shared across executor threads, serialized by a
threading.Lock.

Timezone discipline (v8.4, critical): event ts is LOCAL time
(datetime.now().isoformat()). Callers must never pass UTC, and no query here
may use SQLite's date('now') (UTC).
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import sqlite3
import threading
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .const import (
    SCHEMA_VERSION,
    BATTERY_RENOTIFY_DAYS,
    DRY_BOOST_EXCLUDED_DOMAINS,
    NOISE_BINARY_DEVICE_CLASSES,
    EMIT_HISTORY_MAX,
    ENGAGEMENT_DELTA_MAX,
    ENGAGEMENT_DELTA_MIN,
    ENGAGEMENT_DOWN_RATE,
    ENGAGEMENT_MIN_ALERTS,
    ENGAGEMENT_UP_RATE,
    EVENT_LOG_RETENTION_DAYS,
    MEMORY_ACTIVE_DEMOTE_DAYS,
    MEMORY_ACTIVE_PROMOTE_MENTIONS,
    MEMORY_ACTIVE_PROMOTE_WINDOW,
    MEMORY_EPHEMERAL_FADE_DAYS,
    MEMORY_RULE_FADE_DAYS,
    NOCTURNAL_HABIT_MIN_DAYS,
    NOCTURNAL_LOOKBACK_DAYS,
    PRESENCE_RECENT_MINUTES,
    MEMORY_FTS_MIN_SCORE,
    MEMORY_STABLE_DEMOTE_DAYS,
    MEMORY_STABLE_PROMOTE_MENTIONS,
    MEMORY_STABLE_PROMOTE_WINDOW,
    MONITORED_ENTITIES_RELATIVE_PATH,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON file state (availability snapshot, ARAS stats, agent circuit).
# flock-based, byte-compatible with scripts/lib/memory.py — the shell cycles
# still read/write the same files during coexistence. Executor-only.
# ---------------------------------------------------------------------------

def load_json(path: str, default=None):
    """Load JSON with a safe fallback (mirrors lib/memory.load_json)."""
    if default is None:
        default = {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


@contextmanager
def locked_json_update(path: str, default=None):
    """Atomic read-modify-write with LOCK_EX (mirrors lib/memory.locked_update).

    Mutations must be made in place on the yielded object. On exception the
    file is not saved. Executor threads only — never call from the event loop.
    """
    if default is None:
        default = {}
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    lock_path = path + ".lock"
    tmp_path = path + ".tmp"
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                data = default
            yield data
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, path)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def _today_local() -> str:
    """Local date string — NEVER SQLite date('now') (UTC, rule #41)."""
    return datetime.now().strftime("%Y-%m-%d")


def _parse_iso(s: str) -> datetime:
    """Lenient ISO parser for stored LOCAL timestamps (old rows may vary)."""
    s = s[:26]
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


def _fts_query(content: str) -> str:
    """Sanitize content into a safe FTS MATCH query (OR of significant tokens)."""
    tokens = [t for t in re.findall(r"\w+", content.lower()) if len(t) > 3]
    return " OR ".join(tokens[:10]) if tokens else content[:20]


# Entity-id tokens that name a place/direction, not the device subject. Removed
# from restriction matching so a refusal on one room's device cannot suppress
# an unrelated insight that merely shares the room (RODADA G / Q10).
_RESTRICTION_FILLER_TOKENS = frozenset({
    "sala", "quarto", "cozinha", "casa", "banheiro", "corredor", "varanda",
    "escritorio", "esquerda", "direita", "frente", "fundo", "lado", "principal",
})


def _engagement_delta(ent: dict, floor: int, current: int) -> int:
    """The entity's stored engagement delta, clamped (v9.7).

    Legacy conversion: before v9.7 engagement wrote `priority` absolutely and
    stamped priority_source='learned'. Those entities carry no delta, so it is
    derived from what they actually hold — delta = current - floor — which
    reproduces their present priority exactly. The demotion the engagement
    learned is preserved; only its permanence is gone, because the delta is now
    a value the next weekly run can move in either direction.
    """
    if "engagement_delta" in ent:
        raw = ent.get("engagement_delta")
    elif ent.get("priority_source") == "learned":
        raw = current - floor
    else:
        return 0
    try:
        return max(ENGAGEMENT_DELTA_MIN, min(ENGAGEMENT_DELTA_MAX, int(raw)))
    except (TypeError, ValueError):
        return 0


def _norm_token(word: str) -> str:
    """Lowercase, strip accents, crude singular (drop trailing 's')."""
    w = "".join(
        c for c in unicodedata.normalize("NFD", word.lower())
        if unicodedata.category(c) != "Mn"
    )
    if len(w) > 3 and w.endswith("s"):
        w = w[:-1]
    return w

# Schema matches the production layout the shell-side cycle scripts read
# (scripts/lib/memory_schema.sql). event_buffer keeps the tipo/canal columns
# so existing readers (build_heartbeat.py et al.) keep working unchanged.
SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content       TEXT NOT NULL,
    kind          TEXT NOT NULL,
    tier          TEXT NOT NULL DEFAULT 'ephemeral',
    subject       TEXT,
    key           TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    mention_count INTEGER NOT NULL DEFAULT 1,
    source        TEXT,
    metadata      TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tier ON memory_items(tier);
CREATE INDEX IF NOT EXISTS idx_kind ON memory_items(kind);
CREATE INDEX IF NOT EXISTS idx_last_seen ON memory_items(last_seen);
CREATE INDEX IF NOT EXISTS idx_subject ON memory_items(subject);
CREATE INDEX IF NOT EXISTS idx_key ON memory_items(key);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    content,
    content_rowid=id,
    content=memory_items
);

CREATE TABLE IF NOT EXISTS system_flags (
    name        TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_buffer (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    tipo       TEXT NOT NULL,
    detalhe    TEXT NOT NULL,
    entity_id  TEXT,
    canal      TEXT,
    metadata   TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_event_buffer_ts ON event_buffer(ts);

CREATE TABLE IF NOT EXISTS event_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    entity_id  TEXT,
    detalhe    TEXT NOT NULL,
    metadata   TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_event_log_ts ON event_log(ts);

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
"""


# ---------------------------------------------------------------------------
# Schema versioning (v9.x). The DB carries its schema version in PRAGMA
# user_version; const.SCHEMA_VERSION is the version the code above represents.
# On open, _apply_schema_version() compares the two and brings the DB forward.
#
# To add a future schema change, two edits:
#   1. write a migration function (idempotent, transaction-safe, DDL/DML only on
#      `conn`) that moves the schema from N-1 to N;
#   2. register it under its TARGET version N in MIGRATIONS and bump
#      SCHEMA_VERSION in const.py to N.
# Each step runs inside an explicit transaction and PRAGMA user_version is
# stamped to the target only after it commits, so an interrupted update resumes
# from the last completed version on the next open.
#
# MIGRATIONS[1] is a no-op ANCHOR: the base SCHEMA already *is* v1, so there is
# no delta to apply when reaching v1. Fresh installs and legacy (un-stamped,
# user_version=0) production DBs are simply stamped to 1 without recreating
# anything. The anchor keeps the registry complete and the loop uniform.
# ---------------------------------------------------------------------------

def _migrate_to_1(conn: sqlite3.Connection) -> None:
    """No-op anchor — the base SCHEMA already represents schema v1."""


MIGRATIONS = {
    1: _migrate_to_1,
}


class PermearStorage:
    """Organic Memory event store. All SQLite work runs off the event loop."""

    def __init__(self, hass: HomeAssistant, db_path: str) -> None:
        self._hass = hass
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    async def async_init(self) -> None:
        """Open the connection, create the schema if missing, and migrate."""
        await self._hass.async_add_executor_job(self._init)

    def _init(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        self._apply_schema_version(conn)
        self._conn = conn
        _LOGGER.debug("Organic Memory opened at %s (WAL)", self._db_path)

    @staticmethod
    def _tables_exist(conn: sqlite3.Connection) -> bool:
        """True if the core memory_items table is already present (i.e. this is
        not an empty, brand-new database file)."""
        return conn.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type='table' AND name='memory_items'"
        ).fetchone() is not None

    def _apply_schema_version(self, conn: sqlite3.Connection) -> None:
        """Bring the DB schema up to SCHEMA_VERSION (see registry above).

        - user_version > SCHEMA_VERSION (downgrade): refuse — a newer build
          wrote this DB; opening it risks destroying data we can't interpret.
        - user_version == SCHEMA_VERSION: already current; re-run the idempotent
          SCHEMA only as a safety net for missing tables.
        - user_version == 0: un-versioned. The live schema IS v1, so NEVER
          recreate/drop — executescript is all IF NOT EXISTS (creates tables for
          a fresh file, no-ops for a populated legacy DB), then stamp to v1.
        - 0 < user_version < SCHEMA_VERSION: apply MIGRATIONS in order, each in
          its own transaction, stamping user_version after each succeeds.
        """
        version = conn.execute("PRAGMA user_version").fetchone()[0]

        if version > SCHEMA_VERSION:
            _LOGGER.error(
                "Organic Memory schema v%s is newer than this build supports"
                " (v%s); refusing to open the DB to avoid data loss. Update"
                " PERMEAR to a build that understands schema v%s.",
                version, SCHEMA_VERSION, version,
            )
            raise RuntimeError(
                f"permear DB schema v{version} is newer than supported"
                f" v{SCHEMA_VERSION}; refusing to open"
            )

        if version == SCHEMA_VERSION:
            conn.executescript(SCHEMA)
            conn.commit()
            return

        if version == 0:
            legacy = self._tables_exist(conn)
            conn.executescript(SCHEMA)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()
            _LOGGER.info(
                "Organic Memory stamped to schema v%s (%s)",
                SCHEMA_VERSION,
                "existing DB preserved" if legacy else "fresh DB created",
            )
            return

        # 0 < version < SCHEMA_VERSION: apply each pending step in order.
        for target in range(version + 1, SCHEMA_VERSION + 1):
            migrate = MIGRATIONS.get(target)
            if migrate is None:
                raise RuntimeError(
                    f"no migration registered for schema v{target}"
                )
            conn.execute("BEGIN")
            try:
                migrate(conn)
                conn.execute(f"PRAGMA user_version = {target}")
                conn.commit()
            except Exception:
                conn.rollback()
                _LOGGER.exception(
                    "Schema migration to v%s failed; rolled back", target
                )
                raise
            _LOGGER.info("Organic Memory migrated schema -> v%s", target)

    async def async_add_event(
        self, ts: str, entity_id: str, detalhe: str, metadata: str
    ) -> int:
        """Dual write: same occurrence into event_buffer and event_log, same ts.

        ts must be LOCAL time ISO format. metadata is a JSON string ('{}' min).
        Returns the event_buffer row id.
        """
        return await self._hass.async_add_executor_job(
            self._add_event, ts, entity_id, detalhe, metadata
        )

    def _add_event(self, ts: str, entity_id: str, detalhe: str, metadata: str) -> int:
        assert self._conn is not None
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO event_buffer (ts, tipo, detalhe, entity_id, canal, metadata)"
                " VALUES (?,?,?,?,?,?)",
                (ts, "auto", detalhe, entity_id, None, metadata),
            )
            row_id = cur.lastrowid
            self._conn.execute(
                "INSERT INTO event_log (ts, entity_id, detalhe, metadata)"
                " VALUES (?,?,?,?)",
                (ts, entity_id, detalhe, metadata),
            )
            self._conn.commit()
        return row_id

    # ------------------------------------------------------------------
    # v8.9 — Heartbeat/ARAS queries (ported from scripts/lib/memory_db.py).
    # One executor hop fetches the whole DB context for a cycle.
    # ------------------------------------------------------------------

    async def async_heartbeat_context(
        self, window_start_iso: str, first_cycle: bool = False,
        presence_entity_ids: set | None = None,
    ) -> dict:
        """Window events + today's emitted keys + consolidated count + active
        restriction memories (v9.0.2), one executor job. On the first cycle of
        the day (the only one that evaluates the night) also returns the set of
        entities habitually active in the small hours (v9.2.2). When the caller
        passes the house's presence-sensor entity ids, also answers whether any
        of them produced an event within PRESENCE_RECENT_MINUTES (v9.4.3)."""
        return await self._hass.async_add_executor_job(
            self._heartbeat_context, window_start_iso, first_cycle,
            presence_entity_ids,
        )

    def _heartbeat_context(
        self, window_start_iso: str, first_cycle: bool = False,
        presence_entity_ids: set | None = None,
    ) -> dict:
        assert self._conn is not None
        today = _today_local()
        with self._lock:
            events = [
                dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM event_buffer WHERE ts >= ? ORDER BY ts",
                    (window_start_iso,),
                )
            ]
            # battery_low keys keep novelty at 0 for BATTERY_RENOTIFY_DAYS, not
            # just today: a low battery is a standing condition, and the daily
            # reset made the scanner deliver the same alert every single day
            # (30-day report, 2026-07). Local date arithmetic — never date('now').
            battery_floor = (
                datetime.now() - timedelta(days=BATTERY_RENOTIFY_DAYS)
            ).strftime("%Y-%m-%d")
            recent_keys = [
                r["key"]
                for r in self._conn.execute(
                    "SELECT key FROM memory_items WHERE source='heartbeat'"
                    " AND key IS NOT NULL AND (date(last_seen) = ?"
                    " OR (key LIKE 'battery_low:%' AND date(last_seen) >= ?))",
                    (today, battery_floor),
                )
            ]
            consolidated = self._conn.execute(
                "SELECT COUNT(*) FROM memory_items WHERE tier IN ('active','stable')"
            ).fetchone()[0]
            # Learned restrictions (v9.0.2) — biological: a faded restriction
            # stops applying and the subject re-emerges. Few rows; the
            # restriction flag lives in metadata, filtered below.
            restr_rows = self._conn.execute(
                "SELECT content, key, metadata FROM memory_items"
                " WHERE kind = 'behavior_rule' AND tier != 'faded'"
            ).fetchall()
            # Nocturnal habituation (v9.2.2) — only needed on the first cycle
            # (the one whose window reaches the night). ONE deterministic query
            # over the existing event_log: entities with small-hours activity on
            # >= MIN_DAYS distinct days within the lookback are "habitually
            # nocturnal" → night is normal for them → not anomalous. substr on
            # the LOCAL ISO ts (never date('now')/UTC, rule #41).
            nocturnal_habitual: set = set()
            if first_cycle:
                cutoff = (
                    datetime.now() - timedelta(days=NOCTURNAL_LOOKBACK_DAYS)
                ).strftime("%Y-%m-%dT%H:%M:%S")
                nocturnal_habitual = {
                    r["entity_id"]
                    for r in self._conn.execute(
                        "SELECT entity_id FROM event_log"
                        " WHERE ts >= ? AND CAST(substr(ts, 12, 2) AS INT) < 6"
                        " AND entity_id IS NOT NULL"
                        " GROUP BY entity_id"
                        " HAVING COUNT(DISTINCT substr(ts, 1, 10)) >= ?",
                        (cutoff, NOCTURNAL_HABIT_MIN_DAYS),
                    )
                }
            # Recent presence in the house (v9.4.3) — any event from a
            # presence-class binary_sensor within the window. The capture
            # records presence as the sustained-span event, so ANY row from
            # these entities means someone was home. ONE query per cycle,
            # LOCAL ts (never date('now')/UTC, rule #41). No presence
            # sensors → False → the gray prompt stays untouched.
            presence_recent = False
            if presence_entity_ids:
                ids = sorted(presence_entity_ids)
                presence_cutoff = (
                    datetime.now() - timedelta(minutes=PRESENCE_RECENT_MINUTES)
                ).isoformat()
                presence_recent = self._conn.execute(
                    "SELECT 1 FROM event_log WHERE ts >= ?"
                    f" AND entity_id IN ({','.join('?' * len(ids))})"
                    " LIMIT 1",
                    (presence_cutoff, *ids),
                ).fetchone() is not None
        restrictions = []
        for r in restr_rows:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            if not meta.get("restriction"):
                continue
            entity_id = meta.get("entity_id")
            if not entity_id and r["key"] and ":" in r["key"]:
                entity_id = r["key"].split(":", 1)[1]
            restrictions.append(
                {"content": r["content"], "entity_id": entity_id}
            )
        return {
            "events": events,
            "recent_keys": recent_keys,
            "consolidated_count": consolidated,
            "restrictions": restrictions,
            "nocturnal_habitual": nocturnal_habitual,
            "presence_recent": presence_recent,
        }

    async def async_record_emit(
        self, content: str, key: str | None, metadata: dict | None
    ) -> tuple:
        """Persist an emitted alert (ports memory_record_emit.py)."""
        return await self._hass.async_add_executor_job(
            self._record_emit, content, key, metadata
        )

    def _record_emit(self, content: str, key: str | None, metadata: dict | None):
        clean_key = (key.strip() or None) if key else None
        item_id, was_new, via = self._add_or_reinforce(
            content.strip(), kind="observation", source="heartbeat",
            key=clean_key, metadata=metadata,
        )
        # Persist score on reinforce paths — _add_item stores it for new items
        if not was_new and metadata and "score" in metadata:
            self._update_metadata(item_id, {"score": metadata["score"]})
        if clean_key:
            self._note_emission(item_id)
        return item_id, was_new, via

    def _note_emission(self, item_id: int) -> None:
        """Append the emission timestamp to metadata.emits (bounded list).

        Reinforcement collapses a week of alerts into a single row, so
        engagement learning cannot count alerts by row (it never reached
        ENGAGEMENT_MIN_ALERTS that way) — per-emission counting lives here.
        """
        assert self._conn is not None
        now = datetime.now().isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT metadata FROM memory_items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                return
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            emits = meta.get("emits") or []
            emits.append(now)
            meta["emits"] = emits[-EMIT_HISTORY_MAX:]
            self._conn.execute(
                "UPDATE memory_items SET metadata = ? WHERE id = ?",
                (json.dumps(meta), item_id),
            )
            self._conn.commit()

    async def async_record_interaction(self, canal: str, content: str) -> None:
        """Persist a system→user interaction (ports record_interaction.py)."""
        if not content.strip():
            return
        await self._hass.async_add_executor_job(
            self._add_or_reinforce, content.strip(), "interaction", "interaction",
            None, {"canal": canal},
        )

    def _add_or_reinforce(
        self, content: str, kind: str, source: str,
        key: str | None = None, metadata: dict | None = None,
    ) -> tuple:
        """Two-layer reinforce-or-create: canonical key, then FTS (≤ -5.0).

        kind='interaction' skips the FTS layer and dedups by EXACT content
        instead: an interaction is the resident's literal words, read verbatim
        by the Sleep extraction — a fuzzy merge replaces today's speech with an
        old row's text, so a new restriction never reaches extraction (v9.4.1;
        two real losses in production, both absorbed at score ≈ −5.2/−5.9).
        Exact match is lossless (same words) and still folds plain repeats.
        """
        assert self._conn is not None
        now = datetime.now().isoformat()
        with self._lock:
            if key:
                hit = self._conn.execute(
                    "SELECT id, tier, first_seen FROM memory_items WHERE key = ?"
                    " ORDER BY last_seen DESC LIMIT 1",
                    (key,),
                ).fetchone()
                if hit:
                    self._reinforce_row_locked(hit, now)
                    self._conn.commit()
                    return hit["id"], False, "key"
            if kind == "interaction":
                hit = self._conn.execute(
                    "SELECT id, tier, first_seen FROM memory_items"
                    " WHERE kind = 'interaction' AND content = ?"
                    " ORDER BY last_seen DESC LIMIT 1",
                    (content,),
                ).fetchone()
                if hit:
                    self._reinforce_row_locked(hit, now)
                    self._conn.commit()
                    return hit["id"], False, "exact"
                cur = self._conn.execute(
                    "INSERT INTO memory_items (content, kind, tier, subject, key,"
                    " first_seen, last_seen, mention_count, source, metadata)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (content, kind, "ephemeral", None, key, now, now, 1, source,
                     json.dumps(metadata) if metadata else None),
                )
                self._conn.commit()
                return cur.lastrowid, True, "new"
            try:
                rows = self._conn.execute(
                    "SELECT m.id, m.tier, m.first_seen, m.key,"
                    " bm25(memory_fts) AS score"
                    " FROM memory_fts JOIN memory_items m ON m.id = memory_fts.rowid"
                    " WHERE memory_fts MATCH ? AND m.kind = ?"
                    " ORDER BY score LIMIT 1",
                    (_fts_query(content), kind),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []  # FTS query parse issue -> treat as no match
            if rows and rows[0]["score"] <= MEMORY_FTS_MIN_SCORE:
                self._reinforce_row_locked(rows[0], now)
                if key and not rows[0]["key"]:
                    # Adopt the caller's canonical key on a keyless row — the
                    # key lookup above already missed, so no other row owns it.
                    # Without this the subject reinforces keyless forever and
                    # never enters recent_keys (novelty dedup).
                    self._conn.execute(
                        "UPDATE memory_items SET key = ? WHERE id = ?",
                        (key, rows[0]["id"]),
                    )
                self._conn.commit()
                return rows[0]["id"], False, "fts"
            cur = self._conn.execute(
                "INSERT INTO memory_items (content, kind, tier, subject, key,"
                " first_seen, last_seen, mention_count, source, metadata)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (content, kind, "ephemeral", None, key, now, now, 1, source,
                 json.dumps(metadata) if metadata else None),
            )
            self._conn.commit()
            return cur.lastrowid, True, "new"

    def _reinforce_row_locked(self, row, now: str) -> None:
        """Reinforce one matched row (caller holds the lock) with epoch rules.

        - faded row → resurrect as a fresh ephemeral (new epoch). The key/FTS
          lookups reach faded rows but tier maintenance skips them, so without
          this a faded memory swallowed every future mention forever — and a
          re-stated restriction (behavior_rule) could never re-apply.
        - ephemeral row older than the promotion window → restart the epoch
          (first_seen/mention_count reset). Promotion measures age from
          first_seen, so a demoted or long-lived row otherwise sat below the
          window forever no matter how often it was mentioned.
        - anything else → plain reinforce (mention_count+1, last_seen).
        """
        stale_ephemeral = (
            row["tier"] == "ephemeral"
            and (datetime.now() - _parse_iso(row["first_seen"])).days
            > MEMORY_ACTIVE_PROMOTE_WINDOW
        )
        if row["tier"] == "faded" or stale_ephemeral:
            self._conn.execute(
                "UPDATE memory_items SET tier = 'ephemeral', mention_count = 1,"
                " first_seen = ?, last_seen = ? WHERE id = ?",
                (now, now, row["id"]),
            )
            _LOGGER.debug(
                "Memory %s re-learned (%s) — new ephemeral epoch",
                row["id"], "resurrected" if row["tier"] == "faded" else "stale",
            )
        else:
            self._conn.execute(
                "UPDATE memory_items SET mention_count = mention_count + 1,"
                " last_seen = ? WHERE id = ?",
                (now, row["id"]),
            )

    def _update_metadata(self, item_id: int, patch: dict) -> bool:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT metadata FROM memory_items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                return False
            current = json.loads(row["metadata"]) if row["metadata"] else {}
            current.update(patch)
            self._conn.execute(
                "UPDATE memory_items SET metadata = ? WHERE id = ?",
                (json.dumps(current), item_id),
            )
            self._conn.commit()
        return True

    # ------------------------------------------------------------------
    # v8.9 — sensor reads (daily memory, household data).
    # ------------------------------------------------------------------

    async def async_daily_summary(self) -> dict:
        """Today's events/interactions/flags (ports sensor_daily_memory.py)."""
        return await self._hass.async_add_executor_job(self._daily_summary)

    def _daily_summary(self) -> dict:
        assert self._conn is not None
        today = _today_local()
        with self._lock:
            # ts is LOCAL ISO ("YYYY-MM-DDT…") — a range compare against the
            # date prefix is equivalent to date(ts)=today and uses the index
            # (date(ts) forced a full scan every 5 minutes via the sensor).
            events = [
                dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM event_buffer WHERE ts >= ? ORDER BY ts",
                    (today,),
                )
            ]
            inter_rows = self._conn.execute(
                "SELECT content, metadata FROM memory_items"
                " WHERE source='interaction' AND last_seen >= ?"
                " ORDER BY last_seen",
                (today,),
            ).fetchall()
            flags = {
                r["name"]: r["value"]
                for r in self._conn.execute(
                    "SELECT name, value FROM system_flags WHERE name LIKE 'daily_%'"
                )
            }
        interactions = []
        for r in inter_rows:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            interactions.append(
                {"content": r["content"], "canal": meta.get("canal", "desconhecido")}
            )
        return {
            "data": today,
            "eventos": events,
            "interacoes": interactions,
            "boletim_disparado": flags.get("daily_boletim_disparado") == "true",
            "briefing_enviado": flags.get("daily_briefing_enviado") == "true",
        }

    async def async_system_insights(self) -> dict:
        """System insights from memory_items source='systems' (v8.7 contract)."""
        return await self._hass.async_add_executor_job(self._system_insights)

    def _active_restriction_tokens(self) -> set:
        """Device-noun tokens of ACTIVE (non-faded) restriction behavior_rules.

        Used to suppress Systems insights the resident already refused (RODADA
        G / Q10). Only ENTITY-ANCHORED restrictions contribute (entity_id from
        metadata or the 'restriction:<eid>' key); keyless vague refusals do not
        drive suppression — that keeps false positives near zero. Place/short
        tokens are dropped (filler list + len>=4), so e.g. the TV refusal
        (media_player.tv_example) yields no token and cannot hide any insight,\n        while a curtain refusal (cover.curtain_*) yields {'curtain'}."""
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, metadata FROM memory_items"
                " WHERE kind = 'behavior_rule' AND tier != 'faded'"
            ).fetchall()
        tokens: set = set()
        for r in rows:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            if not meta.get("restriction"):
                continue
            eid = meta.get("entity_id")
            if not eid and r["key"] and r["key"].startswith("restriction:"):
                eid = r["key"].split(":", 1)[1]
            if not eid or "." not in eid:
                continue
            for raw in re.split(r"[._]", eid.split(".", 1)[1]):
                tok = _norm_token(raw)
                if len(tok) >= 4 and tok not in _RESTRICTION_FILLER_TOKENS:
                    tokens.add(tok)
        return tokens

    @staticmethod
    def _insight_matches_tokens(content: str, tokens: set) -> bool:
        words = {_norm_token(w) for w in re.findall(r"\w+", content)}
        return bool(words & tokens)

    def _system_insights(self) -> dict:
        assert self._conn is not None
        reject_tokens = self._active_restriction_tokens()
        with self._lock:
            # Faded suggestions leave the briefing: silence is an answer. An
            # unanswered suggestion gets ~7 nights of exposure (ephemeral fade
            # window), then tier decay retires it from the reader too — before
            # this filter, one faded suggestion was repeated nightly for 14+
            # days (30-day report, 2026-07). The row stays: mark/decay, never
            # delete; a resident mention still resurrects it.
            rows = self._conn.execute(
                "SELECT id, content, metadata, last_seen FROM memory_items"
                " WHERE source = 'systems' AND tier != 'faded'"
                " ORDER BY last_seen DESC"
            ).fetchall()
        result = {"suggestions": [], "pending": []}
        for r in rows:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            insight_type = meta.get("insight_type", "")
            if insight_type not in ("suggestion", "pending"):
                continue
            # Refused before → stays refused. Durable + idempotent: the flag
            # survives the weekly Systems reinforce (which only bumps
            # mention_count/last_seen, never metadata).
            if meta.get("rejected"):
                continue
            # The resident refused this subject (an active restriction names
            # the entity). Mark rejected so it stops reappearing — biological:
            # we mark, never delete; tier decay still ages the row.
            if reject_tokens and self._insight_matches_tokens(
                r["content"], reject_tokens
            ):
                self._update_metadata(r["id"], {"rejected": True})
                _LOGGER.info(
                    "Systems insight %s suppressed from briefing — subject "
                    "matches an active restriction", r["id"],
                )
                continue
            bucket = "suggestions" if insight_type == "suggestion" else "pending"
            result[bucket].append(
                {"id": r["id"], "content": r["content"], "last_seen": r["last_seen"]}
            )
        return result

    # ------------------------------------------------------------------
    # v8.10 — Sleep / Systems reads and writes.
    # ------------------------------------------------------------------

    async def async_add_or_reinforce(
        self, content: str, kind: str, source: str,
        key: str | None = None, metadata: dict | None = None,
    ) -> tuple:
        """Public reinforce-or-create (Sleep memories, Systems insights)."""
        return await self._hass.async_add_executor_job(
            self._add_or_reinforce, content, kind, source, key, metadata
        )

    async def async_set_flag(self, name: str, value: str) -> None:
        await self._hass.async_add_executor_job(self._set_flag, name, value)

    def _set_flag(self, name: str, value: str) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                "INSERT INTO system_flags(name, value, updated_at) VALUES(?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET value=excluded.value,"
                " updated_at=excluded.updated_at",
                (name, value, datetime.now().isoformat()),
            )
            self._conn.commit()

    async def async_recent_memories(self, days: int = 7, source: str = "daily") -> list:
        """Memory contents from the last N days (weekly compile context)."""
        return await self._hass.async_add_executor_job(
            self._recent_memories, days, source
        )

    def _recent_memories(self, days: int, source: str) -> list:
        assert self._conn is not None
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._lock:
            rows = self._conn.execute(
                "SELECT content FROM memory_items WHERE source=? AND last_seen >= ?"
                " ORDER BY last_seen DESC",
                (source, cutoff),
            ).fetchall()
        return [r["content"] for r in rows]

    async def async_recent_interactions(self, days: int = 7) -> list:
        """Telegram/voice interactions of the last N days ({content, canal})."""
        return await self._hass.async_add_executor_job(
            self._recent_interactions, days
        )

    def _recent_interactions(self, days: int) -> list:
        assert self._conn is not None
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._lock:
            rows = self._conn.execute(
                "SELECT content, metadata FROM memory_items"
                " WHERE source='interaction' AND last_seen >= ?"
                " ORDER BY last_seen DESC",
                (cutoff,),
            ).fetchall()
        result = []
        for r in rows:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            result.append(
                {"content": r["content"], "canal": meta.get("canal", "desconhecido")}
            )
        return result

    async def async_event_log_range(self, days: int = 7) -> list:
        """event_log rows from the last N days — co-occurrence input.

        LOCAL-time cutoff (rule #41) — the shell version still used SQLite
        date('now') (UTC) here; fixed in the port.
        """
        return await self._hass.async_add_executor_job(self._event_log_range, days)

    def _event_log_range(self, days: int) -> list:
        assert self._conn is not None
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, entity_id, detalhe, metadata FROM event_log"
                " WHERE date(ts) >= ? ORDER BY ts",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    async def async_emits_for_engagement(self, days: int = 7) -> list:
        """Keyed heartbeat emits of the last N days (engagement learning)."""
        return await self._hass.async_add_executor_job(
            self._emits_for_engagement, days
        )

    def _emits_for_engagement(self, days: int) -> list:
        assert self._conn is not None
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, metadata FROM memory_items"
                " WHERE source='heartbeat' AND last_seen >= ? AND key IS NOT NULL",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    async def async_mark_reactions(self, minutes: int = 15) -> int:
        """Mark recent heartbeat emits as reacted (ports mark_reaction.py).
        Called when the user replies on Telegram — engagement signal."""
        return await self._hass.async_add_executor_job(self._mark_reactions, minutes)

    def _mark_reactions(self, minutes: int) -> int:
        assert self._conn is not None
        now = datetime.now()
        cutoff = (now - timedelta(minutes=minutes)).isoformat()
        marked = 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, metadata FROM memory_items"
                " WHERE source='heartbeat' AND last_seen >= ?",
                (cutoff,),
            ).fetchall()
            for r in rows:
                meta = json.loads(r["metadata"]) if r["metadata"] else {}
                emits = meta.get("emits") or []
                reactions = meta.get("reactions") or []
                if emits:
                    # one reaction per emission at most — a second reply inside
                    # the window must not double-credit the same alert
                    if reactions and reactions[-1] >= emits[-1]:
                        continue
                elif meta.get("reacted"):
                    continue  # legacy row without emission history
                reactions.append(now.isoformat())
                meta["reactions"] = reactions[-EMIT_HISTORY_MAX:]
                meta["reacted"] = True
                self._conn.execute(
                    "UPDATE memory_items SET metadata = ? WHERE id = ?",
                    (json.dumps(meta), r["id"]),
                )
                marked += 1
            self._conn.commit()
        return marked

    # ------------------------------------------------------------------
    # v8.10 — memory maintenance (Sleep). Tier logic lives ONLY here.
    # Ports run_memory_maintenance.py + lib/memory_db.run_tier_maintenance
    # + update_priority_from_memory (with the v8.8-fix bidirectional decay).
    # ------------------------------------------------------------------

    async def async_run_maintenance(self) -> dict:
        """Cleanup + tier transitions + tiers→priority loop. One executor job."""
        # device_class snapshot built on the loop (thread-safe, mirrors Wake)
        # so the priority loop can separate noise binary_sensors from signal
        # ones without reading the state machine from the executor.
        binary_device_classes = {
            s.entity_id: (s.attributes.get("device_class") or "")
            for s in self._hass.states.async_all("binary_sensor")
        }
        return await self._hass.async_add_executor_job(
            self._run_maintenance, binary_device_classes
        )

    def _run_maintenance(self, binary_device_classes: dict | None = None) -> dict:
        counts = self._tier_maintenance()
        changes = self._update_priority_from_memory(binary_device_classes or {})
        report = {"tiers": counts, "priority_changes": changes}
        _LOGGER.info("Memory maintenance: %s", report)
        return report

    def _tier_maintenance(self) -> dict:
        """Tier transitions. Fade beats promotion (silence wins over count).
        observation promoted ephemeral→active becomes 'pattern' (v7.9-D);
        kind='interaction' never promotes (rule #42, narrowed in v9.7).

        v9.7 — rule #42 used to key on source='interaction', which covers TWO
        kinds: the resident's raw speech ('ola', 'ok.', 'sim' — kind
        'interaction') and the rules the Sleep extraction distils from it
        (kind 'behavior_rule'). The rule's target was always the trivial
        speech; catching the rules too meant a restriction could never leave
        'ephemeral' and therefore always faded. "Nao notificar sobre TV
        offline" reached mention_count=3 — the promotion threshold — and faded
        anyway. Keying on KIND separates them with the discriminator that
        already exists: speech stays unpromotable, a repeated rule can
        consolidate. No new declarative path — the rule still only comes from
        the Sleep extraction.

        A behavior_rule also fades on its own horizon (MEMORY_RULE_FADE_DAYS):
        an instruction is not an observation. Decay is preserved, not removed.
        """
        assert self._conn is not None
        now = datetime.now()
        counts = {
            "promoted_active": 0, "promoted_stable": 0,
            "demoted_active": 0, "demoted_ephemeral": 0, "faded": 0,
            "observation_to_pattern": 0, "rule_unfaded": 0,
        }
        rule_floor = (
            now - timedelta(days=MEMORY_RULE_FADE_DAYS)
        ).isoformat()
        with self._lock:
            # Calibration convergence (v9.7, idempotent): a behavior_rule that
            # was retired by the OLD 7-day observation horizon but is still
            # inside its own 30-day horizon goes back to ephemeral. This is not
            # a general un-fade — only the kind whose horizon changed, and only
            # while its own silence window has not expired. Once it does, the
            # normal pass below fades it again and it stays faded.
            counts["rule_unfaded"] = self._conn.execute(
                "UPDATE memory_items SET tier = 'ephemeral'"
                " WHERE kind = 'behavior_rule' AND tier = 'faded'"
                " AND last_seen >= ?",
                (rule_floor,),
            ).rowcount
            rows = self._conn.execute(
                "SELECT * FROM memory_items WHERE tier != 'faded'"
            ).fetchall()
            for r in rows:
                item = dict(r)
                tier = item["tier"]
                age = (now - _parse_iso(item["first_seen"])).days
                silence = (now - _parse_iso(item["last_seen"])).days
                mentions = item["mention_count"]
                new_tier = tier

                is_rule = item["kind"] == "behavior_rule"
                fade_after = (
                    MEMORY_RULE_FADE_DAYS if is_rule
                    else MEMORY_EPHEMERAL_FADE_DAYS
                )

                if tier == "ephemeral":
                    if silence >= fade_after:
                        new_tier = "faded"
                        counts["faded"] += 1
                    elif (item["kind"] != "interaction"
                          and mentions >= MEMORY_ACTIVE_PROMOTE_MENTIONS
                          and age <= MEMORY_ACTIVE_PROMOTE_WINDOW):
                        new_tier = "active"
                        counts["promoted_active"] += 1
                elif tier == "active":
                    if silence >= MEMORY_ACTIVE_DEMOTE_DAYS:
                        new_tier = "ephemeral"
                        counts["demoted_ephemeral"] += 1
                    elif (mentions >= MEMORY_STABLE_PROMOTE_MENTIONS
                          and age <= MEMORY_STABLE_PROMOTE_WINDOW):
                        new_tier = "stable"
                        counts["promoted_stable"] += 1
                elif tier == "stable":
                    if silence >= MEMORY_STABLE_DEMOTE_DAYS:
                        new_tier = "active"
                        counts["demoted_active"] += 1

                if new_tier != tier:
                    new_kind = item["kind"]
                    if (tier == "ephemeral" and new_tier == "active"
                            and item["kind"] == "observation"):
                        new_kind = "pattern"
                        counts["observation_to_pattern"] += 1
                    self._conn.execute(
                        "UPDATE memory_items SET tier = ?, kind = ? WHERE id = ?",
                        (new_tier, new_kind, item["id"]),
                    )
            self._conn.commit()
        return counts

    def _update_priority_from_memory(self, binary_device_classes=None) -> list:
        """Loop tiers→priority: memory sets the FLOOR, engagement modulates it.

        floor = 2 (stable) / 1 (active) / 0, granted only to entities that earn
        the boost (dry state-change domains never do). Final priority =
        clamp(floor + engagement_delta, 0, 2), and an entity with floor 0 stays
        at 0 — engagement modulates the consolidation boost, it never invents
        priority the memory did not earn. Recomputed from scratch every run:
        idempotent, and it rises AND decays with the tier (rule #5).

        v9.7 — engagement used to write `priority` absolutely and stamp
        priority_source='learned', which this loop skipped forever (the
        hierarchy user > learned > memory was written for HUMAN curation).
        Since engagement is the only writer of 'learned', a single low-reaction
        week sealed an entity at 0 with no way back: recovery needs
        ENGAGEMENT_MIN_ALERTS, which a silenced entity cannot accumulate. The
        three entities with stable memory (door, window, TV) sat at 0, so no
        entity in the house reached SPIKE_MIN_PRIORITY and the orienting reflex
        was arithmetically impossible (09/08 check). Only priority_source='user'
        — the resident's own hand — is untouchable now; 'learned' is read as
        legacy engagement and converted to a delta that preserves the entity's
        current priority exactly (no behaviour jump on the first run).
        """
        assert self._conn is not None
        with self._lock:
            # behavior_rule is EXCLUDED: its canonical key is
            # 'restriction:<entity_id>', so a consolidated restriction would
            # RAISE the priority of the very entity the resident asked to hear
            # less about. Inert before v9.7 (a rule could never reach
            # active/stable); live the moment rule #42 stopped blocking it.
            rows = self._conn.execute(
                "SELECT key, tier FROM memory_items"
                " WHERE tier IN ('active','stable') AND key IS NOT NULL"
                " AND kind != 'behavior_rule'"
            ).fetchall()
            # RODADA B: a light is "rich" (dimmer) only if it EVER recorded a
            # brightness — a single consolidated row reflects just the last
            # event, so an "off" reinforcement would hide a real dimmer. Stable
            # signal: any historical row carrying brightness.
            rich_light_ids = {
                r["key"].split(":", 1)[1]
                for r in self._conn.execute(
                    "SELECT key, metadata FROM memory_items"
                    " WHERE key LIKE '%:light.%' AND metadata LIKE '%brightness%'"
                )
                if r["metadata"] and "brightness" in (json.loads(r["metadata"]) or {})
            }

        entity_map: dict = {}
        for r in rows:
            key = r["key"]
            if ":" not in key:
                continue
            entity_id = key.split(":", 1)[1]
            if "." not in entity_id:
                continue
            if entity_map.get(entity_id) != "stable":
                entity_map[entity_id] = r["tier"]

        dc_map = binary_device_classes or {}

        def _earns_memory_boost(eid: str) -> bool:
            """Dry binary-state entities don't earn the consolidation boost.
            switch is always dry; a light is dry unless it's a dimmer
            (brightness ever recorded); a binary_sensor of a noise class
            (occupancy/motion/presence) is dry — signal classes and classless
            binary_sensors keep the boost. Rich domains keep the boost."""
            domain = eid.split(".")[0]
            if domain in DRY_BOOST_EXCLUDED_DOMAINS:
                return False
            if domain == "light":
                return eid in rich_light_ids
            if domain == "binary_sensor":
                return dc_map.get(eid, "") not in NOISE_BINARY_DEVICE_CLASSES
            return True

        changes = []
        path = self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH)
        with locked_json_update(path, {"entities": []}) as data:
            for ent in data.get("entities", []):
                eid = ent.get("entity_id")
                if not eid or not ent.get("monitor", False):
                    continue
                # The resident's own hand. Never recomputed (rule #5).
                if ent.get("priority_source", "") == "user":
                    continue

                tier = entity_map.get(eid)
                floor = 0
                if tier and _earns_memory_boost(eid):
                    floor = 2 if tier == "stable" else 1

                current = int(ent.get("priority", 0))
                delta = _engagement_delta(ent, floor, current)
                # floor 0 → priority 0: engagement modulates the consolidation
                # boost, it never originates priority on its own.
                target = 0 if floor <= 0 else max(0, min(2, floor + delta))

                if delta:
                    source = "engagement"
                elif target > 0:
                    source = "memory"
                else:
                    source = None

                if target != current or ent.get("priority_source") != source:
                    changes.append({
                        "entity": eid, "from": current, "to": target,
                        "tier": tier or "none", "floor": floor, "delta": delta,
                    })
                ent["priority"] = target
                if source:
                    ent["priority_source"] = source
                else:
                    ent.pop("priority_source", None)
                if delta:
                    ent["engagement_delta"] = delta
                else:
                    ent.pop("engagement_delta", None)
        return changes

    # ------------------------------------------------------------------
    # v8.10 — engagement-based priority learning (Systems, weekly).
    # Ports systems_compile.adjust_priorities_by_engagement (v7.7-B).
    # ------------------------------------------------------------------

    async def async_adjust_priorities_by_engagement(self) -> list:
        return await self._hass.async_add_executor_job(
            self._adjust_priorities_by_engagement
        )

    def _adjust_priorities_by_engagement(self) -> list:
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        engagement: dict = {}
        for row in self._emits_for_engagement(days=7):
            meta = json.loads(row["metadata"]) if row.get("metadata") else {}
            # Alerts are counted per EMISSION (metadata.emits), not per row —
            # reinforcement collapses the week into one row, which kept alerts
            # below ENGAGEMENT_MIN_ALERTS forever. Rows without history (from
            # before emits tracking) carry no evidence and are skipped.
            emits = [t for t in (meta.get("emits") or []) if t >= cutoff]
            if not emits:
                continue
            reactions = [t for t in (meta.get("reactions") or []) if t >= cutoff]
            st = engagement.setdefault(row["key"], {"alerts": 0, "reacted": 0})
            st["alerts"] += len(emits)
            st["reacted"] += min(len(reactions), len(emits))
        if not engagement:
            return []

        changes = []
        path = self._hass.config.path(MONITORED_ENTITIES_RELATIVE_PATH)
        with locked_json_update(path, {"entities": []}) as data:
            for e in data.get("entities", []):
                eid = e.get("entity_id")
                if not eid or e.get("priority_source") == "user":
                    continue
                alerts = reacted = 0
                for key, st in engagement.items():
                    if key.endswith(f":{eid}"):
                        alerts += st["alerts"]
                        reacted += st["reacted"]
                if alerts < ENGAGEMENT_MIN_ALERTS:
                    continue
                rate = reacted / alerts
                # v9.7 — move the DELTA, never `priority` itself. The effective
                # priority is recomputed by _update_priority_from_memory as
                # clamp(memory_floor + delta), so a demotion can always be
                # walked back by a later week of reactions. Writing priority
                # absolutely (with priority_source='learned') is what sealed
                # entities at 0 and made the orienting reflex unreachable.
                if "engagement_delta" not in e:
                    if e.get("priority_source") == "learned":
                        # Legacy stamp, delta not materialised yet. Deriving it
                        # here would need the memory floor, which only the
                        # nightly loop knows. Skip one run; it converges tonight.
                        continue
                    cur = 0
                else:
                    cur = _engagement_delta(e, 0, 0)
                new = cur
                if rate >= ENGAGEMENT_UP_RATE:
                    new = min(cur + 1, ENGAGEMENT_DELTA_MAX)
                elif rate <= ENGAGEMENT_DOWN_RATE:
                    new = max(cur - 1, ENGAGEMENT_DELTA_MIN)
                if new != cur:
                    e["engagement_delta"] = new
                    changes.append({"entity": eid, "delta_from": cur,
                                    "delta_to": new, "rate": round(rate, 2),
                                    "alerts": alerts})
        return changes

    # ------------------------------------------------------------------
    # v9.0 — daily DB cleanup (ports the shell maintenance chain that was
    # deleted with the runtime shell: buffer prune 00:05, event_log 30-day
    # retention, daily_ flags reset). Without it the DB grows unbounded on
    # the Pi's SD card and daily_briefing_enviado never resets.
    # ------------------------------------------------------------------

    async def async_daily_cleanup(self) -> dict:
        return await self._hass.async_add_executor_job(self._daily_cleanup)

    def _daily_cleanup(self) -> dict:
        assert self._conn is not None
        today = _today_local()
        log_cutoff = (
            datetime.now() - timedelta(days=EVENT_LOG_RETENTION_DAYS)
        ).strftime("%Y-%m-%d")
        with self._lock:
            # ts is LOCAL ISO — lexicographic compare against a date prefix
            # is correct ("…-11T…" < "…-12" < "…-12T…") and uses the indexes.
            buf = self._conn.execute(
                "DELETE FROM event_buffer WHERE ts < ?", (today,)
            ).rowcount
            log = self._conn.execute(
                "DELETE FROM event_log WHERE ts < ?", (log_cutoff,)
            ).rowcount
            flags = self._conn.execute(
                "DELETE FROM system_flags WHERE name LIKE 'daily_%'"
            ).rowcount
            self._conn.commit()
            # Bound the WAL on the Pi's SD card (it was growing to ~5× the DB);
            # the nightly cleanup is the quiet moment for a full checkpoint.
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        report = {"event_buffer": buf, "event_log": log, "daily_flags": flags}
        _LOGGER.info("Daily DB cleanup: %s", report)
        return report

    async def async_close(self) -> None:
        await self._hass.async_add_executor_job(self._close)

    def _close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
        _LOGGER.debug("Organic Memory connection closed")
