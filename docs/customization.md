# Customizing PERMEAR for your household

<<<<<<< HEAD
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
=======
After installation, you'll want to tune PERMEAR to your home. This guide walks through the customization points.

---

## 1. soul.json — agent personality

`/config/memory/soul.json` defines how the agent behaves.

```json
{
  "name": "Aurora",
  "mission": "Take care of the family's apartment intelligently and proactively.",
  "tone": "warm, direct, never alarmist",
  "values": [
    "family privacy",
    "data efficiency",
    "respect for silence"
  ],
  "behavior_rules": [
    "Pre-briefings should be silent unless something is unusual",
    "Daily briefings at 23:30 — max 120 words",
    "Never speculate — only report observed facts",
    "Suggest automations only after 3+ days of evidence"
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
  ]
}
```

<<<<<<< HEAD
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
=======
**Tips:**
- `name`: shown in briefings. Pick something you like saying.
- `tone`: the LLM follows this hint. Try "formal" vs "casual" and see the difference.
- `behavior_rules`: max 15. Weekly compilation adds/removes 1/week based on observed interactions.

---

## 2. users.json — household profiles

One key per resident.

```json
{
  "alice": {
    "role": "primary resident, software engineer",
    "response_style": "technical, no fluff",
    "primary_channel": "telegram",
    "preferred_temperature": 22,
    "interests": ["coding", "running", "podcasts"],
    "restrictions": [],
    "observed_patterns": []
  },
  "bob": {
    "role": "partner, teacher",
    "response_style": "warm, casual",
    "primary_channel": "voice",
    "preferred_temperature": 24,
    "interests": ["cooking", "literature"],
    "restrictions": [],
    "observed_patterns": []
  }
}
```

**Tips:**
- `role`: how the agent thinks of this person. Short descriptive phrases work best.
- `restrictions`: the agent will avoid alerting about these. Auto-populated via quick learning (you saying "I know" / "irrelevant" in chat).
- `observed_patterns`: auto-populated by weekly compilation. Don't edit manually unless cleaning up.

The **first key** in users.json is treated as the primary user for pre-briefings.

---

## 3. monitored_entities.json — what to watch

Auto-populated by `discover_entities.py`. Format:

```json
{
  "updated_at": "2026-05-17T10:30:00",
  "source": "entity_registry",
  "count": 23,
  "entities": [
    {
      "entity_id": "light.kitchen",
      "friendly_name": "Kitchen Light",
      "domain": "light",
      "monitor": true,
      "events": [
        {
          "trigger_type": "state",
          "to": "on",
          "id": "kitchen_light_on"
        }
      ]
    }
  ]
}
```

**Field meanings:**
- `monitor: true` — included in pre-briefing house state
- `events` — state changes to log to daily file

### Adding events to an entity

```json
"events": [
  {"trigger_type": "state", "to": "on", "id": "fridge_door_open"},
  {"trigger_type": "state", "to": "off", "id": "fridge_door_closed"}
]
```

After editing, regenerate the buffer triggers:

```bash
python3 /config/scripts/generate_buffer_events.py
```

Then reload automations in HA. Now any state change on those entities will be appended to today's daily file.

### Manually adding/removing entities

```bash
# Add a custom entity to monitoring
python3 /config/scripts/discover_entities.py --add sensor.outdoor_temperature "Outdoor Temperature"

# Remove an entity from monitoring (won't appear in pre-briefing)
python3 /config/scripts/discover_entities.py --remove sensor.useless_thing
```

---

## 4. Pre-briefing prompt template

Edit `/config/scripts/build_prebriefing.py` if you want to change:
- What information is presented to the LLM each hour
- How decisions are framed (alert vs silence)
- Tone of the prompt itself

The default prompt is in English. If you want to localize the agent's interactions to your native language, edit:
- `build_prebriefing.py` — translate `prompt = f"""..."""`
- `build_briefing.py` — translate `prompt = f"""..."""`
- `briefing_simple.py` — translate fallback messages
- Daily files don't need translation (data only)

---

## 5. Cycle timing

Edit `/config/automations/permear.yaml`:

| Cycle | Default time | Where to change |
|---|---|---|
| Pre-briefing | Hourly at :30 | `permear_prebriefing` → `trigger.minutes` |
| Daily briefing | 23:30 | `permear_daily_briefing` → `trigger.at` |
| Entity discovery | 06:00 | `permear_entity_discovery` → `trigger.at` |
| Weekly compilation | Sunday 04:00 | `permear_weekly_compilation` → `trigger.at` + condition weekday |
| Daily reset | 00:00 | `permear_daily_reset` → `trigger.at` |

Pre-briefing has a built-in random delay of 60-300 seconds to avoid exact-minute spikes.

---

## 6. AI provider customization

`/config/scripts/permear_config.py`:

```python
AI_TASK_PRIMARY = "ai_task.openrouter_deepseek_v3"
AI_TASK_SECONDARY = "ai_task.google_ai_task"
```

Use any HA AI Task entity. To use Claude Haiku for non-interactive cycles:

1. Install Anthropic integration
2. Add AI Task sub-entry with Haiku model
3. Set `AI_TASK_PRIMARY = "ai_task.claude_haiku"`

To use a local Ollama model:

1. Install Ollama integration
2. Add AI Task sub-entry
3. Set `AI_TASK_PRIMARY = "ai_task.ollama_local"`

(Ollama works if your hardware can host a 7B+ model reliably.)

---

## 7. Day names for non-English

If you want the daily files in Portuguese, Spanish, or another language:

```python
# /config/scripts/permear_config.py
DAYS = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo']
DAYS_DISPLAY = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
```

And rename your existing daily files accordingly. The data inside (JSON keys) should stay in English for compatibility with prompts and scripts.

---

## 8. Noisy components — what to silence in error monitor

`/config/scripts/permear_config.py`:

```python
NOISY_COMPONENTS = [
    "recorder", "statistics", "logbook", "history",
    "speedtestdotnet"
]
```

Components in this list are silenced in the real-time error monitor. Add yours if certain integrations spam your logs (`ERROR (MainThread) [homeassistant.components.X]`). Use the lowercase short name.

---

## 9. Self components — what counts as PERMEAR errors

`/config/scripts/permear_config.py`:
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)

```python
SELF_COMPONENTS = [
    "telegram_bot", "telegram", "conversation",
    "google_generative_ai", "google_ai",
<<<<<<< HEAD
=======
    "openrouter", "deepseek",
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
    "shell_command", "automation"
]
```

<<<<<<< HEAD
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
=======
When errors from these components arrive, they're tagged `SELF_ERROR` (vs generic `HA_ERROR`) so the pre-briefing prompt can give them priority. Add provider integrations if you use them.

---

## 10. After customizing

Always reload after changes:

```yaml
# Developer Tools → YAML
- Reload Command Line Sensors
- Reload Automations
- Reload Shell Commands
```

Or just restart HA if many things changed.
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
