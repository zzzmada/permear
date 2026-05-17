# PERMEAR

**Persistent Memory Architecture for Home Assistant AI Agents.**

PERMEAR turns Home Assistant + an LLM into a household agent that remembers, learns, and proposes — without you babysitting it.

> *Latest release: **v7.2.0**. See [CHANGELOG.md](CHANGELOG.md) for what's new. Upgrading from v5.x? See [MIGRATION.md](MIGRATION.md).*

<<<<<<< HEAD
Home Assistant's conversation agents (Gemini, OpenAI, etc.) have no memory between interactions. Every conversation starts from zero. PERMEAR fixes that with a file-based memory architecture that gives your agent a persistent soul, user profiles, learned insights, and the ability to create automations and monitor system health.

**The agent evolves from household assistant to system caretaker** — it monitors HA health, detects errors (including its own), checks for updates, autodiscovers entities, and can create native HA automations with user approval.
=======
---

## What PERMEAR does
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)

PERMEAR is a Home Assistant configuration that gives your LLM-based voice/chat assistant:

- **Persistent memory** across days, weeks, and indefinitely (file-based, no database required)
- **Proactive contact** via Telegram when something relevant happens (and silence when nothing does)
- **Daily and weekly self-reflection** that distills events into reusable patterns
- **Automation creation by chat** — describe what you want, agent proposes, you confirm
- **Active forgetting** — items not seen in 30 days get archived automatically
- **Health monitoring** — circuit breaker, retry, and automatic fallback between LLM providers
- **Real-time error filtering** — HA errors come to Telegram, noise stays out

It runs on **Home Assistant OS or Supervised**, including a **Raspberry Pi 4 with 2 GB RAM**.

---

## Architecture at a glance

```
<<<<<<< HEAD
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
=======
┌─────────────────────────────────────────────────────────────┐
│                Home Assistant + PERMEAR                     │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐   ┌────────────────┐  │
│  │ Telegram bot │◄──►│ Conversation │   │  AI Task entity│  │
│  │   (chat,     │    │   agent      │   │  (structured   │  │
│  │   buttons)   │    │  (Gemini)    │   │   output)      │  │
│  └──────────────┘    └──────────────┘   └────────────────┘  │
│         │                  │ Tools             │            │
│         ▼                  ▼                   ▼            │
│  Interactive cycles    Voice control     Non-interactive    │
│  (chat, voice)         (lights, fans)    (briefings,        │
│                                           weekly compile,   │
│                                           automation create)│
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │     /config/memory/   (persistent state)            │    │
│  │     soul.json · users.json · insights.json          │    │
│  │     guidelines.json · monitored_entities.json       │    │
│  │     daily/{monday..sunday}.json                     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

PERMEAR keeps **two LLM paths** intentionally separated:

| Path | Used for | Why |
|---|---|---|
| `conversation.process` (interactive) | Telegram chat replies, voice commands | Needs HA Tools support for device control |
| `ai_task.generate_data` (non-interactive) | Briefings, weekly compile, automation creation, memory extraction, restriction learning | Native structured output, no fence-stripping, schema-guaranteed |

Why this split matters: the interactive path needs Gemini (or another Tools-capable provider). The non-interactive path can use cheaper models like DeepSeek V4-Flash, which is ~5× cheaper per token than Gemini for structured tasks. **You pay almost nothing per month while keeping the smart parts smart.**

---

## Cycles

| Cycle | Time | What it does |
|---|---|---|
| Pre-briefing | Hourly, 08:30–20:00 | Reads house state, decides if proactive Telegram message is warranted (mostly silent) |
| Daily briefing | 23:30 | 120-word summary of the day, with pending items and update suggestions |
| Memory extraction | After briefing | LLM picks the 5 most useful sentences worth re-reading; saved to today's daily file |
| Entity discovery | 06:00 | Syncs `monitored_entities.json` with HA entity registry (entities exposed to voice) |
| Weekly compilation | Sunday 04:00 | 3 focused LLM calls update `soul.json`, `users.json`, `insights.json` |
| Forget old items | Before weekly | Patterns/pending not mentioned in 30+ days move to archive |
| Daily reset | 00:00 | Emits `permear_day_reset` event |
| Real-time error monitor | Continuous | Filters noisy components, alerts on genuine errors with [Silence 24h] button |

---

## AI Provider Architecture

Configure **two** AI Task entities in your Home Assistant (Settings → Devices & Services), one of each:

1. **Primary** (cheap, non-interactive): OpenRouter integration with DeepSeek V4-Flash
   *Entity ID expected by config:* `ai_task.openrouter_deepseek_v3`
2. **Secondary** (fallback): Google AI Task integration with Gemini Flash
   *Entity ID expected by config:* `ai_task.google_ai_task`

You can customize entity IDs in `scripts/permear_config.py`. Both entities must exist for the fallback mechanism to work.

**Recommended setup for DeepSeek:** add **BYOK (Bring Your Own Key)** in OpenRouter pointing to your `platform.deepseek.com` API key. This routes billing through DeepSeek directly (cheaper, no OpenRouter fee, larger rate limits). See [docs/byok.md](docs/byok.md) for setup.

**Estimated monthly cost (typical household):** $0.06 – $0.15 USD. Gemini interactive runs in free tier (~5 chats/day fits easily).

---

## Fallback model

Every `ai_task.generate_data` call follows this pattern:

```yaml
# 1. Pre-check: skip primary if a recent fallback happened (< 1h ago)
- choose:
    - conditions: [primary degraded recently?]
      sequence: [call secondary directly]
  default:
    # 2. Try primary
    - ai_task.generate_data: { entity_id: primary }
      continue_on_error: true
    # 3. Try secondary if primary returned empty/failed
    - if: [result empty or undefined]
      then: [call secondary]
