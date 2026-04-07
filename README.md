# PERMEAR — Persistent Memory Architecture for Home Assistant AI Agents

A persistent memory and self-improvement system that transforms Home Assistant's conversation agent from a stateless chatbot into an intelligent assistant that **remembers, learns, monitors, and maintains** your smart home over time.

> Built and battle-tested on a Raspberry Pi 4 (2GB RAM) running HAOS. No external databases, no cloud storage, no paid services beyond what you already use.

## What This Is

Home Assistant's conversation agents (Gemini, OpenAI, etc.) have no memory between interactions. Every conversation starts from zero. PERMEAR fixes that with a file-based memory architecture that gives your agent a persistent soul, user profiles, learned insights, and the ability to create automations and monitor system health — all through local JSON files, Python scripts, and HA automations.

**In v5.0, the agent evolves from household assistant to system caretaker** — it monitors HA health, detects errors, checks for updates, autodiscovers entities, and can create native HA automations with user approval.

## Architecture

```
MEMORY (persistent JSON files)
├── guidelines.json          ← IMMUTABLE constitution (chmod 444)
├── soul.json                ← Agent personality (edited weekly by agent)
├── users.json               ← Household profiles (edited weekly + quick-learn)
├── insights.json            ← Detected patterns (edited weekly)
├── monitored_entities.json  ← Autodiscovered entities (daily 06:00)
└── daily/
    └── monday..sunday.json  ← 7-day rotating event logs

CYCLES
├── Every 30 min (08-20h) ── Pre-briefing: health check + house evaluation
├── Daily 21h ────────────── Briefing: day summary + updates + memories
├── Daily 06:00 ──────────── Entity autodiscovery
├── Sunday 00:05 ─────────── Weekly compile: pattern detection + self-improvement
└── On demand ────────────── Telegram chat + voice commands

CARETAKER (v5.0)
├── ha_log_monitor.py        ← Parse HA logs for errors/warnings
├── ha_updates_check.py      ← Check HA/addon updates via Supervisor API
├── discover_entities.py     ← Autodiscover exposed entities
├── generate_buffer_events.py ← Regenerate event triggers from JSON
└── manage_agent_automations.py ← Create/remove HA automations
```

## Key Concepts

### Self-Calibrating Proactivity

The pre-briefing system starts noisy and becomes precise over time. When you tell the agent "that's irrelevant," it immediately learns the restriction. No manual tuning — your natural responses are the training data.

### 7-Day Rotation

Daily files are named by weekday (`monday.json` through `sunday.json`). Next Monday overwrites this Monday automatically. No cleanup jobs, no growing storage. The weekly compilation extracts patterns before files get overwritten.

### Agent-Created Automations

The agent can create native HA automations in a dedicated file (`agent_automations.yaml`). It proposes via Telegram, the user approves, and the automation activates immediately via `automation.reload` — no HA restart needed. The agent never touches other automation files.

### Guidelines: The Immutable Constitution

`guidelines.json` (chmod 444) defines the rules for how the agent edits its own memory. The agent operates within these boundaries but cannot change them.

## Requirements

- Home Assistant 2023.7+ (for `shell_command` with `response_variable`)
- A conversation agent configured in HA (Gemini 2.5 Flash recommended — free tier sufficient)
- Telegram bot in HA (polling mode)
- Python 3 + PyYAML (included in HAOS)
- A long-lived HA access token (for REST API calls)
- `max_tokens` set to 8192+ in your LLM integration

### LLM Free Tier Budget

| Use | Calls/day |
|---|---|
| Pre-briefings (08h-20h, every 30min) | 24 |
| Daily briefing + memory extraction | 2 |
| Voice/Telegram interactions | 15-30 |
| Weekly compilation (Sunday) | ~0.14 |
| **Total** | **~42-57** |

Gemini free tier limit: 1,500/day. Usage: ~4%.

## Installation

### 1. Create directory structure

```bash
mkdir -p /config/memory/daily
mkdir -p /config/scripts
mkdir -p /config/logs
touch /config/automations/agent_automations.yaml
```

### 2. Verify automation include mode

In `configuration.yaml`, ensure you have directory-based includes:

```yaml
automation: !include_dir_merge_list automations/
```

If you have `automation: !include automations.yaml`, change it. The agent automation file won't load otherwise.

### 3. Create access token

Required for entity state queries, automation reload, and action execution.

1. HA sidebar → click your username (bottom left)
2. Scroll to **Long-Lived Access Tokens** → **Create Token**
3. Name it "PERMEAR", copy the token
4. Save it:

```bash
echo "YOUR_TOKEN_HERE" > /config/.permear_token
chmod 600 /config/.permear_token
```

### 4. Set max_tokens

