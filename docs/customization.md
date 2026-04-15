# Customization Guide

## Directory Structure (permear_config.py)

All paths and constants are centralized in `/config/scripts/permear_config.py`. If your HA uses a non-standard directory structure (e.g., `automation.d/` instead of `automations/`), edit **only this file** — all scripts import from it.

Key settings:

| Variable | Default | Purpose |
|---|---|---|
| `MEMORY_DIR` | `/config/memory` | Where JSON memory files live |
| `DAILY_DIR` | `/config/memory/daily` | Daily rotation files |
| `AGENT_YAML` | `/config/automations/agent_automations.yaml` | Agent-created automations |
| `AUTOMATIONS_YAML` | `/config/automations/permear.yaml` | Main automations (for buffer event generation) |
| `TOKEN_PATH` | `/config/.permear_token` | Long-lived access token |
| `HA_URL` | `http://localhost:8123` | HA REST API base URL |
| `DAYS` | `['monday', ...]` | Daily file names — change for your language |
| `SELF_COMPONENTS` | `['telegram_bot', ...]` | Components whose errors are flagged as SELF_ERRORS |

### Non-English day names

Change the `DAYS` array in `permear_config.py`:

```python
# Portuguese
DAYS = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo']
```

All scripts read from this single source.

## Agent Language

To have the agent respond in another language, adjust the prompt strings in `build_briefing.py`, `build_prebriefing.py`, and `build_weekly_prompt.py`. You can add "Respond in [your language]." to each prompt.

## Localizing Rejection Keywords (Quick Learning)

**Critical for non-English users.** The `permear_quick_learning` automation matches rejection keywords in the user's Telegram message. These must match the language the user types in.

### Default (English)

```yaml
{{ 'irrelevant' in text or 'unnecessary' in text or
   'already know' in text or 'stop alerting' in text or
   "don't alert" in text or 'not important' in text or
   "don't care" in text or 'stop telling' in text or
   'i know' in text }}
```

### Portuguese (pt-BR)

```yaml
{{ 'irrelevante' in text or 'desnecessario' in text or
   'desnecessário' in text or 'já sei' in text or
   'ja sei' in text or 'não preciso' in text or
   'nao preciso' in text or 'para de avisar' in text or
   'não me avise' in text or 'nao me avise' in text }}
```

### Spanish

```yaml
{{ 'irrelevante' in text or 'innecesario' in text or
   'ya lo sé' in text or 'ya lo se' in text or
   'no me avises' in text or 'deja de avisar' in text or
   'no importa' in text }}
```

Include accented and non-accented versions for mobile keyboards. `| lower` is already applied.

## Entity Monitoring vs. Event Logging

Two separate systems in `monitored_entities.json`:

**`monitor: true`** — Pre-briefing reads current state every 30 min via REST API.

**`events: [...]`** — State changes logged as events in daily file via HA automation triggers.

In short: `monitor` = "what is the state now?", `events` = "what changed today?"

### Customizing the Event Buffer

Add `events` to any entity in `monitored_entities.json`:

```json
{
  "entity_id": "lock.front_door",
  "friendly_name": "Front Door",
  "domain": "lock",
  "monitor": false,
  "events": [
    {"trigger_type": "state", "to": "unlocked", "id": "door_unlocked"}
  ]
}
```

Then regenerate: Developer Tools → Services → `shell_command.generate_buffer_events`

| Field | Values | Trigger type |
|---|---|---|
| `to`, `from` | State string | `state` |
| `for` | Duration (e.g., `"00:05:00"`) | `state` |
| `above`, `below` | Numeric | `numeric_state` |
| `id` | Unique identifier | Both |

### Entity Discovery

Daily at 06:00 — syncs with entities exposed to the conversation agent. Preserves `monitor` and `events` fields. Proposals for new entities happen in the **weekly compilation** (7 days of context).

## SELF_ERRORS — Agent Self-Awareness

The `ha_log_monitor.py` classifies errors from PERMEAR-related components (telegram_bot, conversation, automation, shell_command) as `SELF_ERRORS`. These are errors the agent likely caused itself.

The pre-briefing prompt has a special instruction: when SELF_ERRORS are present, the agent must report what it thinks went wrong and what its last action was.

To customize which components are flagged, edit `SELF_COMPONENTS` in `permear_config.py`:

```python
SELF_COMPONENTS = [
    "telegram_bot", "telegram", "conversation",
    "google_generative_ai", "google_ai",
    "shell_command", "automation"
]
```

## Pre-briefing Frequency

Default: every 30 minutes.

| Frequency | Calls/day (08h-20h) |
|---|---|
| Every 15 min | 48 |
| Every 30 min | 24 |
| Every 60 min | 12 |

## Adding Voice Output

Add after any `telegram_bot.send_message`:

```yaml
- condition: state
  entity_id: binary_sensor.YOUR_OCCUPANCY_SENSOR
  state: "on"
- service: YOUR_TTS_SERVICE
  data:
    entity_id: YOUR_SPEAKER_ENTITY
    message: "{{ answer }}"
```

## Multi-User Setup

1. Add each user to `users.json`
2. Expand `chat_id` condition in `permear_telegram_handler`
3. Identify speaker in prompt via `chat_id` comparison

## Guidelines

Edit `guidelines.json` before locking with `chmod 444`. The `guidelines_monitoring` section now includes a rule about SELF_ERRORS — customize the expected behavior when the agent detects its own failures.
