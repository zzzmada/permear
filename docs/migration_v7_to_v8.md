# PERMEAR — Migration Guide: v7.x → v8

This guide describes the changes introduced in PERMEAR v8 for users migrating
from the last public v7.x release (approximately v7.3).

> See `CHANGELOG.md` for the version-by-version history. This guide focuses
> on the architectural changes relevant when migrating from v7.x.

---

## Breaking changes

### Memory system (major)

v7 stored daily data in JSON files under `memory/daily/*.json`. v8 replaces
this entirely with SQLite (`memory/permear_memory.db`).

**You cannot migrate v7 memory to v8 automatically.** The system starts fresh
with no prior memory, which is equivalent to PERMEAR's "born curious" state.
This is acceptable — the system re-learns patterns within 2–4 weeks.

**Files eliminated:**
- `memory/daily/*.json` (all of them)
- `memory/soul.json`
- `memory/users.json`
- `memory/insights.json`
- `memory/diretrizes.json`

**New files:**
- `memory/permear_memory.db` — the Organic Memory (auto-created on startup)
- `memory/guidelines.json` — replaces soul.json + users.json + insights.json

### scripts/append_daily.py removed

v7 used `append_daily.py` to write events. v8 uses three separate record
scripts: `record_event.py`, `record_interaction.py`, `record_flag.py`.

Update any automation or shell script that called `append_daily.py`.

### `nabu.yaml` modularized

The monolithic `automations/nabu.yaml` (2000+ lines) was split into:
- `automations/cycles.yaml` — Heartbeat, Sleep Consolidation, Systems Consolidation
- `automations/telegram.yaml` — Telegram state machine
- `automations/events.yaml` — event buffer + entity sync + ARAS priority alerts
- `automations/infrastructure.yaml` — startup, error monitor, log cleanup
- `automations/maintenance.yaml` — housekeeping
- `automations/base.yaml` — household automations (examples)

The original `nabu.yaml` is now an empty shell.

---

## Non-breaking changes (new capabilities)

### Organic Memory (v7.8–v7.9)

The SQLite memory now has tiered decay, automatic pattern emergence, and
a self-regulating loop from memory tiers to entity priority. No configuration
needed — it works from day one.

### ARAS dynamic threshold (v7.9-C)

The emit threshold is no longer fixed. It scales with the system's maturity
(ratio of consolidated entities to total exposed entities). A fresh install
has threshold = 2 (curious). A mature install reaches threshold = 4 (selective).

### Provider abstraction (v8-S-providers)

All AI providers are now configured in `permear.yaml` instead of being
hardcoded. Four slots: `conversation`, `data`, `conversation_fallback`,
`data_fallback`. See `docs/providers.md`.

### Conversation fallback — Reading 2 (v8-S-providers)

When the primary conversation provider fails 3×, PERMEAR transparently
switches to `conversation_fallback` with full tools — the user doesn't notice.
If that also fails, the user gets an honest error (Reading B: no degraded mode).

### Memory extraction during Sleep Consolidation (v7.8-B)

Sleep Consolidation now extracts memories from the day's events and writes
them to the DB — the system accumulates what it has observed over time.

### Loop tiers→priority (v7.9-F)

Entities the system has learned about (consolidated in memory) automatically
get a priority boost in ARAS evaluation. The more the system knows about an
entity, the more appropriately it weighs its events.

### Pattern emergence from repetition (v7.9-D)

When an observation is mentioned ≥ 3 times within 30 days and promotes from
ephemeral → active tier, its `kind` changes from `observation` to `pattern`.
Patterns are not LLM-detected — they emerge from pure accumulation.

---

## Configuration migration

### 1. Create `memory/guidelines.json`

```json
{
  "residents": [
    {
      "name": "YourName",
      "role": "primary",
      "entity": "person.your_person_entity"
    }
  ],
  "action_items": {
    "padroes": [],
    "pendencias": [],
    "sugestoes": []
  }
}
```

### 2. Create `permear.yaml`

See `docs/configuration.md` for the full format. Minimum required:

```yaml
providers:
  conversation: conversation.your_conversation_integration
  data: ai_task.your_ai_task_integration
  conversation_fallback: conversation.your_conversation_integration
  data_fallback: ai_task.your_ai_task_integration
```

### 3. Add secrets to `secrets.yaml`

In v8, AI providers are configured directly in `permear.yaml` (step 2) — they
are **not** secrets. The automations reference only two `!secret` keys:

```yaml
permear_person_entity: person.your_person_entity   # primary resident's person entity
telegram_chat_id: YOUR_CHAT_ID                      # Telegram chat to message
```

(Your Telegram bot token lives in the Home Assistant `telegram_bot`
integration config, not here.) See `secrets.yaml.example`.

### 4. Remove old files

Delete: `memory/soul.json`, `memory/users.json`, `memory/insights.json`,
`memory/diretrizes.json`, `memory/daily/` (entire directory).

### 5. Initialize the DB

The memory DB is auto-created on HA startup via the `permear_init_memory_db`
automation. If you want to initialize manually:

```bash
python3 /config/scripts/init_memory_db.py
```

---

## What you do NOT need to migrate

- Your entity states and HA config — PERMEAR reads them live.
- Your monitored_entities.json (if you had it) — keep it; format is compatible.
- Your automations in `base.yaml` — these are household-specific and don't
  interact with the memory system.
