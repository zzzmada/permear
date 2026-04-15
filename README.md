# PERMEAR — Persistent Memory Architecture for Home Assistant AI Agents

A persistent memory and self-improvement system that transforms Home Assistant's conversation agent from a stateless chatbot into an intelligent assistant that **remembers, learns, monitors, and maintains** your smart home over time.

> Built and battle-tested on a Raspberry Pi 4 (2GB RAM) running HAOS. No external databases, no cloud storage, no paid services beyond what you already use.

## What This Is

Home Assistant's conversation agents (Gemini, OpenAI, etc.) have no memory between interactions. Every conversation starts from zero. PERMEAR fixes that with a file-based memory architecture that gives your agent a persistent soul, user profiles, learned insights, and the ability to create automations and monitor system health — all through local JSON files, Python scripts, and HA automations.

**The agent evolves from household assistant to system caretaker** — it monitors HA health, detects errors (including its own), checks for updates, autodiscovers entities, and can create native HA automations with user approval.

## Architecture

```
MEMORY (persistent JSON files)
├── guidelines.json          ← IMMUTABLE constitution (chmod 444)
├── soul.json                ← Agent personality (edited weekly by agent)
├── users.json               ← Household profiles (edited weekly + quick-learn)
├── insights.json            ← Detected patterns (edited weekly)
├── monitored_entities.json  ← Single source of truth for entities
│                              monitor:true → pre-briefing reads state
│                              events:[] → buffer logs state changes
└── daily/
    └── monday..sunday.json  ← 7-day rotating event logs

SCRIPTS (all import from permear_config.py)
├── permear_config.py           ← Centralized paths and constants
├── append_daily.py             ← Log events/interactions/memories
├── build_briefing.py           ← Daily briefing prompt (21h)
├── build_prebriefing.py        ← Proactive evaluation (30min) + SELF_ERRORS
├── build_weekly_prompt.py      ← Weekly compilation prompt (Sunday)
├── update_daily_memory.py      ← Save extracted memories
├── weekly_compile.py           ← Apply LLM edits to perennials
├── apply_quick_learning.py     ← Instant restriction from rejections
├── discover_entities.py        ← Autodiscover exposed entities
├── generate_buffer_events.py   ← Regenerate triggers from JSON
├── ha_log_monitor.py           ← Parse logs: SELF_ERRORS vs ERRORS
├── ha_updates_check.py         ← Check HA/addon updates
├── manage_agent_automations.py ← Create/remove HA automations
├── sensor_current_day.py       ← HA sensor: current day memory
└── sensor_perennial.py         ← HA sensor: perennial files

CYCLES
├── Every 30 min (08-20h) ── Pre-briefing: health + house evaluation
├── Daily 21h ────────────── Briefing: day summary + updates + memories
├── Daily 06:00 ──────────── Entity autodiscovery
├── Sunday 00:05 ─────────── Weekly compile: self-improvement
└── On demand ────────────── Telegram chat + voice commands
```

## Key Concepts

### Self-Calibrating Proactivity

The pre-briefing starts noisy and becomes precise over time. Reply "that's irrelevant" and the agent learns immediately.

### 7-Day Rotation

Daily files named by weekday. Next Monday overwrites this Monday. No cleanup needed.

### Monitored Entities — Single Source of Truth

`monitored_entities.json` serves two roles: `monitor: true` for pre-briefing state reading, `events` for buffer trigger generation. Edit one file, run `generate_buffer_events.py`, both systems update.

### SELF_ERRORS — Agent Self-Awareness

The log monitor classifies errors from PERMEAR components (telegram_bot, conversation, automation, shell_command) as `SELF_ERRORS`. When detected, the pre-briefing prompt instructs the agent to report what went wrong, what its last action was, and suggest a fix. External HA errors remain as regular `ERRORS`.

### Agent-Created Automations

The agent proposes automations via Telegram, you approve, they activate via `automation.reload`.

### Guidelines: The Immutable Constitution

`guidelines.json` (chmod 444) defines the agent's operating boundaries. It cannot change them.

## Requirements

- Home Assistant 2023.7+
- A conversation agent (Gemini 2.5 Flash recommended — free tier sufficient)
- Telegram bot in HA (polling mode)
- Python 3 + PyYAML (included in HAOS)
- Long-lived HA access token
- `max_tokens` set to 8192+ in your LLM integration

## Installation

### 1. Create directories

```bash
mkdir -p /config/memory/daily /config/scripts /config/logs
touch /config/automations/agent_automations.yaml
```

### 2. Verify automation include mode

```yaml
# configuration.yaml — must be directory-based:
automation: !include_dir_merge_list automations/
```

