# Changelog

All notable changes to PERMEAR will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [7.3.0] - 2026-05-19

### Stability & Concurrency Safety

This release focuses on hardening v7.2 against concurrency, performance, and operational risks discovered in code review. No new user-facing features — only safer and faster execution.

### Added

- **File locking (`fcntl.flock`)** in `lib/memory.py` — new `save_json()` with atomic write (temp + rename) and new `locked_update()` context manager for atomic read-modify-write.
- **`validate_ha_config()`** in `manage_agent_automations.py` — calls Supervisor API `check_config` before reload; automatic rollback if invalid YAML would break HA.
- **Reverse-seek log tail** in `ha_log_monitor.py` — `read_last_lines()` with O(1) RAM regardless of log size. Safe for logs of any size up to 10MB cap.
- **AI Task entities in `secrets.yaml`** — `permear_ai_task_primary` and `permear_ai_task_secondary` replace hardcoded `entity_id` references. Swap providers without editing automations.
- **JSON parse failure tracking in circuit breaker** — `fix_json()` returns tuple `(parsed, needed_repair)`. When repair is needed, circuit breaker logs as degradation signal (detects inferential degradation before HTTP errors).

### Changed

- **`build_prebriefing.py`** — single `/api/states` bulk fetch instead of N sequential `/api/states/{id}` calls. Latency drops from ~5-10s to <2s on RPi4 with 30 monitored entities.
- **All memory-mutating scripts migrated to `locked_update`:**
  - `append_daily.py`
  - `apply_daily_memory.py`
  - `apply_quick_learning.py`
  - `weekly_compile.py`
  - `forget_old_items.py`
  - `manage_archived.py`
  - `lib/agent.py` (circuit breaker mutators)
- **`manage_agent_automations.py`** — `cmd_create` and `cmd_remove` now call `validate_ha_config()` before reload; rollback automatic if invalid.

### Fixed

- **Race condition in concurrent daily writes** — multiple automations writing to the same daily file simultaneously no longer lose updates. Validated with stress test: 50 concurrent subprocess writes, 50/50 events persisted with all unique values.
- **`split(b'\n')` trailing empty bytes** in reverse-seek tail — filtered before slice (would otherwise occasionally produce one fewer line than requested).

### Removed

- Direct dependency on `/api/config/entity_registry/list` REST endpoint — endpoint does not exist as REST (WebSocket only). `discover_entities.py` continues using `.storage/core.entity_registry` raw read; risk acceptable because HA writes atomically via temp+rename. Documented as won't-fix.

### Documentation

- New [ROADMAP.md](ROADMAP.md) covering v7.4 (Telegram polish), v7.5 (ARAS Filter — salience evaluator inspired by Ascending Reticular Activating System), v7.6 (Memory tiers — ephemeral/active/stable), v7.7-v7.8 (pre-HACS hardening), v8.0 (SQLite backend), v9.0 (HACS preparation), v10.0 (HACS official).
- README slimmed and refocused on persona ("HA hobbyist with technical knowledge").
- MIGRATION.md updated with v7.2 → v7.3 path (minimal — automatic for most users).

### Notes for users on v7.2

Upgrade is **safe and almost transparent**. The only required action is adding two new lines to `secrets.yaml`:

```yaml
permear_ai_task_primary: ai_task.openrouter_deepseek_v3
permear_ai_task_secondary: ai_task.google_ai_task
```

(adjust entity IDs to match your actual setup). Everything else updates automatically when you copy the new files.

---

## [7.2.0] - 2026-05-17

### Major changes

**Dual LLM path architecture.** PERMEAR separates interactive (chat/voice) from non-interactive (cycles) LLM calls. Interactive uses `conversation.process` with a Tools-capable provider (Gemini); non-interactive uses native `ai_task.generate_data` for structured output (DeepSeek primary, Gemini fallback).

**Automatic provider fallback.** Every `ai_task` call has a 3-stage pattern: pre-check via health sensor → primary attempt → secondary attempt. Resilient to rate limits and provider outages.

**Active forgetting.** Patterns and pending items not mentioned in 30+ days move to `insights_archived.json`.

**Shared library (`lib/`).** `memory.py`, `agent.py`, `logs.py` extracted from duplicated code across scripts.

### Added

- `lib/` package (memory, agent, logs)
- `apply_daily_memory.py`, `build_automation_spec.py`, `briefing_simple.py`
- `circuit_breaker.py`, `forget_old_items.py`, `get_monitored_entities_text.py`
- `ha_update_manager.py`, `log_fallback.py`, `manage_archived.py`
- `process_log_event.py`, `sensor_permear_health.py`, `write_pending_spec.py`
- `memory/lovelace_card.yaml`
- Real-time error monitor with [Silence 24h] Telegram button
- Automation creation flow with [Create / Adjust / Discard] buttons
- `/list_automations` Telegram command

### Changed

- `weekly_compile.py` — 3 structured JSON inputs (soul/users/insights) instead of one prompt
- `apply_quick_learning.py` — direct string from ai_task structured output
- `manage_agent_automations.py` — `--json` flag, new commands (details, disable, enable, stats)
- All daily file keys now in English

---

## [7.1.0] - 2026-05-16 (internal, not published)

Internal development version with sprints A-I.1 (lib refactor, ai_task migration, fallback pattern). Never published. Consolidated into 7.2.0.

---

## [7.0.0] - 2026-04 (internal, not published)

Internal development version with shared library, active forgetting, health sensor, circuit breaker, real-time error monitor. Consolidated into 7.2.0.

---

## [6.x] - 2026-Q1 (internal, not published)

Internal versions for automation creation flow (`/new_automation`) via Telegram cards. Consolidated into 7.2.0.

---

## [5.7] - 2025

First public release. Foundational architecture:
- Daily files + perennial memory
- Briefing 21h + pre-briefings every 30 min
- Weekly compilation (single LLM call)
- Entity discovery from voice-exposed entities
- Telegram bot integration

---

## Upgrade paths

| From | To | Effort | Guide |
|---|---|---|---|
| 7.2.0 | 7.3.0 | ~5 min | [MIGRATION.md](MIGRATION.md) — just add 2 secrets |
| 5.7 | 7.3.0 | ~30 min | [MIGRATION.md](MIGRATION.md) |
