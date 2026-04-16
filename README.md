# PERMEAR — Persistent Memory Architecture for Home Assistant AI Agents

A persistent memory and self-improvement system that transforms Home Assistant's conversation agent from a stateless chatbot into an intelligent assistant that **remembers, learns, monitors, and maintains** your smart home over time.

> Built and battle-tested on a Raspberry Pi 4 (2GB RAM) running HAOS. No external databases, no cloud storage, no paid services beyond what you already use.

## What This Is

Home Assistant's conversation agents (Gemini, OpenAI, etc.) have no memory between interactions. Every conversation starts from zero. PERMEAR fixes that with a file-based memory architecture that gives your agent a persistent soul, user profiles, learned insights, and the ability to create automations and monitor system health.

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

## Quick Start

### Option A: Installer (recommended)

```bash
git clone https://github.com/zzzmada/permear.git
cd permear
./install.sh
```

With HA packages support:
```bash
./install.sh /config automations scripts packages
```

The installer prompts for your token and secrets interactively.

### Option B: Manual

See detailed steps below.

## Requirements

- Home Assistant 2023.7+
- A conversation agent (Gemini 2.5 Flash recommended — free tier sufficient)
- Telegram bot in HA (polling mode)
- Python 3 + PyYAML (included in HAOS)
- Long-lived HA access token
- `max_tokens` set to 8192+ in your LLM integration

## Manual Installation

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

### 4. Configure secrets.yaml

Add to your `/config/secrets.yaml`:

```yaml
permear_chat_id: 123456789
permear_agent_id: conversation.google_ai_conversation
permear_person_entity: person.your_name
```

See [`secrets.yaml.example`](secrets.yaml.example) for details on finding these values.

### 5. Set max_tokens to 8192+

Google Generative AI: Settings → Configure → uncheck "Recommended model settings" → Maximum tokens: `8192`

### 6. Copy files

```
scripts/*.py         → /config/scripts/
memory/*.json        → /config/memory/
automations/*.yaml   → /config/automations/
```

### 7. Add configuration

**Option A (packages):** Copy `configuration_additions.yaml` to `/config/packages/permear.yaml`

**Option B (manual):** Copy contents of `configuration_additions.yaml` into your `configuration.yaml`

### 8. Lock guidelines

```bash
chmod 444 /config/memory/guidelines.json
```

### 9. Customize

- **`permear_config.py`** — Paths, `DAYS` for language, `SELF_COMPONENTS`. See [Customization Guide](docs/customization.md).
- **`soul.json`** — Agent personality.
- **`users.json`** — Household profiles.
- **`guidelines.json`** — Edit before locking.

### 10. Configure Telegram (polling mode)

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

### 12. Restart HA and run initial discovery

Developer Tools → Services → `shell_command.discover_entities`

## Critical Technical Notes

1. **Never use sentence triggers** (`platform: conversation`).
2. **Verify your agent_id** — often `conversation.google_ai_conversation`, NOT `google_generative_ai`. Check Developer Tools.
3. **`telegram_bot.send_message`**: `chat_id`, not `target`.
4. **HA triggers are static.** Define events in JSON, run `generate_buffer_events.py`.
5. **`max_tokens` must be 8192+** for weekly compilation.
6. **`ha_updates_check.py` only works inside HAOS container** (`SUPERVISOR_TOKEN`).
7. **Use `| truncate()` not `[:255]`** in HA templates.
8. **All response_variable stdout** must use `| default('') | trim | default('fallback')`.
9. **Gemini ignores format with long conversation history.** Inject instructions in message text.
10. **`discover_entities.py` filters by `should_expose`** in entity registry.
11. **SELF_ERRORS** flag errors from agent components. Customize in `permear_config.py`.
12. **Shell command JSON limited to 255 chars** via `input_text`. For larger payloads, use temporary files.
13. **Python not available in SSH addon terminal.** Run scripts via Developer Tools → Services.
14. **Clean phantom entities** after upgrades: Settings → Entities → filter "unavailable" → delete.

## Changelog

### v5.5 (2026-04-16)
- **`secrets.yaml` integration**: All user-specific values (`chat_id`, `agent_id`, `person_entity`) now use HA's native `!secret` mechanism. Zero placeholders to replace in automation files. Updates via `git pull` never overwrite user configuration.
- **`install.sh` improved**: Interactive installer with secrets.yaml setup (Step 3), HA packages support, `chattr` protection for `permear_config.py`, soul.json preservation. Original script by [@clyra](https://github.com/clyra).
- **`secrets.yaml.example`**: Reference file with all required secrets and instructions for finding values.
- **HA packages support**: `configuration_additions.yaml` works as a drop-in HA package — copy to `/config/packages/permear.yaml`.
- **Telegram event_data filter**: `chat_id` moved to `event_data` in triggers where possible, eliminating template conditions.

### v5.4 (2026-04-08)
- **SELF_ERRORS**: `ha_log_monitor.py` classifies errors from PERMEAR components separately. Pre-briefing instructs agent to report its own failures with context.
- **`SELF_COMPONENTS`** configurable in `permear_config.py`.

### v5.3 (2026-04-07)
- **Centralized configuration**: `permear_config.py` — all scripts import from it.

### v5.2 (2026-04-07)
- **`monitored_entities.json` as single source of truth**: `monitor` + `events` dual role.
- **`generate_buffer_events.py`**: Regenerates YAML between markers.
- **Empty speech fix**: `| default('') | trim` with fallback.

### v5.1 (2026-04-06)
- Agent ID fix, `should_expose` filter, `apply_users` any-field diff, truncation detection, prompt compaction.

### v5.0 (2026-04-06)
- Agent as system caretaker. HA monitoring, entity autodiscovery, native automations. Allowed actions removed.

### v3.2 (2026-03-31)
- Telegram context injection, quick-learn localization.

### v3.0 (2026-03-29)
- Initial release.

## License

MIT — Use it, fork it, improve it.

## Credits

- Architecture designed in collaboration with Claude (Anthropic)
- Installation script by [@clyra](https://github.com/clyra)