### 3. Create access token

HA sidebar → username → Long-Lived Access Tokens → Create → "PERMEAR"

```bash
echo "YOUR_TOKEN" > /config/.permear_token
chmod 600 /config/.permear_token
```

### 4. Set max_tokens to 8192+

Google Generative AI: Settings → Configure → uncheck "Recommended model settings" → Maximum tokens: `8192`

### 5. Copy files

```
scripts/*.py         → /config/scripts/
memory/*.json        → /config/memory/
automations/*.yaml   → /config/automations/
```

### 6. Lock guidelines

```bash
chmod 444 /config/memory/guidelines.json
```

### 7. Customize

- **`permear_config.py`** — Paths, `DAYS` for language, `SELF_COMPONENTS`. See [Customization Guide](docs/customization.md).
- **`soul.json`** — Agent personality.
- **`users.json`** — Household profiles.
- **`guidelines.json`** — Edit before locking.

### 8. Add to configuration.yaml

Copy contents of [`configuration_additions.yaml`](configuration_additions.yaml).

### 9. Configure Telegram (polling mode)

### 10. Add automations + replace placeholders

`YOUR_CHAT_ID`, `YOUR_AGENT_ID` (verify in Developer Tools → Services → conversation.process), `person.YOUR_PERSON`.

### 11. Update LLM system prompt

```
SYSTEM MONITORING: You monitor HA health. Critical errors: notify immediately.
SELF_ERRORS are from your own actions — always report what you think went wrong.
Updates: mention in daily briefing only. New devices: ask user to name them.

AUTOMATIONS: Create with manage_agent_auto_create, remove with manage_agent_auto_remove,
list with manage_agent_auto_list. ALWAYS ask confirmation before creating.

ENTITY MONITORING: "monitor [entity]" → add_monitored_entity.
"stop monitoring [entity]" → remove_monitored_entity.
```

### 12. Run initial discovery + restart HA

## Critical Technical Notes

1. **Never use sentence triggers** (`platform: conversation`).
2. **Verify your agent_id** — often `conversation.google_ai_conversation`, NOT `google_generative_ai`.
3. **`telegram_bot.send_message`**: `chat_id`, not `target`.
4. **HA triggers are static.** Define events in JSON, run `generate_buffer_events.py`.
5. **`max_tokens` must be 8192+** for weekly compilation.
6. **`ha_updates_check.py` only works inside HAOS container** (`SUPERVISOR_TOKEN`).
7. **Use `| truncate()` not `[:255]`** in HA templates.
8. **All response_variable stdout must use** `| default('') | trim | default('fallback')` to prevent empty message errors.
9. **Gemini ignores format with long conversation history.** Reset `conversation_id` or inject in message.
10. **`discover_entities.py` filters by `should_expose`** in entity registry.
11. **SELF_ERRORS** flag errors from components the agent uses directly. Customize in `permear_config.py`.

## Changelog

### v5.4 (2026-04-08)
- **SELF_ERRORS awareness**: `ha_log_monitor.py` now classifies errors from PERMEAR components (telegram_bot, conversation, automation, shell_command) as `SELF_ERRORS` — separate from external HA `ERRORS`. The pre-briefing prompt instructs the agent to report what it thinks went wrong, what its last action was, and suggest a fix.
- **`SELF_COMPONENTS` in `permear_config.py`**: Configurable list of components whose errors are flagged as self-caused.
- **`guidelines.json` updated**: Monitoring guidelines now include SELF_ERRORS handling rule.

### v5.3 (2026-04-07)
- **Centralized configuration**: `permear_config.py` with all paths and constants. All scripts import from it. Users with non-standard directories edit one file.

### v5.2 (2026-04-07)
- **`monitored_entities.json` as single source of truth**: `monitor` for pre-briefing, `events` for buffer triggers.
- **`generate_buffer_events.py`**: Regenerates YAML between markers.
- **`discover_entities.py`** preserves `monitor` and `events` fields.
- **Empty speech fix**: `| default('') | trim` with fallback message.
- **`generate_buffer_events` shell_command** added.

### v5.1 (2026-04-06)
- Agent ID fix, `should_expose` filter, `apply_users` any-field diff, truncation detection, `| truncate()` fix, prompt compaction.

### v5.0 (2026-04-06)
- Agent as system caretaker. HA health monitoring, update checking, entity autodiscovery, native automation creation. Allowed actions removed.

### v3.2 (2026-03-31)
- Telegram context injection, briefing memory timing, quick-learn localization.

### v3.0 (2026-03-29)
- Initial release.

## License

MIT — Use it, fork it, improve it.

## Credits

Architecture designed in collaboration with Claude (Anthropic).
