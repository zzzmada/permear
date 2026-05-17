# Customizing PERMEAR for your household

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
  ]
}
```

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

```python
SELF_COMPONENTS = [
    "telegram_bot", "telegram", "conversation",
    "google_generative_ai", "google_ai",
    "openrouter", "deepseek",
    "shell_command", "automation"
]
```

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