```

The fallback is **automatic and silent**. The `sensor.permear_health` will show `fallback_active` if it kicks in. Your weekly briefings keep happening even when one provider has a bad day.

---

## Requirements

- **Home Assistant OS or Supervised** version 2025.7+ (for `ai_task.generate_data`)
- **Telegram bot** integration configured (chat ID required)
- **Two LLM integrations:**
  - Google Generative AI (free tier OK) for interactive Telegram/voice
  - OpenRouter or DeepSeek direct for non-interactive cycles
- **Python 3.11+** (comes with HAOS)
- Disk space: ~50 MB
- RAM: works on RPi4 2GB

---

## Installation

### Quick install (recommended)

Use the install script contributed by [@clyra](https://github.com/clyra):

```bash
# SSH or Terminal addon on your HA instance
cd /config
wget https://raw.githubusercontent.com/zzzmada/permear/main/install.sh
bash install.sh
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
```

The script:
1. Creates `/config/scripts/`, `/config/memory/`, `/config/automations/` if missing
2. Downloads all PERMEAR files
3. Generates a long-lived token at `/config/.permear_token`
4. Prints next-step instructions

<<<<<<< HEAD
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
=======
### Manual install

1. **Clone the repo:**
   ```bash
   git clone https://github.com/zzzmada/permear /tmp/permear
   ```
2. **Copy files into your HA config:**
   ```bash
   cp -r /tmp/permear/scripts /config/
   cp -r /tmp/permear/memory /config/
   cp /tmp/permear/automations/permear.yaml /config/automations/
   touch /config/automations/agent_automations.yaml
   echo "[]" > /config/automations/agent_automations.yaml
   ```
3. **Convert example memory files to live ones:**
   ```bash
   cd /config/memory
   cp soul.example.json soul.json
   cp users.example.json users.json
   cp insights.example.json insights.json
   cp monitored_entities.example.json monitored_entities.json
   chmod 444 guidelines.json   # immutable
   for day in monday tuesday wednesday thursday friday saturday sunday; do
     cp daily/monday.example.json daily/$day.json
   done
   ```
4. **Generate the HA long-lived token:**
   *HA UI → your profile → Long-lived access tokens → Create*. Save it:
   ```bash
   echo "PASTE_YOUR_TOKEN_HERE" > /config/.permear_token
   chmod 600 /config/.permear_token
   ```
5. **Edit `/config/secrets.yaml`** — add entries from `secrets.yaml.example`.
6. **Edit `/config/configuration.yaml`** — paste contents of `configuration_additions.yaml`.
7. **Set up your LLM integrations** (see [Configure LLMs](#configure-llms) below).
8. **Restart Home Assistant.**
9. **Run initial entity discovery** (Developer Tools → Services):
   ```yaml
   service: shell_command.discover_entities
   ```
10. **Test by saying "hi" to your Telegram bot.**

---

## Configure LLMs

### 1. Interactive agent (Telegram chat, voice)

You need a **conversation entity** that supports Tools.

- Install **Google Generative AI** integration
- Configure with your Google AI Studio key
- In the integration options, set:
  - Model: `gemini-2.5-flash` or newer
  - Max tokens: 8192
  - Enable "Control Home Assistant" (Tools)
- This gives you `conversation.google_generative_ai_conversation` (rename as needed)
- Set `permear_agent_id` in `secrets.yaml` to this entity ID

### 2. AI Task entities (non-interactive cycles)

#### Primary: OpenRouter + DeepSeek V4-Flash

- Install **OpenRouter** integration
- Configure with your OpenRouter API key (`openrouter.ai/keys`)
- Add a sub-entry **AI Task** with model `deepseek/deepseek-v4-flash`
- This creates `ai_task.openrouter_deepseek_v3` (or similar — rename in `permear_config.py` if different)

**For best cost/reliability, set up BYOK:**
1. Create a key at `platform.deepseek.com/api_keys`
2. Top up $5 (lasts ~4 years at typical PERMEAR usage)
3. In OpenRouter → Settings → Integrations → DeepSeek → paste the key in **Prioritized**
4. Toggle **"Always use for this provider"**

#### Secondary: Google AI Task

- Same Google Generative AI integration (already set up in step 1)
- Add a sub-entry **AI Task**
- This creates `ai_task.google_ai_task`

---

## Customize for your household

After installation, edit:

| File | What to edit |
|---|---|
| `/config/memory/soul.json` | Agent name, tone, values, behavior rules |
| `/config/memory/users.json` | One key per resident — role, style, restrictions |
| `/config/memory/monitored_entities.json` | Add `events:` to entities you want logged to daily file |

After editing `monitored_entities.json` `events`, regenerate buffer triggers:

```bash
python3 /config/scripts/generate_buffer_events.py
```

Then reload automations in HA. See [docs/customization.md](docs/customization.md) for the full guide.

---

## Lovelace card

Want to see PERMEAR health at a glance? Paste [memory/lovelace_card.yaml](memory/lovelace_card.yaml) into:
*HA → Settings → Dashboards → your dashboard → ⋮ → Edit Dashboard → ⋮ → Raw configuration editor*.

It shows:
- 🟢 / 🟡 / 🟠 / 🔴 state of the agent today
- Fallback usage counter
- Last failure / success timestamps
- Circuit breaker state

---

## Telegram commands

| Command | What it does |
|---|---|
| Just type to chat | Talks to the interactive agent, can control devices via Tools |
| `/new_automation` (or `/nova_automacao`) | Starts the automation creation flow |
| `/list_automations` (or `/listar_automacoes`) | Shows agent-created automations with [Remove N] button per row |
| Reply with "I know", "irrelevant", etc. | Triggers quick-learning — agent extracts a restriction and saves it |
| `[Silence 24h]` button on an error alert | Silences that exact error signature for 24h |

---

## File structure

```
/config/
├── scripts/
│   ├── lib/                          # Shared library (v7.0)
│   │   ├── memory.py                 # JSON/YAML I/O
│   │   ├── agent.py                  # Circuit breaker + health helpers
│   │   └── logs.py                   # Error classification
│   ├── permear_config.py             # Paths, constants, AI_TASK_PRIMARY/SECONDARY
│   ├── build_briefing.py             # Daily briefing prompt builder
│   ├── build_prebriefing.py          # Hourly pre-briefing prompt builder
│   ├── briefing_simple.py            # Python fallback if LLM fails 3x
│   ├── weekly_compile.py             # Weekly compilation (3 JSON inputs from ai_task)
│   ├── apply_daily_memory.py         # Save extracted memories to today's daily
│   ├── apply_quick_learning.py       # Save restriction from chat to users.json
│   ├── append_daily.py               # Add event/interaction/memory to daily file
│   ├── discover_entities.py          # Sync with entity registry (--add / --remove)
│   ├── manage_agent_automations.py   # CRUD with --json output (v7.1)
│   ├── manage_archived.py            # Silenced 24h errors
│   ├── ha_log_monitor.py             # Parse home-assistant.log
│   ├── ha_updates_check.py           # Supervisor API for updates
│   ├── ha_update_manager.py          # Install/skip updates
│   ├── circuit_breaker.py            # Thin entry point → lib/agent.py
│   ├── process_log_event.py          # Thin entry point → lib/logs.py
│   ├── sensor_permear_health.py      # Health sensor (4 states)
│   ├── sensor_current_day.py         # Today's daily as sensor attrs
│   ├── sensor_perennial.py           # soul/users/insights as sensor attrs
│   ├── log_fallback.py               # Increment fallback counter (v7.1-I)
│   ├── forget_old_items.py           # 30-day retention (v7.0)
│   ├── get_monitored_entities_text.py  # Format entities for ai_task prompts
│   ├── build_automation_spec.py      # Transform raw spec → HA automation spec
│   ├── write_pending_spec.py         # Avoid 255-char input_text limit
│   └── generate_buffer_events.py     # Regenerate triggers between markers
│
├── memory/
│   ├── soul.json                     # Agent personality
│   ├── users.json                    # Household profiles
│   ├── insights.json                 # Patterns, pending, suggestions
│   ├── guidelines.json               # IMMUTABLE (chmod 444)
│   ├── monitored_entities.json       # Single source of truth: monitor + events
│   ├── agent_circuit.json            # Circuit breaker state (auto-generated)
│   ├── archived_errors.json          # Silenced 24h errors (auto-generated)
│   ├── insights_archived.json        # Items archived after 30 days
│   ├── pending_auto_spec.json        # Temp file for automation creation flow
│   └── daily/
│       └── {monday..sunday}.json
│
└── automations/
    ├── permear.yaml                  # Main PERMEAR automations
    └── agent_automations.yaml        # User automations created by agent (initially [])
