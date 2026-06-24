# Changelog

All notable changes to PERMEAR will be documented in this file.

The format is inspired by Keep a Changelog and the project follows Semantic Versioning where applicable.

---

## [9.1.1] — June 2026

Patch release. Two fixes so the system honors what you tell it to ignore.

### Fixed

- **Device-offline messages no longer notify**: when a device stops responding (a TV losing network overnight, for example), PERMEAR no longer sends a Telegram message about it. Availability is now treated purely as a health signal — reflected in `permear_health` and consultable when you want it — rather than an event that interrupts you. This also means a device's connectivity dropping is no longer something the filter can surface on its own.
- **Declined suggestions stop reappearing**: when you decline an automation suggestion tied to a specific device (for example, "I don't want the curtains closed automatically"), that suggestion is now marked declined and stops showing up in the daily briefing, instead of being re-presented every day.

---
## [9.1.0] — June 2026

Quality and noise-reduction release. Refines what earns your attention, makes configuration easier, and removes the last internal code duplication.

### Added

- **Reconfigure providers without reinstalling**: the four LLM providers and the Telegram chat ID can now be changed from **Configure** (options), not only at install. Switch models or accounts from the UI.

### Changed

- **Less noise from trivial state changes**: plain switches and repeated occupancy/motion no longer earn a memory-based attention boost on their own. They still consolidate as memory, but they only surface when genuinely anomalous (an odd hour) or when you mark them as a priority. Doors, windows, climate, covers, media and dimmers with real brightness are unaffected.
- **Health sensor reflects the current state**: `permear_health` now shows `fallback_ativo` only while a fallback is actually recent, returning to `tudo_ok` once the primary provider recovers. The daily fallback count stays as a historical attribute.
- **Single source of truth for provider fallback**: the Heartbeat now shares the same fallback choreography as the other cycles. Internal cleanup with no behavior change.

---
## [9.0.0] — June 2026

First public release of the component era. Bundles the internal releases v8.6 through v8.10 — the public version line jumps from v8.5 directly to v9.0.

PERMEAR is now a single in-process Home Assistant custom component. Zero shell remains at runtime: no shell_command, no helper scripts, no tokens, no YAML configuration.

### Added

- **UI-only setup**: config flow + options flow. Providers, Telegram chat ID, sensitivity, resident and cycle schedules all live in the config entry (encrypted `.storage`). Saving options reloads the integration — no restart needed.
- **In-process event capture**: native state-change listener → SQLite dual write, metadata extracted directly from the state object. First-run bootstrap: entity discovery runs right after setup, so capture works on day one.
- **In-process cycles**: Heartbeat (hourly attention window + ARAS salience filter), Sleep Consolidation (nightly briefing + memory extraction + tier maintenance), Systems Consolidation (weekly compile with deterministic co-occurrence), Wake (daily entity discovery from conversation exposure).
- **Native status sensors** grouped under a PERMEAR device: `permear_attention`, `permear_health`, `permear_config`, `permear_daily_memory`, `permear_household_data`.
- **In-process Telegram surface**: conversation with provider fallback, automation creation/removal cards, priority cards, update cards. Agent-created automations are restricted to a safe action-domain allowlist.
- **In-process error monitor**: filtered Telegram error cards with a 24h silence button, secret redaction, and a Repair issue when `system_log: fire_event: true` is missing.
- **Daily database maintenance**: event buffer pruning, 30-day event-log retention, daily flag reset.

### Changed

- ARAS sensitivity (`sensitive` / `balanced` / `quiet`) is the only attention knob; the emit threshold self-regulates with memory maturity.
- All user-facing output is Brazilian Portuguese; code, logs and identifiers are English.

### Removed

- The entire shell architecture: `shell_command` bridges, capture/cycle/maintenance scripts, `permear.yaml`, `secrets.yaml` usage, `input_text` staging entities, REST/token transport, and the YAML automations that orchestrated the cycles.

---

## [8.8] — June 2026 (Internal Development)

### Added

#### In-process event capture (HACS migration, phase 1)

New `custom_components/permear` — event capture via native HA state-change listener, in-process. No shell call, no REST API, no token file.

- Metadata extracted directly from state object (closed-list per-domain in `const.METADATA_ATTRIBUTES`)
- Domain filter (`CAPTURE_DOMAINS`) excludes continuous noise (numeric sensors, weather, scripts)
- Dual-write: `event_buffer` (daily salience) + `event_log` (long-term correlation)
- Legacy shell capture chain turned OFF: `events.yaml` triggers, `record_event.py`, `input_text.permear_event_metadata`, `.ha_token` REST fetches

#### Priority decay for memory-source entities