The weekly compilation sends all 7 daily files to the LLM and expects structured JSON back. The default `max_tokens` is too low and will cause truncated responses.

**Google Generative AI:** Settings → Integrations → Google Generative AI → Configure → uncheck "Recommended model settings" → set Maximum tokens to `8192`.

### 5. Copy files

Copy all files from this repository to your HA instance:

```
memory/*.json     → /config/memory/
scripts/*.py      → /config/scripts/
```

### 6. Lock guidelines

```bash
chmod 444 /config/memory/guidelines.json
```

### 7. Customize memory files

- **`soul.json`** — Agent name, personality, behavior rules
- **`users.json`** — Household member profiles
- **`guidelines.json`** — Edit before locking; defines the agent's operating boundaries

### 8. Add to configuration.yaml

Copy contents of [`configuration_additions.yaml`](configuration_additions.yaml). Includes input_text, shell_commands, and command_line sensors.

### 9. Configure Telegram

Set up [Telegram bot](https://www.home-assistant.io/integrations/telegram/) in **polling mode**:

1. Create bot via [@BotFather](https://t.me/botfather)
2. Get chat_id via [@userinfobot](https://t.me/userinfobot)
3. Configure via HA UI. If previously used webhook: `https://api.telegram.org/botTOKEN/deleteWebhook`

### 10. Add automations

Copy [`automations/permear.yaml`](automations/permear.yaml) and replace `YOUR_CHAT_ID`, `YOUR_AGENT_ID`, `person.YOUR_PERSON`.

**Finding your agent_id:** Go to Developer Tools → Services → select `conversation.process` → the agent dropdown shows all available agents. The entity_id is shown (e.g., `conversation.google_ai_conversation`). Do NOT guess this — verify it.

### 11. Update LLM system prompt

Add to your conversation agent's instructions (Settings → your LLM integration → Configure → Instructions):

```
SYSTEM MONITORING: You monitor HA health via pre-briefing cycles.
Critical errors: notify immediately via Telegram with suggested fix.
Non-critical: include in daily briefing or wait for user to ask.
Updates: mention in daily briefing only.
New devices: ask user how to name them.

AUTOMATIONS: You can create and remove simple HA automations.
To create: use manage_agent_auto_create with JSON: {"alias": "name", "trigger": {...}, "action": {...}}
To remove: use manage_agent_auto_remove with the alias or id.
To list: use manage_agent_auto_list.
ALWAYS ask for confirmation before creating. NEVER create without explicit approval.

ENTITY MONITORING: When user says "monitor [entity]" or "stop monitoring [entity]":
To add: use add_monitored_entity. To remove: use remove_monitored_entity.
```

### 12. Run initial discovery

Via Developer Tools → Services → `shell_command.discover_entities`. This populates `monitored_entities.json` with entities exposed to your conversation agent.

### 13. Restart HA and test

```
Developer Tools → Services → shell_command.ha_log_monitor
Developer Tools → Services → shell_command.manage_agent_auto_list
```

Send a test message via Telegram to verify the handler works.

## Critical Technical Notes

1. **Never use sentence triggers** (`platform: conversation`). They intercept before the LLM.
2. **Verify your agent_id** — it's NOT always `conversation.google_generative_ai`. Common: `conversation.google_ai_conversation`. Check Developer Tools.
3. **`telegram_bot.send_message`**: Use `chat_id`, not `target` (deprecated).
4. **One automation per `telegram_text` event** is safest. Quick-learning works as exception due to strict keyword conditions.
5. **HA triggers are static.** You cannot dynamically generate triggers from a JSON file. The event buffer triggers must be hardcoded in YAML.
6. **Entity IDs via UI get double prefixes** (e.g., `input_text.input_text_X`). Always verify in States.
7. **Container paths**: `/config/` = `/homeassistant/` (HAOS terminal) = `smb://IP/config/`.
8. **YAML anchors break the HA parser.** Don't use them.
9. **`max_tokens` must be 8192+** for weekly compilation. If it fails with "Invalid JSON" or "truncated," this is the cause.
10. **`ha_updates_check.py` only works inside HAOS container** where `SUPERVISOR_TOKEN` exists. Cannot be tested from SSH addons.
11. **Shell command JSON has limits.** `input_text` caps at 255 chars. Use `| truncate()` not `[:255]` in HA templates (the slice syntax causes Jinja2 errors).
12. **Gemini ignores format instructions with long conversation history.** If the agent stops following a format, the `conversation_id` may need to be reset or the instruction injected directly in the message text.
13. **Entity registry accumulates phantom automations** from old YAML files. After major version upgrades, clean orphaned entities via Settings → Entities → filter "unavailable" → delete.
14. **`discover_entities.py` filters by `should_expose`** in the entity registry (`core.entity_registry` → `options.conversation.should_expose: true`). Without this filter, you get 150+ entities instead of the ~30 the LLM actually sees.

## Adapting to Other LLMs

Replace `YOUR_AGENT_ID` with your agent's entity_id:
- **Google**: Usually `conversation.google_ai_conversation` (verify!)
- **OpenAI**: `conversation.openai_conversation`
- **Ollama**: `conversation.ollama` — verify hardware can handle it

The prompts are model-agnostic. Smaller models may struggle with JSON output in weekly compilation.

## FAQ

**Q: Does this work without Telegram?**
A: The memory system works independently. Adapt briefing/pre-briefing delivery to `notify.mobile_app_*` or another service.

**Q: How much storage does this use?**
A: Under 100KB even after months. The 7-day rotation prevents growth.

**Q: The pre-briefing is too noisy?**
A: Reply with "irrelevant" or "don't care" and the quick-learn system adds the restriction immediately. See [Customization Guide](docs/customization.md) for localized keywords.

**Q: How do I approve an automation the agent proposes?**
A: The agent asks via Telegram. Reply "yes" or "approve" and it creates the automation. The weekly compilation can also propose automations — these appear in `insights.json` under `automation_suggestions` for you to discuss with the agent.

**Q: Weekly compilation fails with "Invalid JSON"?**
A: Almost certainly `max_tokens` is too low. Set to 8192+. Check `/config/logs/` for the raw response.

## Changelog

### v5.2 (2026-04-07)
- **`monitored_entities.json` as single source of truth**: The file now serves two roles — entities with `monitor: true` are read by the pre-briefing prompt, and entities with an `events` array define triggers for the event buffer automation. No more maintaining two separate lists.
- **`generate_buffer_events.py`**: New script that reads `events` from `monitored_entities.json` and regenerates the automation YAML triggers between `[BEGIN]`/`[END]` markers. Run after editing events in the JSON.
- **`discover_entities.py` preserves user fields**: Discovery now preserves existing `monitor` and `events` fields when updating entities. Previously, rediscovery could overwrite user-set flags.
- **`build_prebriefing.py` filters by `monitor: true`**: Only entities explicitly marked for monitoring are included in the pre-briefing prompt.
- **`customization.md` rewritten**: New section "Entity Monitoring vs. Event Logging" explains the two systems and the `generate_buffer_events.py` workflow.

### v5.1 (2026-04-06)
- **Agent ID fix**: Documented that the correct entity_id is often `conversation.google_ai_conversation`, NOT `conversation.google_generative_ai`. Must be verified in Developer Tools.
- **`discover_entities.py` filters by `should_expose`**: Now reads `core.entity_registry` and only includes entities with `options.conversation.should_expose: true`. Without this, 150+ entities were sent to the LLM instead of ~30.
- **`weekly_compile.py` apply_users fix**: Now handles ANY field in `{add, remove}` diff format, not just `observed_patterns`. Prevents data corruption when the LLM sends restrictions or other fields in diff format.
- **Truncation detection**: `weekly_compile.py` detects unbalanced braces/brackets before parsing. Logs raw response to `/config/logs/`.
- **Jinja2 fix**: Uses `| truncate()` instead of `[:255]` slice in HA templates (slice syntax causes KeyError in HA's Jinja2).
- **HA triggers are static**: Documented that automation triggers cannot be generated dynamically — they must be hardcoded in YAML.
- **`ha_updates_check.py` requires SUPERVISOR_TOKEN**: Documented that this only works inside the HAOS container, not from SSH addons.
- **Prompt compaction**: Weekly prompt limits to 20 events and 10 interactions per day to avoid MAX_TOKENS truncation.

### v5.0 (2026-04-06)
- **Agent as system caretaker**: The agent monitors HA health, checks for updates, autodiscovers entities, and can create native HA automations.
- **Allowed actions removed**: The v4.0 `allowed_actions.json` approach replaced by agent-created HA automations (`agent_automations.yaml` + `manage_agent_automations.py`).
- **HA health monitoring**: `ha_log_monitor.py` parses HA logs for errors/warnings/unavailable entities.
- **Update checking**: `ha_updates_check.py` queries Supervisor API for HA Core and addon updates.
- **Entity autodiscovery**: `discover_entities.py` runs daily at 06:00, replaces hardcoded entity lists.

### v3.2 (2026-03-31)
- Telegram context injection (`input_text.permear_last_agent_message`)
- Briefing memory timing clarification
- Quick-learn localization guide

### v3.0 (2026-03-29)
- Initial release: 7-day memory, 3 perennial files, weekly compilation, Telegram briefings

## License

MIT — Use it, fork it, improve it.

## Credits

Architecture designed in collaboration with Claude (Anthropic).