```

---
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Telegram bot doesn't respond | Token wrong or HA can't reach Telegram | Check `secrets.yaml`, `tail -f /config/home-assistant.log` |
| `circuit breaker open` Telegram message | LLM had 3 consecutive failures | Wait 10 min cooldown, check provider status |
| `sensor.permear_health` shows `fallback_active` | Primary provider hit rate limit | Check OpenRouter / DeepSeek dashboards for usage |
| Briefing didn't arrive at 23:30 | Probably circuit breaker, or Telegram chat ID wrong | Check `sensor.permear_health.summary` |
| Pre-briefing always silent | This is by design — the agent reports SILENCE when nothing relevant happens | Check daily file is being populated to confirm cycles are running |
| `Error code 429` in logs | DeepSeek rate-limited | Set up BYOK (see above) |
| Automation creation says "couldn't parse" | Provider returned empty or non-JSON | Ask agent to be more specific (entity name, time) |

For detailed diagnostics, check:
```bash
python3 /config/scripts/circuit_breaker.py status
python3 /config/scripts/sensor_permear_health.py
```

<<<<<<< HEAD
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

AUTOMATIONS: Create with permear_create_automation, remove with permear_remove_automation,
list with permear_list_automations. ALWAYS ask confirmation before creating.

ENTITY MONITORING: "monitor [entity]" → add_monitored_entity.
"stop monitoring [entity]" → remove_monitored_entity.
```

