# Customization Guide

## Agent Language

All prompts are in English by default. To have the agent respond in another language, adjust the prompt strings in:
- `build_briefing.py` — daily briefing prompt
- `build_prebriefing.py` — proactive evaluation prompt  
- `build_weekly_prompt.py` — weekly compilation prompt

You can simply add "Respond in [your language]." to the end of each prompt. The JSON keys and file structure remain in English regardless of the agent's response language.

## Localizing Rejection Keywords (Quick Learning)

**This is critical for non-English users.** The `permear_quick_learning` automation detects when the user rejects a pre-briefing alert by matching keywords in the Telegram message. These keywords are hardcoded in the automation's condition template and **must match the language the user actually types in**.

If your users communicate in a language other than English, you **must** update the keyword list or the quick-learning system will never trigger.

### Default keywords (English)

```yaml
{{ 'irrelevant' in text or
   'unnecessary' in text or
   'already know' in text or
   'stop alerting' in text or
   'dont alert' in text or
   "don't alert" in text or
   'not important' in text or
   'dont care' in text or
   "don't care" in text or
   'stop telling' in text or
   'i know' in text }}
```

### Example: Portuguese (pt-BR)

Replace or extend the keyword list in `permear_quick_learning`:

```yaml
{{ 'irrelevante' in text or
   'desnecessario' in text or
   'desnecessário' in text or
   'já sei' in text or
   'ja sei' in text or
   'não preciso' in text or
   'nao preciso' in text or
   'para de avisar' in text or
   'não me avise' in text or
   'nao me avise' in text or
   'não importa' in text or
   'nao importa' in text or
   'sem importancia' in text or
   'sem importância' in text }}
```

### Example: Spanish

```yaml
{{ 'irrelevante' in text or
   'innecesario' in text or
   'ya lo sé' in text or
   'ya lo se' in text or
   'no me avises' in text or
   'deja de avisar' in text or
   'no importa' in text or
   'no me interesa' in text }}
```

### Tips for keyword selection

- Include both accented and non-accented versions (e.g., `desnecessário` and `desnecessario`) since users may type without accents on mobile keyboards.
- Use `| lower` in the template (already applied) so capitalization does not matter.
- Test by sending each keyword phrase to your bot and verifying the automation triggers in the HA automation trace.
- You can support multiple languages simultaneously by combining all keywords in a single condition.

## Guidelines

The `guidelines.json` file is your constitution. Examples of customizations:

### Stricter pattern recording
```json
"guidelines_insights": {
  "rules": [
    "Only record a pattern if observed on at least 5 distinct days.",
    "Maximum 15 patterns."
  ]
}
```

### Allowing personality evolution
```json
"guidelines_soul": {
  "rules": [
    "The agent may adjust its tone based on observed user preferences.",
    "The agent may add up to 2 new behavioral rules per week."
  ]
}
```

### Restricting user data
```json
"guidelines_users": {
  "rules": [
    "Never record location patterns beyond home/away.",
    "Never record sleep schedule details."
  ]
}
```

## Pre-briefing Frequency

Default: every 30 minutes. To change:

```yaml
# Every hour
- platform: time_pattern
  hours: "/1"
  minutes: "0"

# Every 15 minutes (more aggressive, uses more API calls)
- platform: time_pattern
  minutes: "/15"
```

**API budget impact:**
| Frequency | Calls/day (08h-20h) |
|---|---|
| Every 15 min | 48 |
| Every 30 min | 24 |
| Every 60 min | 12 |

## Adding Voice Output

The architecture is Telegram-first, but you can add voice output alongside any Telegram notification:

```yaml
# Add after any telegram_bot.send_message action:
- condition: state
  entity_id: binary_sensor.YOUR_OCCUPANCY_SENSOR
  state: "on"
- service: YOUR_TTS_SERVICE
  data:
    entity_id: YOUR_SPEAKER_ENTITY
    message: "{{ answer }}"
```

## Multi-User Setup

To support multiple Telegram users:

1. Add each user to `users.json` with their own profile and key
2. In `permear_telegram_handler`, expand the chat_id condition
3. Adjust the LLM prompt to identify who is speaking:

```yaml
- service: conversation.process
  data:
    text: >
      {% if trigger.event.data.chat_id == USER_1_CHAT_ID %}
      [Context: Speaking with User 1. Direct and technical.]
      {% elif trigger.event.data.chat_id == USER_2_CHAT_ID %}
      [Context: Speaking with User 2. Friendly and patient.]
      {% endif %}
      {{ trigger.event.data.text }}
```

## Extending the Event Buffer

Add triggers to `permear_buffer_events` for any HA entity you want tracked:

```yaml
# Door lock
- platform: state
  entity_id: lock.front_door
  to: "unlocked"
  id: "door_unlocked"

# Energy spike
- platform: numeric_state
  entity_id: sensor.energy_consumption
  above: 3000
  id: "high_energy"

# Motion in unexpected hours
- platform: state
  entity_id: binary_sensor.hallway_motion
  to: "on"
  id: "hallway_motion"
  conditions:
    - condition: time
      after: "00:00:00"
      before: "05:00:00"
```

The more relevant events you capture, the richer the daily briefing and the better the weekly compilation's pattern detection.
