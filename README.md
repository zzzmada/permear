# PERMEAR — Persistent Memory Architecture for Home Assistant AI Agents

A three-layer persistent memory system that transforms Home Assistant's Gemini (or any LLM) conversation agent from a stateless chatbot into an intelligent assistant that **remembers, learns, and self-improves** over time.

> Built and battle-tested on a Raspberry Pi 4 (2GB RAM) running HAOS. No external databases, no cloud storage, no paid services beyond what you already use.

## What This Is

Home Assistant's conversation agents (Gemini, OpenAI, etc.) have no memory between interactions. Every conversation starts from zero. PERMEAR fixes that with a file-based memory architecture that gives your agent a persistent soul, user profiles, and learned insights — without external databases or middleware.

**The system runs entirely on local JSON files + Python scripts + HA automations.** The LLM itself manages its own memory through structured prompts and a weekly self-improvement cycle.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    PERENNIAL FILES                            │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐         │
│  │  soul.json   │  │ users.json  │  │ insights.json│         │
│  │ personality  │  │  profiles   │  │   patterns   │         │
│  │ rules, tone  │  │preferences  │  │  learnings   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘         │
│         │                │                │                   │
│         └────────────────┼────────────────┘                   │
│                          │                                    │
│              ┌───────────▼───────────┐                        │
│              │   guidelines.json     │                        │
│              │   IMMUTABLE (chmod 444)│                        │
│              │   Rules for editing    │                        │
│              │   perennial files      │                        │
│              └───────────────────────┘                        │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    DAILY FILES (7-day rotation)               │
│  ┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐         │
│  │ monday ││tuesday ││  ...   ││saturday││ sunday │         │
│  │ .json  ││ .json  ││        ││ .json  ││ .json  │         │
│  │events  ││events  ││        ││events  ││events  │         │
│  │interact││interact││        ││interact││interact│         │
│  │memories││memories││        ││memories││memories│         │
│  └────────┘└────────┘└────────┘└────────┘└────────┘         │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                        CYCLES                                 │
│                                                               │
│  Every 30 min ─── PRE-BRIEFING ──── Evaluate house state     │
│  (08h-20h)        Read perennials    Alert if relevant        │
│                   Read daily          SILENCE if not           │
│                   Quick-learn from    ◄── User feedback        │
│                   rejections                                  │
│                                                               │
│  Daily 21h ────── BRIEFING ───────── Summarize the day        │
│                   Read daily          Extract memories         │
│                   Read perennials     Send via Telegram        │
│                                                               │
│  Sunday 00:05 ─── WEEKLY COMPILE ─── Read all 7 dailies       │
│                   Read guidelines     Update perennials        │
│                   Detect patterns     Backup before edit       │
│                   Self-improve        Report via Telegram      │
└──────────────────────────────────────────────────────────────┘
```

## Key Concepts

### The Intelligence Comes From the LLM, Not the Infrastructure

The memory files are just JSON. The scripts are just plumbing. The actual intelligence — pattern detection, decision-making, personality — comes from the LLM reading rich context and reasoning about it. This architecture simply ensures the LLM has the right context at the right time.

### Guidelines: The Immutable Constitution

`guidelines.json` is the only file the agent can never edit. It contains the rules for *how* the agent is allowed to edit the perennial files. Think of it as a constitution: the agent operates within its boundaries, but cannot change the boundaries themselves. You write it, you own it.

### Self-Calibrating Proactivity

The pre-briefing system starts noisy (the agent alerts about everything) and becomes precise over time. When you tell the agent "that's irrelevant," it immediately learns the restriction and stops. No manual tuning — the user's natural responses are the training data.

### 7-Day Rotation Without Cleanup

Daily files are named by weekday (`monday.json` through `sunday.json`), not by date. Next Monday's events overwrite this Monday's file automatically. No cron jobs to delete old files, no growing storage. The weekly compilation on Sunday extracts patterns before the files get overwritten.

## Requirements

- Home Assistant 2023.7+ (for `shell_command` with `response_variable`)
- A conversation agent configured in HA (Gemini 2.5 Flash recommended — free tier is sufficient)
- Telegram bot configured in HA (polling mode) for briefings and bidirectional chat
- Python 3 (included in HAOS)
- SSH or Samba access to `/config/`

### Gemini Free Tier Budget

| Use | Calls/day |
|---|---|
| Pre-briefings (08h-20h, every 30min) | 24 |
| Daily briefing (21h) + memory extraction | 2 |
| Voice/Telegram interactions | 15-30 |
| Weekly compilation (Sunday) | ~0.14 |
| **Total** | **~42-57** |

Free tier limit: 1,500/day. Usage: ~4%. Plenty of headroom.

## Installation

### Step 1: Create directory structure

```bash
# SSH into your HA instance
# Inside the container, /config/ is the working directory
# Via HAOS terminal, use /homeassistant/
# Via Samba, use smb://YOUR_IP/config/