### 12. Expose scripts to your agent

The LLM agent cannot call shell_commands directly — it can only use exposed HA scripts. After restarting:

Settings → Voice Assistants → your agent → Exposed Entities → enable:
- `script.permear_list_automations`
- `script.permear_create_automation`
- `script.permear_remove_automation`

Without this step, the agent will return "function does not exist" when trying to manage automations.

### 13. Restart HA and run initial discovery

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
12. **Shell commands are invisible to the LLM agent.** The agent can only call exposed scripts. PERMEAR includes wrapper scripts (`permear_list_automations`, `permear_create_automation`, `permear_remove_automation`) that must be exposed in Voice Assistants settings.
13. **Python not available in SSH addon terminal.** Run scripts via Developer Tools → Services.
14. **Clean phantom entities** after upgrades: Settings → Entities → filter "unavailable" → delete.
15. **Telegram parse_mode: All telegram_bot.send_message calls that send shell_command stdout or agent responses must include parse_mode: plain_text. Underscores in strings like NO_AUTOMATIONS break Telegram's default Markdown parser. Messages with intentional formatting should use markdownv2 with proper escaping.

## Changelog

### v5.7 (2026-04-27)

- Telegram parse_mode fix: All telegram_bot.send_message calls that send shell_command stdout or LLM responses now include parse_mode: plain_text. Underscores in internal strings (like automation IDs) were breaking Telegram's default Markdown parser with "Can't parse entities" errors.
- Human-readable script outputs: manage_agent_automations.py outputs rewritten from - JSON/internal tokens to readable text. "NO_AUTOMATIONS" → "No automations created yet." Create/remove outputs are now plain sentences without underscores.
- Internal token filter: The Telegram handler default branch now filters internal protocol tokens (LIST_AUTOS, CREATE_AUTO:, REMOVE_AUTO:, NO_AUTOMATIONS) from reaching the user as raw messages.