`update_priority_from_memory()` now decays priority when entities leave the consolidated tier set:
- Priority source `memory`: 2→1 (exited stable), 1→0 (exited active)
- `user` and `learned` priorities never touched (rule #31)

#### Heartbeat temporal window

`build_heartbeat.py` processes only events from the last 90 minutes (not the full day's buffer). Reduces ARAS candidate pool by ~87%.

### Changed

- v8.0→v8.5 schemas preserved (no migration needed — component writes same table structure)
- `run_memory_maintenance.py` now runs decay alongside tier maintenance

### Removed

- `automation.permear_daily_event_buffer` — turned off (replaced by the component)
- `input_text.permear_event_metadata` — staging area no longer needed

---

## [8.7] — June 2026 (Internal Development)

### Added

#### Systems insights in the database

Systems Consolidation output now writes directly to `memory_items` with `source='systems'`:
- Action items, suggestions, and pending automation specs persist across restarts
- No more ephemeral JSON output files

#### guidelines.json reverts to curated-only

`guidelines.json` is now strictly read-only for the system:
- Residents are curated by the user, never evolved by LLM
- `forget_old_items.py` becomes a no-op (tier maintenance replaces pruning)

### Changed

- Systems Consolidation prompt now reads insights from DB instead of legacy JSON files
- `build_systems_prompt.py` sources 7-day Organic Memory summary via `get_system_insights()`

---

## [8.6] — May 2026 (Internal Development)

### Added

#### Temporal event correlation

- `correlate_events.py` — deterministic co-occurrence detector over `event_log` (requires ≥3 distinct days)
- Systems Consolidation injects correlated pairs into the weekly prompt → LLM evaluates automation candidates
- Correlation is pure arithmetic (count-based), not ML/LLM

#### Metadata capture fix (legacy chain)

- Entity_id validation in `record_event.py`: rejects non-entity strings (`-`, `while`, `mesmo`, empty, no-dot)
- Metadata fetched from HA REST API via long-lived token (instead of broken supervisor proxy)
- Safe fallback to `{}` on any API error

---

## [8.5] — June 2026 (Draft Publication)

### Added

- `hacs.json` — HACS compatibility metadata
- `configuration_example.yaml` — annotated template for new users
- Publication-focused `.gitignore` cleanup

### Changed

- All PERMEAR package configuration consolidated into `packages/permear.yaml`
- `input_text.permear_event_metadata` added for v8.6 metadata pipeline

---

## [8.2.0] — 2026-06-02

### Added

#### Configurable cycle schedules

All cycle schedules now live in `permear.yaml` under a dedicated `cycles:` section.

Available settings:

- `heartbeat_start`
- `heartbeat_end`
- `sleep_time`
- `systems_time`

A new synchronization flow automatically updates Home Assistant `input_datetime` entities whenever `permear.yaml` changes.

### Changed

- `sensor.permear_config` now exposes schedule configuration alongside provider configuration.
- Cycle automations consume `input_datetime.*` entities instead of hardcoded times.
- Schedule changes no longer require editing automation YAML files.

### Notes

Heartbeat frequency remains fixed because Home Assistant `time_pattern` triggers do not support dynamic intervals.

---

## [8.1.0] — 2026-06-02

### Added

#### Systems Consolidation context restoration

Systems Consolidation now injects a 7-day Organic Memory summary generated by `build_systems_prompt.py`.

### Changed

#### ARAS configuration simplification

Replaced `ARAS_THRESHOLD_MIN` / `ARAS_THRESHOLD_MAX` with a single `aras.sensitivity` parameter (`sensitive`, `balanced`, or `quiet`).

#### Entity standardization

Renamed sensors to `permear_*` namespace:
- `sensor.memoria_dia_atual` → `sensor.permear_daily_memory`
- `sensor.memoria_perene` → `sensor.permear_household_data`

#### Publication readiness

- All PERMEAR package configuration consolidated into `packages/permear.yaml`
- Created `configuration_example.yaml`
- Added `hacs.json`
- Added publication-focused `.gitignore` cleanup
- AI provider configuration centralized in `permear.yaml`

### Removed

- Dead weekly memory sensor loop
- Unused ARAS constants: `ARAS_SUPPRESS_THRESHOLD`, `ARAS_GRAY_LLM_THRESHOLD`

---

## [8.0.0] — 2026-06-02

Major Release — first publication-ready version. Entire codebase standardized, translated to English, generalized for public use, and migrated to SQLite-based Organic Memory.

### Added

#### Package architecture

- `packages/permear.yaml`
- Simplified Home Assistant installation flow

#### Organic Memory (SQLite)

New database architecture: `memory_items`, `memory_fts`, `event_buffer`, `system_flags`.

Tiered memory model: `ephemeral` → `active` → `stable` → `faded`.

#### ARAS Filter

- Dynamic attention threshold
- Household-size-aware scaling
- Memory-driven prioritization
- Pure module implementation (`lib/aras_filter.py`)

#### AI provider architecture

Four configurable provider slots: `conversation`, `conversation_fallback`, `data`, `data_fallback`.

### Changed

#### Automation structure

Monolithic automation files decomposed into `cycles.yaml`, `telegram.yaml`, `events.yaml`, `infrastructure.yaml`, `maintenance.yaml`.

#### Cycle architecture

- Sleep Consolidation: extracts memories, stores them in SQLite, performs tier maintenance
- Systems Consolidation: focused exclusively on insights generation

#### Codebase standardization

- Entire codebase translated to English
- All automation IDs prefixed with `permear_`
- `service:` replaced by `action:`
- `PRIMARY_RESIDENT` replaces hardcoded resident names

### Removed

- Legacy JSON memory architecture: `memory/soul.json`, `memory/users.json`, `memory/insights.json`, `memory/daily/*.json`
- Retired components: `apply_soul_v2`, `apply_users_v2`, quick learning legacy flow, stale rollback logic

---

## [7.9] — May 2026 (Internal Development)

Organic Memory maturation — six internal releases completed the Organic Memory architecture.

### Added

#### Tier maintenance

Memory now evolves automatically (`ephemeral → active`, `active → stable`, `active → ephemeral`, `stable → active`, `ephemeral → faded`) based on repetition and silence.

#### Autonomous memory reinforcement

Heartbeat emissions now feed the memory database automatically.

#### Pattern emergence

Patterns are no longer generated by LLMs. Repeated observations naturally become patterns when promoted from ephemeral to active.

#### Dynamic ARAS thresholds

Attention thresholds now scale with memory maturity and entity count.

#### Priority feedback loop

Consolidated memories automatically influence ARAS prioritization.

### Fixed

- Canonical key generation bug for event-triggered memories
- False memory merges caused by overly permissive FTS scoring
- Error events leaking into candidate selection

---

## [7.8] — May 2026 (Internal Development)

### Added

- First SQLite memory implementation: `memory/permear_memory.db`, `memory_items`, `memory_fts`, `lib/memory_db.py`
- Sleep Consolidation persistence — daily memory extraction now writes directly into SQLite

---

## [7.7] — May 2026 (Internal Development)

### Added

#### Provider specialization

Interactive and non-interactive workloads became separated (one provider for conversation, another for structured cycle execution).

#### Telegram fallback architecture

Automatic fallback when the primary conversational provider fails.

#### Circuit tracking

`agent_circuit.json`, fallback throttling, provider health tracking.

---

## [7.6] — April 2026 (Internal Development)

### Added

#### ARAS engagement learning

Telegram notifications gained feedback buttons (Confirm / Dismiss). User reactions now influence future prioritization.

#### Priority source tracking

Priority origins are now classified as `user`, `learned`, or `default`.

---

## [7.5] — April 2026 (Internal Development)

### Changed

#### Cycle stabilization

Current cycle model established: Heartbeat, Sleep Consolidation, Wake, Systems Consolidation. Scheduling remained hardcoded until v8.2.

---

## [7.4] — April 2026 (Internal Development)

### Added

- Telegram interaction framework: inline keyboards, callback routing
- Multi-step automation creation flow (`/nova_automacao` workflow)
- First conversational state-machine architecture

---

## [7.3.0] — 2026-05-19

Stability & Concurrency Safety — focused release dedicated to reliability, concurrency protection, and operational hardening.

### Added

- Memory safety: atomic file writes via `fcntl.flock` (`save_json()`, `locked_update()`)
- Configuration validation: `validate_ha_config()` with automatic rollback on invalid Home Assistant configuration
- Log monitoring: reverse-seek log tail with constant memory consumption
- Provider abstraction: configurable provider entities
- Circuit-breaker degradation detection — JSON repair events tracked as degradation signals

### Changed

- API efficiency: single bulk state fetch instead of multiple sequential calls
- All memory-modifying scripts migrated to atomic update operations

### Fixed

- Concurrent daily write race condition
- Reverse-seek line counting edge case

### Documentation

- New roadmap, updated migration guide, refined README

---

## [7.2.0] — 2026-05-17

Major Release — introduced the dual-LLM architecture that became the foundation of later releases.

### Added

#### Dual-path LLM architecture

Interactive: `conversation.process`. Non-interactive: `ai_task.generate_data`.

#### Automatic provider fallback

Three-stage execution model: health check → primary provider → secondary provider.

#### Active forgetting

Items not referenced for 30+ days are archived automatically.

#### Shared library

New modules: `memory.py`, `agent.py`, `logs.py`.

#### New components

Real-time error monitor, automation creation flow, Telegram management commands, health monitoring sensors.

### Changed

- Structured JSON-based weekly compilation
- Improved automation management commands
- Standardized daily memory keys

---

## [5.7] — 2025

First public release.

### Added

Foundational architecture: daily files plus perennial memory, 21:00 daily briefing, periodic pre-briefings, weekly compilation, entity discovery.