mkdir -p /config/memory/daily
mkdir -p /config/scripts
```

### Step 2: Copy files

Copy the files from this repository to your HA instance:

```
memory/
├── guidelines.json     →  /config/memory/guidelines.json
├── soul.json           →  /config/memory/soul.json
├── users.json          →  /config/memory/users.json
├── insights.json       →  /config/memory/insights.json

scripts/
├── append_daily.py             →  /config/scripts/append_daily.py
├── build_briefing.py           →  /config/scripts/build_briefing.py
├── build_prebriefing.py        →  /config/scripts/build_prebriefing.py
├── build_weekly_prompt.py      →  /config/scripts/build_weekly_prompt.py
├── update_daily_memory.py      →  /config/scripts/update_daily_memory.py
├── weekly_compile.py           →  /config/scripts/weekly_compile.py
├── apply_quick_learning.py     →  /config/scripts/apply_quick_learning.py
├── sensor_current_day.py       →  /config/scripts/sensor_current_day.py
└── sensor_perennial.py         →  /config/scripts/sensor_perennial.py
```

### Step 3: Lock guidelines

```bash
chmod 444 /config/memory/guidelines.json
```

This prevents the agent (or any script bug) from modifying the file at the OS level.

### Step 4: Customize the memory files

Edit these files to match your household:

**`soul.json`** — Your agent's personality, name, tone, and behavioral rules. This is who your agent *is*.

**`users.json`** — Profiles for each household member. Name, preferences, interaction style, comfort settings.

**`guidelines.json`** — The rules for how the agent is allowed to edit the perennial files during weekly compilation. See [Customization Guide](docs/customization.md) for details.

### Step 5: Add to configuration.yaml

Add the contents of [`configuration_additions.yaml`](configuration_additions.yaml) to your `configuration.yaml`. This includes:
- An `input_text` helper for Telegram reply context
- Shell commands for all scripts
- Command-line sensors for daily and perennial memory

### Step 6: Configure Telegram

If not already done, set up the [Telegram bot integration](https://www.home-assistant.io/integrations/telegram/) in polling mode:

1. Create a bot via [@BotFather](https://t.me/botfather) on Telegram
2. Get your chat_id via [@userinfobot](https://t.me/userinfobot)
3. Configure via the HA UI (Settings → Integrations → Telegram Bot)
4. If you previously used webhook mode, clear it: `https://api.telegram.org/botYOUR_TOKEN/deleteWebhook`

### Step 7: Add automations

Copy [`automations/permear.yaml`](automations/permear.yaml) and update:
- `YOUR_CHAT_ID` → your Telegram chat_id (integer)
- `YOUR_AGENT_ID` → your conversation agent entity_id (e.g., `conversation.google_generative_ai`)
- Sensor entity_ids to match your actual devices
- Time windows to match your schedule

### Step 8: Create a Telegram send script

Create a script in HA (Settings → Automations & Scenes → Scripts) that the agent can use for outbound Telegram:

```yaml
alias: Send Telegram
sequence:
  - service: telegram_bot.send_message
    data:
      chat_id: YOUR_CHAT_ID
      message: "{{ message }}"
fields:
  message:
    description: Message to send
    required: true
    selector:
      text:
```

