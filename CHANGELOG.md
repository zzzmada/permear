# Changelog

All notable changes to PERMEAR will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [7.2.0] - 2026-05-17

### Major changes

**Dual LLM path architecture.** PERMEAR now separates interactive (chat/voice) from non-interactive (cycles) LLM calls. Interactive uses `conversation.process` with a Tools-capable provider (Gemini); non-interactive uses native `ai_task.generate_data` for structured output (DeepSeek primary, Gemini fallback).

**Automatic provider fallback.** Every `ai_task` call has a 3-stage pattern: pre-check via health sensor → primary attempt → secondary attempt. Resilient to rate limits and provider outages.

**Active forgetting.** Patterns and pending items not mentioned in 30+ days move to `insights_archived.json`. Keeps the perennial memory focused on the actually-relevant.

**Shared library (`lib/`).** `memory.py`, `agent.py`, `logs.py` extracted from duplicated code across scripts. ~700 lines of duplication removed.

### Added

- `lib/memory.py` — JSON/YAML I/O (load_json, save_json, parse_iso, load_yaml, save_yaml)
- `lib/agent.py` — Circuit breaker state, daily stats, health summary helpers
- `lib/logs.py` — Error classification (NOISY/SELF/HA, transient provider errors)
- `apply_daily_memory.py` — Save LLM-extracted memories to today's daily file
- `build_automation_spec.py` — Transform raw spec from ai_task into full HA automation
- `briefing_simple.py` — Pure-Python fallback briefing when LLM fails 3 retries
- `circuit_breaker.py` — Thin entry point delegating to lib/agent.py
- `forget_old_items.py` — 30-day retention enforcement
- `get_monitored_entities_text.py` — Format entities for ai_task prompts
- `ha_update_manager.py` — install/skip/check_backup commands for HA updates
- `log_fallback.py` — Track secondary provider usage in daily stats
- `manage_archived.py` — Silenced-24h errors with auto-expiration
- `process_log_event.py` — Thin entry point delegating to lib/logs.py
- `sensor_permear_health.py` — 4-state health sensor (all_ok / recovering / fallback_active / degraded)
- `write_pending_spec.py` — Sidesteps 255-char input_text limit for spec passing
- `memory/lovelace_card.yaml` — Snippet to paste into Lovelace dashboard
- `MIGRATION.md` — Guide for users upgrading from v5.x
- Real-time error monitor with [Silence 24h] Telegram button
- Automation creation flow via Telegram with [Create / Adjust / Discard] buttons
- `/list_automations` Telegram command with [Remove N] per row

### Changed

- `weekly_compile.py` — Now receives 3 structured JSON inputs from focused ai_task calls (soul, users, insights), instead of one giant prompt with markdown fence-stripping
- `apply_quick_learning.py` — Receives restriction string directly from ai_task structured output, no parsing
- `manage_agent_automations.py` — Added `--json` flag, new commands `details`, `disable`, `enable`, `stats`
- `discover_entities.py` — Added `--add ENTITY FRIENDLY_NAME` and `--remove ENTITY` flags
- `build_briefing.py` / `build_prebriefing.py` — Inject health summary line from circuit breaker state
- `permear_config.py` — Added `AI_TASK_PRIMARY`, `AI_TASK_SECONDARY`, `NOISY_COMPONENTS`, `SELF_COMPONENTS`
- All daily file keys now in English: `events`, `interactions`, `daily_memories`, etc.

### Removed

- `update_daily_memory.py` — Replaced by `apply_daily_memory.py` (ai_task-based)
- Inline retry/parse logic in weekly_compile (no longer needed with ai_task)
- Markdown fence-stripping helpers (no longer needed)
- `truncation_detection` in weekly_compile (no longer needed)

### Fixed

- Provider 429 errors no longer halt non-interactive cycles (`continue_on_error: true` everywhere + fallback)
- Empty LLM responses now gracefully fall back to Python or secondary provider
- Circuit breaker state survives across HA restarts (file-based)
- YAML inline keyboards now use flat string list format (HA splits internally by `:`)

### Notes

- Telegram inline keyboards: first character of button labels is truncated on some Telegram/HA versions. PERMEAR uses `". Label"` (dot prefix) as a workaround — first char eaten is harmless dot.
- BYOK setup is strongly recommended for DeepSeek; see README "Configure LLMs" section.

---

## [7.1.0] - 2026-05-16 (internal, not published)

Internal development version. Includes:
- Sprint A: secrets.yaml conversion, agent_id rename, lib/ refactor
- Sprint B: Shared `lib/` module
- Sprint C: Lovelace card for permear_health (later simplified)
- Sprint E: `apply_quick_learning` via ai_task
- Sprint F: CREATE_AUTO via ai_task structured output
- Sprint G: weekly_compile in 3 focused ai_task calls
- Sprint H: DeepSeek primary, Gemini secondary
- Sprint I: Automatic fallback DeepSeek → Gemini with sensor reflection
- Sprint I.1: Defensive hardening — pre-check via sensor + continue_on_error on fallback chain

This version was never published. Stabilized and consolidated into 7.2.0.

---

## [7.0.0] - 2026-04 (internal, not published)

Internal development version. Highlights:
- Shared library `lib/` extracted
- Active forgetting (30-day retention)
- Health sensor with daily stats
- Circuit breaker + retry pattern for conversation.process
- Real-time error monitor with archived 24h
- Semantic dedup (Jaccard 0.7) in weekly compilation

This version was never published. Stabilized and consolidated into 7.2.0.

---

## [6.x] - 2026-Q1 (internal, not published)

Internal versions for the automation creation flow (`/new_automation`) via Telegram cards with buttons. Several iterations on inline_keyboard format quirks of HA's `telegram_bot` integration. Stabilized into 7.2.0.

---

## [5.7] - 2025

First public release. Foundational architecture:
- Daily files + perennial memory (soul, users, insights)
- Briefing 21h + pre-briefings every 30 min
- Weekly compilation (single LLM call)
- Entity discovery from voice-exposed entities
- Telegram bot integration

---

## Upgrade paths

| From | To | Effort | Guide |
|---|---|---|---|
| 5.7 | 7.2.0 | ~30 min | [MIGRATION.md](MIGRATION.md) |
| 7.0 / 7.1 (internal) | 7.2.0 | n/a | Internal versions never published |
