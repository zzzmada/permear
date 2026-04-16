# Customization Guide

## Installation Methods

### Method A: install.sh (recommended)

```bash
# Default paths
./install.sh

# With HA packages support
./install.sh /config automations scripts packages

# Custom directory names
./install.sh /config automation.d script.d packages
```

The installer creates directories, prompts for token and secrets, copies files, and locks guidelines.

### Method B: Manual

Follow the step-by-step in README.md.

## secrets.yaml

PERMEAR uses HA's native `!secret` mechanism. Add to your `/config/secrets.yaml`:

```yaml
permear_chat_id: 123456789
permear_agent_id: conversation.google_ai_conversation
permear_person_entity: person.your_name
```

**Finding your values:**
- `chat_id`: Send a message to [@userinfobot](https://t.me/userinfobot) on Telegram
- `agent_id`: Developer Tools → Services → `conversation.process` → agent dropdown shows the entity_id
- `person_entity`: Developer Tools → States → search "person."

**Do NOT quote `chat_id`** — it must be an integer, not a string.

This eliminates all `YOUR_*` placeholders from automations. Updates via `git pull` won't overwrite your secrets.

## HA Packages

If you prefer not to edit `configuration.yaml`, use [HA packages](https://www.home-assistant.io/docs/configuration/packages/):

1. Add to `configuration.yaml` (one-time):
```yaml
homeassistant:
  packages: !include_dir_named packages
```

2. Copy `configuration_additions.yaml` to `/config/packages/permear.yaml`

All shell_commands, input_texts, and sensors load automatically.

## Directory Structure (permear_config.py)

All paths and constants are centralized in `permear_config.py`. Edit **only this file** if your HA uses different directories.

| Variable | Default | Purpose |
|---|---|---|
| `MEMORY_DIR` | `/config/memory` | JSON memory files |
| `DAILY_DIR` | `/config/memory/daily` | Daily rotation files |
| `AGENT_YAML` | `/config/automations/agent_automations.yaml` | Agent-created automations |
| `AUTOMATIONS_YAML` | `/config/automations/permear.yaml` | Main automations (buffer markers) |
| `TOKEN_PATH` | `/config/.permear_token` | Long-lived access token |
| `DAYS` | `['monday', ...]` | Daily file names |
| `SELF_COMPONENTS` | `['telegram_bot', ...]` | Components flagged as SELF_ERRORS |

### Non-English day names

```python
# Portuguese
DAYS = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo']

# Spanish
DAYS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
```

## Localizing Rejection Keywords (Quick Learning)

**Critical for non-English users.** The quick learning automation matches rejection keywords. These must match the language the user types in.

### Default (English)

```yaml
{{ 'irrelevant' in text or 'unnecessary' in text or
   'already know' in text or 'stop alerting' in text or
   "don't alert" in text or 'not important' in text or
   "don't care" in text or 'i know' in text }}
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
   'no me avises' in text or 'no importa' in text }}
```

Include accented and non-accented versions. `| lower` is already applied.

## Entity Monitoring vs. Event Logging

`monitored_entities.json` has two roles:

**`monitor: true`** — Pre-briefing reads current state via REST API every 30 min.

**`events: [...]`** — State changes logged in daily file via HA automation triggers.

`monitor` = "what is the state now?" / `events` = "what changed today?"

### Adding events

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

Then regenerate: `Developer Tools → Services → shell_command.generate_buffer_events`

| Field | Values | Trigger type |
|---|---|---|
| `to`, `from` | State string | `state` |
| `for` | Duration (e.g., `"00:05:00"`) | `state` |
| `above`, `below` | Numeric | `numeric_state` |
| `id` | Unique identifier | Both |

### Discovery frequency

Daily at 06:00 — syncs with exposed entities, preserves `monitor` and `events` fields. Proposals for new entities happen in the **weekly compilation** (7 days of context).

## SELF_ERRORS

The log monitor classifies errors from PERMEAR components as `SELF_ERRORS`. The pre-briefing instructs the agent to report what went wrong and suggest a fix.

Customize in `permear_config.py`:

```python
SELF_COMPONENTS = [
    "telegram_bot", "telegram", "conversation",
    "google_generative_ai", "google_ai",
    "shell_command", "automation"
]
```

## Pre-briefing Frequency

| Frequency | Calls/day (08h-20h) |
|---|---|
| Every 15 min | 48 |
| Every 30 min (default) | 24 |
| Every 60 min | 12 |

## Multi-User Setup

1. Add users to `users.json`
2. Each user needs their own Telegram `chat_id` in `secrets.yaml`
3. Expand event_data filter or add separate automations per user
