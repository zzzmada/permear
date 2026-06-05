"""
PERMEAR Organic Memory — SQLite data access layer (v7.9-A).
English. Pure data access — no cycle logic, no network, no HA.

Tiers: ephemeral | active | stable | faded
  faded = forgotten (never deleted — forgetting != destroying)
"""
import sqlite3
import os
import json
import re
from datetime import datetime, timedelta

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from permear_config import MEMORY_DB_PATH, MEMORY_FTS_MIN_SCORE, ENTITIES_PATH

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_schema.sql")

# Module-level path — override for testing: import lib.memory_db as mdb; mdb.DB_PATH = "/tmp/test.db"
DB_PATH = MEMORY_DB_PATH


def _fromisoformat(s):
    """Python 3.6 compatible ISO datetime parser (fromisoformat added in 3.7)."""
    s = s[:26]
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # safe concurrency on RPi4
    return conn


def init_db():
    """Create schema if not exists. Idempotent."""
    conn = _connect()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def add_item(content, kind, tier="ephemeral", subject=None, source=None,
             key=None, metadata=None, first_seen=None, last_seen=None,
             mention_count=1):
    """Insert a new memory item. Returns id.
    first_seen/last_seen/mention_count can be overridden for seeding/testing.
    """
    now = datetime.now().isoformat()
    fs = first_seen or now
    ls = last_seen or now
    conn = _connect()
    cur = conn.execute(
        """INSERT INTO memory_items
           (content, kind, tier, subject, key, first_seen, last_seen,
            mention_count, source, metadata)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (content, kind, tier, subject, key, fs, ls, mention_count, source,
         json.dumps(metadata) if metadata else None)
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id


def _fts_query(content):
    """Sanitize content into a safe FTS MATCH query (OR of significant tokens)."""
    tokens = [t for t in re.findall(r'\w+', content.lower()) if len(t) > 3]
    return " OR ".join(tokens[:10]) if tokens else content[:20]


def find_similar(content, kind=None, limit=1):
    """FTS search for similar content. Returns list of dicts (most similar first).
    Used to decide reinforce-vs-create. bm25: more negative = more similar."""
    conn = _connect()
    q = """SELECT m.*, bm25(memory_fts) AS score
           FROM memory_fts JOIN memory_items m ON m.id = memory_fts.rowid
           WHERE memory_fts MATCH ?"""
    params = [_fts_query(content)]
    if kind:
        q += " AND m.kind = ?"
        params.append(kind)
    q += " ORDER BY score LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        rows = []  # FTS query parse issue -> treat as no match
    conn.close()
    return [dict(r) for r in rows]


def find_by_key(key, within_days=None):
    """Exact canonical-key match. Deterministic, works with empty corpus.
    Optionally restrict to items seen within N days."""
    if not key:
        return []
    conn = _connect()
    q = "SELECT * FROM memory_items WHERE key = ?"
    params = [key]
    if within_days:
        cutoff = (datetime.now() - timedelta(days=within_days)).isoformat()
        q += " AND last_seen >= ?"
        params.append(cutoff)
    q += " ORDER BY last_seen DESC LIMIT 1"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def reinforce(item_id):
    """Increment mention_count and bump last_seen."""
    now = datetime.now().isoformat()
    conn = _connect()
    conn.execute(
        "UPDATE memory_items SET mention_count = mention_count + 1, last_seen = ? WHERE id = ?",
        (now, item_id)
    )
    conn.commit()
    conn.close()


def add_or_reinforce(content, kind, key=None, **kwargs):
    """Reinforce-or-create with 2 layers:
      1) canonical key (deterministic) — if key matches a recent item, reinforce
      2) FTS similarity (semantic) — fallback for free text without a key
    Returns (item_id, was_new: bool, via: 'key'|'fts'|'new').

    NOTE: MEMORY_FTS_MIN_SCORE is currently -1.5. With small corpus bm25 ~= 0,
    so FTS layer rarely triggers at start (observations are naturally new each day).
    Raise threshold to ~-5.0 once corpus > 20 items. Revisit in v7.9.
    """
    # Layer 1: canonical key (deterministic — works even with 1 item in corpus)
    if key:
        hit = find_by_key(key)
        if hit:
            reinforce(hit[0]["id"])
            return hit[0]["id"], False, "key"
    # Layer 2: FTS semantic similarity
    similar = find_similar(content, kind=kind, limit=1)
    if similar and similar[0].get("score", 0) <= MEMORY_FTS_MIN_SCORE:
        reinforce(similar[0]["id"])
        return similar[0]["id"], False, "fts"
    # New item
    new_id = add_item(content, kind, key=key, **kwargs)
    return new_id, True, "new"


def run_tier_maintenance():
    """v7.9-A — Apply tier transitions based on thresholds from permear_config.
    Returns dict with counts of each transition for reporting.
    Fade takes priority over promotion within ephemeral (silence wins over count).

    v7.9-D: observation promoted ephemeral→active becomes 'pattern'.
    Repetition that caused the promotion IS the evidence of pattern emergence.
    All other kind transitions (demotion, fade, active→stable, non-observation
    promotions) preserve the original kind.
    """
    from permear_config import (
        MEMORY_EPHEMERAL_FADE_DAYS, MEMORY_ACTIVE_PROMOTE_MENTIONS,
        MEMORY_ACTIVE_PROMOTE_WINDOW, MEMORY_STABLE_PROMOTE_MENTIONS,
        MEMORY_STABLE_PROMOTE_WINDOW, MEMORY_ACTIVE_DEMOTE_DAYS,
        MEMORY_STABLE_DEMOTE_DAYS
    )
    now = datetime.now()
    counts = {
        "promoted_active": 0, "promoted_stable": 0,
        "demoted_active": 0, "demoted_ephemeral": 0, "faded": 0,
        "observation_to_pattern": 0,
    }
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM memory_items WHERE tier != 'faded'"
    ).fetchall()
    for r in rows:
        item = dict(r)
        tier = item["tier"]
        first_seen = _fromisoformat(item["first_seen"])
        last_seen = _fromisoformat(item["last_seen"])
        mentions = item["mention_count"]
        age_since_first = (now - first_seen).days
        silence = (now - last_seen).days
        new_tier = tier

        if tier == "ephemeral":
            # fade takes priority: silence >= threshold -> fade
            if silence >= MEMORY_EPHEMERAL_FADE_DAYS:
                new_tier = "faded"
                counts["faded"] += 1
            # promote only if not fading, reinforced enough, and not an interaction record
            # (interactions are context, never promotable — they decay normally)
            elif (item["source"] != "interaction"
                  and mentions >= MEMORY_ACTIVE_PROMOTE_MENTIONS
                  and age_since_first <= MEMORY_ACTIVE_PROMOTE_WINDOW):
                new_tier = "active"
                counts["promoted_active"] += 1

        elif tier == "active":
            if silence >= MEMORY_ACTIVE_DEMOTE_DAYS:
                new_tier = "ephemeral"
                counts["demoted_ephemeral"] += 1
            elif mentions >= MEMORY_STABLE_PROMOTE_MENTIONS and age_since_first <= MEMORY_STABLE_PROMOTE_WINDOW:
                new_tier = "stable"
                counts["promoted_stable"] += 1

        elif tier == "stable":
            if silence >= MEMORY_STABLE_DEMOTE_DAYS:
                new_tier = "active"
                counts["demoted_active"] += 1

        if new_tier != tier:
            # v7.9-D: observation promoted ephemeral→active becomes a pattern.
            # Only this one transition changes kind; all others preserve it.
            new_kind = item["kind"]
            if tier == "ephemeral" and new_tier == "active" and item["kind"] == "observation":
                new_kind = "pattern"
                counts["observation_to_pattern"] += 1
            conn.execute(
                "UPDATE memory_items SET tier = ?, kind = ? WHERE id = ?",
                (new_tier, new_kind, item["id"])
            )
    conn.commit()
    conn.close()
    return counts


def query_by_tier(tier, kind=None):
    conn = _connect()
    q = "SELECT * FROM memory_items WHERE tier = ?"
    params = [tier]
    if kind:
        q += " AND kind = ?"
        params.append(kind)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def all_items(kind=None):
    conn = _connect()
    if kind:
        rows = conn.execute(
            "SELECT * FROM memory_items WHERE kind = ?", (kind,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM memory_items").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats():
    """Counts by tier and kind — for the future sensor."""
    conn = _connect()
    rows = conn.execute(
        "SELECT tier, kind, COUNT(*) c FROM memory_items GROUP BY tier, kind"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_consolidated():
    """Count items in active or stable tier (consolidated memory)."""
    conn = _connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM memory_items WHERE tier IN ('active','stable')"
    ).fetchone()[0]
    conn.close()
    return n


def consolidated_with_entity():
    """Count distinct entity IDs linked to consolidated (active/stable) memory items.
    Only keys with a dot in the entity part are real HA entity IDs (e.g. event:cover.xyz).
    """
    conn = _connect()
    n = conn.execute(
        """SELECT COUNT(*) FROM (
               SELECT DISTINCT SUBSTR(key, INSTR(key,':')+1) AS eid
               FROM memory_items
               WHERE tier IN ('active','stable')
                 AND key IS NOT NULL
                 AND INSTR(key, ':') > 0
                 AND INSTR(SUBSTR(key, INSTR(key,':')+1), '.') > 0
           )"""
    ).fetchone()[0]
    conn.close()
    return n


def set_flag(name: str, value: str) -> None:
    """UPSERT em system_flags."""
    now = datetime.now().isoformat()
    conn = _connect()
    conn.execute(
        "INSERT INTO system_flags(name, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (name, value, now)
    )
    conn.commit()
    conn.close()


def get_flag(name: str, default: str = None) -> str:
    """SELECT value WHERE name=?. Retorna default se não existir."""
    conn = _connect()
    row = conn.execute(
        "SELECT value FROM system_flags WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def reset_daily_flags() -> int:
    """DELETE flags com prefixo 'daily_' — chamado no reset 00:00. Retorna rows afetadas."""
    conn = _connect()
    cur = conn.execute("DELETE FROM system_flags WHERE name LIKE 'daily_%'")
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def record_event(tipo: str, detalhe: str, entity_id: str = None,
                 canal: str = 'evento') -> int:
    """Insere evento no event_buffer. Retorna id."""
    now = datetime.now().isoformat()
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO event_buffer (ts, tipo, detalhe, entity_id, canal) VALUES (?,?,?,?,?)",
        (now, tipo, detalhe, entity_id or None, canal)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_today_events() -> list:
    """Eventos de HOJE do event_buffer. Retorna dicts com {id,ts,tipo,detalhe,entity_id,canal}."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM event_buffer WHERE date(ts) = date('now') ORDER BY ts"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_today_events() -> int:
    """Contagem rápida de eventos de hoje."""
    conn = _connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM event_buffer WHERE date(ts) = date('now')"
    ).fetchone()[0]
    conn.close()
    return n


