# Changelog

All notable changes to PERMEAR are documented here.

This project follows Semantic Versioning.

---

## [7.2.0] — 2026-05-17

### Added

- Dual LLM architecture:
  - `conversation.process` for interactive chat/voice
  - `ai_task.generate_data` for structured background tasks
- Automatic fallback between providers
- Active forgetting with archive after 30 days
- Shared `lib/` modules (`memory.py`, `agent.py`, `logs.py`)
- `sensor_permear_health.py`
- Real-time log monitoring with Telegram alerts
- `[Silence 24h]` Telegram button for noisy errors
- `/list_automations` Telegram command
- Automation creation flow with approval buttons
- `memory/lovelace_card.yaml`
- `MIGRATION.md`

### Changed

- `weekly_compile.py` rewritten to use structured `ai_task` outputs
- `apply_quick_learning.py` now uses direct structured responses
- `manage_agent_automations.py` gained JSON output and extra commands
- `discover_entities.py` now supports `--add` and `--remove`
- Daily memory keys standardized to English
- `permear_config.py` expanded with provider and health settings

### Fixed

- Provider 429 errors no longer break cycles
- Empty LLM responses now trigger fallback automatically
- Circuit breaker state persists across HA restarts
- Telegram inline keyboard formatting issues

### Removed

- Old markdown fence-stripping logic
- Legacy retry/parsing code
- `update_daily_memory.py`

---

## [7.1.x] — Internal development cycle

Main work before 7.2 stabilization:

- DeepSeek + Gemini fallback
- Shared `lib/` refactor
- AI Task migration
- Automation generation flow
- Lovelace health card
- Defensive retry/fallback hardening

Never published publicly.

---

## [7.0.x] — Internal development cycle

- Active forgetting
- Circuit breaker architecture
- Health sensor
- Real-time error monitoring

Never published publicly.

---

## [6.x] — Internal prototypes

Experimental versions focused on Telegram automation flows and inline keyboard behavior.

Never published publicly.

---

## [5.7] — First public release

Initial public architecture with:

- Persistent memory files
- Daily and weekly cycles
- Telegram integration
- Entity discovery
- Pre-briefings and daily briefings

---

## Upgrade paths

| From | To | Guide |
|---|---|---|
| 5.7 | 7.2.0 | `MIGRATION.md` |