Expose this script to your conversation agent.

### Step 9: Restart and test

```bash
# Validate YAML first
# Settings → YAML → Check Configuration

# Restart HA
# Settings → System → Restart
```

Test the pipeline:

```
Developer Tools → Services → shell_command.append_daily_event
Data: {"detail": "test_event"}

Developer Tools → Services → shell_command.build_briefing_prompt
# Check response in the output
```

## File Reference

### Memory Files

| File | Purpose | Edited by | Frequency |
|---|---|---|---|
| `guidelines.json` | Rules for editing perennials | Human only | Rarely |
| `soul.json` | Agent personality and behavior | Weekly compile | Weekly |
| `users.json` | Household member profiles | Weekly compile + quick-learn | Weekly + on rejection |
| `insights.json` | Detected patterns and learnings | Weekly compile | Weekly |
| `daily/*.json` | Day's events, interactions, memories | Automations + briefing | Continuously |

### Scripts

| Script | Called by | Purpose |
|---|---|---|
| `append_daily.py` | Buffer automations | Log events, interactions, memories to daily file |
| `build_briefing.py` | Briefing automation (21h) | Assemble prompt for daily summary |
| `build_prebriefing.py` | Pre-briefing automation (every 30min) | Assemble prompt for proactive evaluation |
| `update_daily_memory.py` | Post-briefing automation | Save LLM's extracted memories to daily file |
| `build_weekly_prompt.py` | Weekly compilation (Sunday) | Assemble prompt with all 7 dailies + perennials |
| `weekly_compile.py` | Weekly compilation (Sunday) | Apply LLM's proposed edits to perennials |
| `apply_quick_learning.py` | Quick-learn automation | Save rejection-based restrictions to users.json |
| `sensor_current_day.py` | Command-line sensor | Expose current day's memory as HA attributes |
| `sensor_perennial.py` | Command-line sensor | Expose perennial files as HA attributes |

### Automations

| Automation | Trigger | Purpose |
|---|---|---|
| `permear_buffer_events` | State changes (sensors, presence) | Log house events to daily file |
| `permear_telegram_handler` | `telegram_text` event | Process Telegram messages via LLM + log interaction + inject last message context |
| `permear_daily_briefing` | Time: 21:00 | Daily intelligent summary via Telegram |
| `permear_prebriefing` | Time pattern: every 30min | Proactive house evaluation, alert if relevant |
| `permear_quick_learning` | `telegram_text` with rejection keywords | Quick-learn restrictions from user feedback |
| `permear_weekly_compile` | Sunday 00:05 | Weekly self-improvement cycle |
| `permear_daily_reset` | Midnight | Emit day-reset event |

## Critical Technical Notes

These are hard-won lessons from months of debugging on a real system.

1. **Never use sentence triggers** (`platform: conversation` with specific phrases). They intercept before the LLM and cause silent tool-use failures.

2. **LLM tool use fails for complex actions** (weather.get_forecasts, notify services, nested JSON attributes). Inject data via Jinja2 templates in the prompt instead.

3. **`telegram_bot.send_message`**: Use `chat_id`, not `target` (deprecated since HA 2026.7).

4. **One automation per `telegram_text` event** is the safe rule. Multiple automations on the same event cause conflicts. The `permear_quick_learning` exception works because it has strict keyword conditions and never sends messages — but monitor it.

5. **Entity IDs with double prefixes**: Helpers created via UI get double prefixes (e.g., `input_text.input_text_my_buffer`). Always verify in Developer Tools → States.

6. **Container paths**: `/config/` inside HA container = `/homeassistant/` in HAOS terminal = `smb://IP/config/` via Samba. Same physical directory.

7. **YAML anchors (`&anchor` / `*anchor`) break the HA parser.** Don't use them.

8. **Custom events** are more reliable as triggers than boolean states with `for:` conditions.

9. **TV trigger**: Use `from: 'off'` `to: 'on'` to avoid re-triggering on internal state changes.