def cleanup_old_events() -> int:
    """DELETE eventos de dias anteriores. Retorna rows afetadas."""
    conn = _connect()
    cur = conn.execute("DELETE FROM event_buffer WHERE date(ts) < date('now')")
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def get_today_interactions() -> list:
    """Interações Telegram/voz de HOJE (source='interaction'). Retorna {content, canal}."""
    conn = _connect()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT content, metadata FROM memory_items "
        "WHERE source='interaction' AND date(last_seen) = ? ORDER BY last_seen",
        (today,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        result.append({"content": r["content"], "canal": meta.get("canal", "desconhecido")})
    return result


def update_metadata(item_id, patch: dict) -> bool:
    """Merge `patch` into item's metadata JSON. Returns True if updated."""
    conn = _connect()
    row = conn.execute(
        "SELECT metadata FROM memory_items WHERE id = ?", (item_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return False
    current = json.loads(row["metadata"]) if row["metadata"] else {}
    current.update(patch)
    conn.execute(
        "UPDATE memory_items SET metadata = ? WHERE id = ?",
        (json.dumps(current), item_id)
    )
    conn.commit()
    conn.close()
    return True


def get_today_emitted_keys() -> list:
    """Keys emitidas hoje pelo ARAS (source='heartbeat') — para novelty check."""
    conn = _connect()
    rows = conn.execute(
        "SELECT key FROM memory_items "
        "WHERE source='heartbeat' AND date(last_seen) = date('now') AND key IS NOT NULL"
    ).fetchall()
    conn.close()
    return [r["key"] for r in rows]


def get_recent_emits(minutes=15) -> list:
    """Items source='heartbeat' nos últimos N minutos, com id+key+metadata."""
    cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
    conn = _connect()
    rows = conn.execute(
        "SELECT id, key, metadata FROM memory_items "
        "WHERE source='heartbeat' AND last_seen >= ?",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_emits_for_engagement(days=7) -> list:
    """Items source='heartbeat' com key dos últimos N dias — para aggregate_engagement."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = _connect()
    rows = conn.execute(
        "SELECT key, metadata FROM memory_items "
        "WHERE source='heartbeat' AND last_seen >= ? AND key IS NOT NULL",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_interactions(days=7) -> list:
    """Conteúdo das interações Telegram/voz (source='interaction') dos últimos N dias — para weekly."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = _connect()
    rows = conn.execute(
        "SELECT content, metadata FROM memory_items "
        "WHERE source='interaction' AND last_seen >= ? "
        "ORDER BY last_seen DESC",
        (cutoff,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        result.append({"content": r["content"], "canal": meta.get("canal", "desconhecido")})
    return result


def get_recent_memories(days=7, source='daily'):
    """Return memory contents from the last N days for weekly compile.
    Replaces memorias_do_dia[] JSON read eliminated in S-daily-1."""
    conn = _connect()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT content FROM memory_items "
        "WHERE source=? AND last_seen >= ? "
        "ORDER BY last_seen DESC",
        (source, cutoff)
    ).fetchall()
    conn.close()
    return [r['content'] for r in rows]


def update_priority_from_memory(dry_run=False, monitored_path=None):
    """Loop tiers→priority: consolidated memory items raise entity priority.

    Rules:
    - Only monitor=True entities in monitored_entities.json
    - Never touches priority_source='user' or 'learned' (human curation wins)
    - active tier  → priority = max(current, 1)
    - stable tier  → priority = max(current, 2)
    - Sets priority_source='memory' on changed entries (write mode only)

    dry_run=True: compute changes without writing (safe for testing).
    Returns list of {entity, from, to, tier}.
    """
    if monitored_path is None:
        monitored_path = ENTITIES_PATH

    consolidated = [
        item for item in all_items()
        if item["tier"] in ("active", "stable") and item.get("key")
    ]

    # entity_id → strongest consolidated item (stable beats active)
    entity_map = {}
    for item in consolidated:
        key = item["key"]
        if ":" not in key:
            continue
        entity_id = key.split(":", 1)[1]
        if "." not in entity_id:
            continue
        existing = entity_map.get(entity_id)
        if existing is None:
            entity_map[entity_id] = item
        elif item["tier"] == "stable" and existing["tier"] == "active":
            entity_map[entity_id] = item

    if not entity_map:
        return []

    changes = []

    def _compute(entities_list, write=False):
        for ent in entities_list:
            eid = ent.get("entity_id")
            if eid not in entity_map:
                continue
            if not ent.get("monitor", False):
                continue
            if ent.get("priority_source", "") in ("user", "learned"):
                continue
            mem_item = entity_map[eid]
            target = 2 if mem_item["tier"] == "stable" else 1
            current = int(ent.get("priority", 0))
            new_p = max(current, target)
            if new_p != current:
                changes.append({
                    "entity": eid, "from": current,
                    "to": new_p, "tier": mem_item["tier"],
                })
                if write:
                    ent["priority"] = new_p
                    ent["priority_source"] = "memory"

    if dry_run:
        try:
            with open(monitored_path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"entities": []}
        _compute(data.get("entities", []), write=False)
    else:
        from lib.memory import locked_update
        with locked_update(monitored_path, default={"entities": []}) as data:
            _compute(data.get("entities", []), write=True)

    return changes
