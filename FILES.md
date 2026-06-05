# FILES.md — PERMEAR publication inventory

> Files that will be published to GitHub.
> Anything absent from this list is either in `.gitignore` (private data,
> household config, secrets) or is a runtime artifact (logs, cache, db).

---

## Root

```
README.md                     ← project front page (rendered by GitHub + HACS)
LICENSE                       ← MIT
.gitignore
hacs.json
FILES.md                      ← this inventory
permear.yaml                  ← user config: providers, aras sensitivity, cycle schedules
configuration_example.yaml    ← template showing what to add to your configuration.yaml
secrets.yaml.example          ← the two !secret keys PERMEAR references
CHANGELOG.md
ROADMAP.md
```

---

## automations/

```
cycles.yaml         ← Heartbeat, Sleep Consolidation, Systems Consolidation
events.yaml         ← event buffer, entity sync, ARAS priority alerts
infrastructure.yaml ← startup DB init, real-time error monitor, log cleanup
maintenance.yaml    ← PERMEAR core housekeeping (event_buffer + archived errors)
telegram.yaml       ← conversation agent state machine (6 automations)
```

---

## packages/

```
permear.yaml       ← shell_commands, sensors, input entities, schedule sync
```

---

## docs/

```
configuration.md
providers.md
agent_prompt_template.md
migration_v7_to_v8.md
```

---

## scripts/

```
permear_config.py             ← loads permear.yaml, exposes all constants

# Cycles
build_heartbeat.py            ← Heartbeat: build_candidates → ARAS → emit/gray/suppress
build_sleep_prompt.py         ← Sleep Consolidation: builds the nightly briefing prompt
build_systems_prompt.py       ← Systems Consolidation: weekly context from Organic Memory DB
apply_sleep_memories.py       ← writes extracted memories to DB
sleep_simple.py               ← Sleep Consolidation fallback (no LLM)
systems_compile.py            ← Systems Consolidation result processor

# Organic Memory
init_memory_db.py             ← creates/migrates permear_memory.db (idempotent)
memory_record_emit.py         ← Heartbeat: writes emitted events to DB
run_memory_maintenance.py     ← tier promotion/demotion/fade (runs after Sleep)
record_event.py               ← writes to event_buffer
record_interaction.py         ← writes to memory_items (Telegram/voice interactions)
telegram_dedup.py             ← message_id dedup guard for the Telegram handler
record_flag.py                ← writes to system_flags
mark_reaction.py              ← marks user reply in DB (engagement tracking)
forget_old_items.py           ← archives stale action_items before weekly compile

# ARAS Filter
aras_evaluate_one.py          ← evaluates a single priority=2 entity alert
aras_log_stats.py             ← logs daily ARAS stats (→ sensor.permear_attention)
generate_buffer_events.py     ← regenerates trigger block in events.yaml

# Wake cycle
discover_entities.py          ← entity discovery via HA registry + REST API
set_entity_priority.py        ← user-set entity priority (from Telegram card)
get_monitored_entities_text.py← formats entity list for ai_task prompts

# Agent-managed automations
manage_agent_automations.py   ← CRUD of agent-created automations
build_automation_spec.py      ← converts raw fields to canonical HA automation spec
write_pending_spec.py         ← writes pending_auto_spec.json

# Sensors
sensor_permear_config.py      ← exposes permear.yaml settings as sensor attributes
sensor_permear_health.py      ← provider health + fallback tracking
sensor_permear_attention.py   ← daily ARAS stats
sensor_daily_memory.py        ← today's event buffer and interactions
sensor_household_data.py      ← guidelines.json (residents + action_items)

# Infrastructure
ha_log_monitor.py             ← real-time HA error monitor (NOISY filter)
ha_update_manager.py          ← HA update list, execute, skip
ha_updates_check.py           ← (HAOS container only)
process_log_event.py          ← processes log events for error monitor
manage_archived.py            ← archives silenced errors
log_fallback.py               ← logs provider fallback events
debug_log_weekly.py           ← debug helper for weekly compile
```

---

## scripts/lib/

```
__init__.py
aras_filter.py      ← pure ARAS salience filter (no HA dependency, testable)
memory_db.py        ← Organic Memory DAL (SQLite)
memory_schema.sql   ← SQLite schema (memory_items, memory_fts, event_buffer, system_flags)
memory.py           ← legacy helpers (load_json, save_json, locked_update)
logs.py             ← log helpers + NOISY_COMPONENTS filter
agent.py            ← HA REST API helpers
```