10. **Fixed `conversation_id`** in Telegram automation maintains context across messages.

11. **`shell_command` with `response_variable`** requires HA 2023.7+. The command's stdout becomes `result.stdout`.

12. **Short Telegram replies lose context.** When the agent asks "Should I turn on the AC?" and the user replies "yes", the LLM receives only "yes" with no reference to the question. PERMEAR stores the agent's last outbound message in `input_text.permear_last_agent_message` (255-char cap) and injects it as a context prefix in the Telegram handler. This is a supplement to `conversation_id`, which doesn't always preserve enough context.

13. **Quick-learn keywords must match the user's language.** The `permear_quick_learning` automation matches rejection words like "irrelevant" and "unnecessary" in English. If your users type in another language, these keywords won't trigger and the agent won't learn from rejections. See [Customization Guide](docs/customization.md) for localization examples.

## Adapting to Other LLMs

The architecture is LLM-agnostic. Replace `conversation.google_generative_ai` with your agent's entity_id:

- **OpenAI**: `conversation.openai_conversation`
- **Ollama** (local): `conversation.ollama` — but verify your hardware can handle it
- **Anthropic**: `conversation.anthropic` (if/when available in HA)

The prompts in `build_briefing.py`, `build_prebriefing.py`, and `build_weekly_prompt.py` are model-agnostic. Adjust tone/instructions if your LLM responds differently.

## FAQ

**Q: Does this work without Telegram?**
A: The memory system (daily files, perennials, weekly compilation) works independently. You'd lose the briefing delivery, pre-briefing alerts, and quick-learn feedback loop. You could adapt these to use `notify.mobile_app_*` or another notification service instead.

**Q: Can I use this with a local LLM (Ollama)?**
A: Yes, if your hardware supports it. The architecture is the same — just change the agent_id. Note that smaller models may struggle with the structured JSON output required by the weekly compilation. Test thoroughly.

**Q: How much storage does this use?**
A: Negligible. The 7 daily files are ~2-5KB each. Perennial files are ~1-3KB each. Weekly backups add ~10KB. Total: under 100KB even after months. The 7-day rotation prevents growth.

**Q: What happens if the weekly compilation produces bad edits?**
A: The `weekly_compile.py` script creates `.bak` files before every edit. Protected fields in `soul.json` (name, mission, values) are hardcoded as read-only in the script. The guidelines.json provides additional guardrails. If something goes wrong, restore from the `.bak` file.

**Q: The pre-briefing is too noisy / too quiet. How do I tune it?**
A: It self-tunes. Reply to unwanted alerts with "irrelevant" or "don't need to know" and the quick-learn system adds the restriction immediately. For the opposite problem (too quiet), edit `guidelines.json` to loosen the relevance criteria, or adjust the prompt in `build_prebriefing.py`.

## Changelog

### v3.2 (2026-03-31)
- **Telegram context injection**: Agent's last outbound message is stored in `input_text.permear_last_agent_message` and injected as context prefix in the Telegram handler. Fixes the problem where short replies ("yes", "no", "do it") lost reference to the agent's question.
- **Briefing memory timing note**: `build_briefing.py` prompt now clarifies that listed memories were extracted during earlier pre-briefings, not after the current briefing. Prevents the LLM from incorrectly reporting "no memories today."
- **Quick-learn localization guide**: `docs/customization.md` now includes a full section on localizing rejection keywords for non-English users, with ready-to-use examples for Portuguese (pt-BR) and Spanish.

### v3.1 (2026-03-29)
- Pre-briefing proactive system (every 30 min, 08h-20h)
- Quick-learning from user rejection (immediate restriction update)
- `apply_quick_learning.py` script

### v3.0 (2026-03-29)
- Initial public release
- 7-day rotating daily memory files
- 3 perennial files (soul, users, insights) + immutable guidelines
- Weekly self-improvement compilation
- Daily briefing via Telegram
- Bidirectional Telegram chat with LLM

## License

MIT — Use it, fork it, improve it.

## Credits

- Architecture designed in collaboration with Claude (Anthropic)
