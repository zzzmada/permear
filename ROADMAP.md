# PERMEAR Roadmap

## v7.3 — Stability & Concurrency Safety

Focus: address concurrency and operational risks discovered post-v7.2 in code review.

- **File locking for JSON writes** (`append_daily.py`, `apply_quick_learning.py`, all memory mutators) — wrap with `fcntl.flock(LOCK_EX)` to prevent race condition between multiple concurrent automations writing to the same daily file.
- **Validate-before-reload for agent automations** (`manage_agent_automations.py`) — write to staging path, run `ha core check` via Supervisor API, only swap if config passes. Prevents bad agent-generated YAML from breaking the whole HA.
- **REST API instead of `.storage` direct reads** (`discover_entities.py`) — use `/api/config/entity_registry/list` rather than reading `.storage/core.entity_registry` raw to avoid race during HA writes.
- **Bulk fetch in pre-briefing** (`build_prebriefing.py`) — replace 30 sequential `/api/states/{id}` calls with single `/api/states` then in-memory dict lookup.
- **Log tail optimization** (`ha_log_monitor.py`) — replace `f.readlines()[-500:]` with reverse-seek block reader to keep O(1) RAM on large logs.
- **Circuit breaker considers JSON parse failures** — increment failure counter when `fix_json` succeeds (signal of provider degradation), not just HTTP errors.

Estimated effort: 8-12h CC. Each item independent, can ship incrementally.

---

## v7.4 — Telegram refinements (deferred from v7.2)

- Edit automations via delta patch (suggested by user Wesio)
- Investigate Telegram button truncation root cause
- Consolidate Card 1 variants
- Lovelace button for `/new_automation`

---

## v8.0 — SQLite & Modular Architecture

Long-term direction surfaced in Gemini Pro architecture review.

- **SQLite for memory backend** — replaces flat JSON for `insights.json`, `archived_errors.json`, `daily/*.json`. Provides ACID, locking, indexed queries, time-based expiry via `DELETE WHERE last_seen < now - 30 days`.
- **FTS5 for semantic search** — replace Jaccard `O(N×M)` dedup with full-text indexing. Scales to longitudinal memory.
- **Pull → Push for sensors** — eliminate `command_line` sensors with `scan_interval`. Replace with `POST /api/states/...` from scripts after mutations. Reduces process spawn and provides instant updates.
- **Modular automation files** — split `permear.yaml` (1500+ lines) into:
  - `telegram.yaml` (handler, callbacks, commands)
  - `memory.yaml` (briefing, weekly, daily reset)
  - `ai_tasks.yaml` (ai_task wrappers)
  - `health.yaml` (circuit breaker, error monitor)
  - `automation_crud.yaml` (CREATE_AUTO, list, remove)
- **Feature flags** in `permear_config.py` — enable/disable cycles independently for gradual rollout.

---

## Not on roadmap (anti-overengineering principle)

These have been considered and explicitly rejected:

- **Python unit tests** — for a single-user project with CC-assisted development, cost (~12h) exceeds value. Smoke tests + Telegram validation suffice.
- **Vector DB** — overkill for household-scale memory. SQLite FTS5 handles it.
- **Multi-provider formal expansion** — HA already supports any provider via AI Task entities. Just docs needed.
- **Web UI** — Lovelace + Telegram cover the needs.

---

## Versioning principles

- **Patch (7.2.x)** — bug fixes only
- **Minor (7.x)** — additions and stability work, backward-compatible
- **Major (8.0)** — SQLite migration with formal migration script

PERMEAR commits to **never** silently break a user's setup. All breaking changes documented in [MIGRATION.md](MIGRATION.md) with rollback path.