### v5.6 (2026-04-18)
- **Script wrappers for LLM agent**: Shell commands are invisible to the conversation agent. Added 3 HA scripts (`permear_list_automations`, `permear_create_automation`, `permear_remove_automation`) that wrap the shell commands and can be exposed to the agent via Voice Assistants settings. Without these, the agent returns "function does not exist" when trying to manage automations.

### v5.5 (2026-04-16)
- **`secrets.yaml` integration**: All user-specific values (`chat_id`, `agent_id`, `person_entity`) now use HA's native `!secret` mechanism. Zero placeholders to replace. Updates via `git pull` never overwrite user configuration.
- **`install.sh` improved**: Interactive installer with secrets.yaml setup, HA packages support, `chattr` protection for `permear_config.py`, soul.json preservation. Original script by [@clyra](https://github.com/clyra).
- **HA packages support**: `configuration_additions.yaml` works as a drop-in HA package.

### v5.4 (2026-04-08)
- **SELF_ERRORS**: `ha_log_monitor.py` classifies errors from PERMEAR components separately. Pre-briefing instructs agent to report its own failures with context.

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
=======
---

## Contributing

PRs welcome. Key principles when proposing changes:

1. **Simple, HA-native, no overengineering.** If HA does it, use HA.
2. **Single source of truth** — don't duplicate state across files.
3. **English everywhere** in this public repo. (Your private fork can be in any language.)
4. **Backward compatibility** for existing users where reasonable.

Open issues at https://github.com/zzzmada/permear/issues

---
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)

## License

MIT — see [LICENSE](LICENSE)

## Credits

<<<<<<< HEAD
- Architecture designed in collaboration with Claude (Anthropic)
- Installation script by [@clyra](https://github.com/clyra)
=======
- Author: [@zzzmada](https://github.com/zzzmada)
- Installer: [@clyra](https://github.com/clyra)
- Tested on: Raspberry Pi 4 (2GB), Home Assistant OS
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
