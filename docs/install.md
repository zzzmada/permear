# Installing PERMEAR

Detailed installation guide. For the quick version, see [README.md](../README.md#quick-install).

---

## Prerequisites

- Home Assistant OS or Supervised, version 2025.7+
- Telegram bot configured (you need the chat ID handy)
- Long-lived access token from your HA profile
- Two LLM integrations ready (see [LLM Setup](#llm-setup) below)

---

## Method 1: install.sh (recommended)

```bash
# SSH or Terminal addon
cd /tmp
git clone https://github.com/zzzmada/permear
cd permear
bash install.sh
```

The script:
1. Creates `/config/scripts/`, `/config/memory/`, `/config/automations/` if missing
2. Prompts for HA long-lived token, saves to `/config/.permear_token`
3. Prompts for Telegram chat_id, conversation agent_id, person entity
4. Copies all PERMEAR files
5. Locks `guidelines.json` as read-only

Then follow [Post-install steps](#post-install-steps) below.

---

## Method 2: Manual install

If you prefer to do it step-by-step:

### 1. Clone the repo

```bash
git clone https://github.com/zzzmada/permear /tmp/permear
```

### 2. Copy files

```bash
cp -r /tmp/permear/scripts /config/
cp /tmp/permear/automations/permear.yaml /config/automations/
echo "[]" > /config/automations/agent_automations.yaml
chmod +x /config/scripts/*.py
```

### 3. Set up memory files

```bash
cd /config/memory
mkdir -p daily

# Copy templates
cp /tmp/permear/memory/soul.example.json soul.json
cp /tmp/permear/memory/users.example.json users.json
cp /tmp/permear/memory/insights.example.json insights.json
cp /tmp/permear/memory/monitored_entities.example.json monitored_entities.json
cp /tmp/permear/memory/guidelines.json guidelines.json
cp /tmp/permear/memory/lovelace_card.yaml lovelace_card.yaml

# Generate 7 daily files
for day in monday tuesday wednesday thursday friday saturday sunday; do
    cp /tmp/permear/memory/daily/monday.example.json daily/$day.json
done

# Lock guidelines (immutable)
chmod 444 guidelines.json
```

### 4. Generate HA token

HA UI → profile (bottom-left) → **Long-lived access tokens** → **Create token**

Save it:

```bash
echo "PASTE_YOUR_TOKEN_HERE" > /config/.permear_token
chmod 600 /config/.permear_token
```

### 5. Edit secrets.yaml

Add to `/config/secrets.yaml`:

```yaml
permear_chat_id: YOUR_TELEGRAM_CHAT_ID
permear_agent_id: conversation.your_interactive_agent
permear_person_entity: person.your_name
```

### 6. Edit configuration.yaml

Paste contents of `/tmp/permear/configuration_additions.yaml` into `/config/configuration.yaml`.

### 7. Continue with [LLM Setup](#llm-setup) and [Post-install steps](#post-install-steps).

---

## LLM Setup

You need **two LLM integrations**.

### Interactive agent (Telegram chat, voice)

This one needs Tools support for device control.

1. HA → Settings → Devices & Services → **Add Integration** → **Google Generative AI**
2. Configure with key from https://aistudio.google.com/apikey
3. In the integration options:
   - Model: `gemini-2.5-flash` (or newer)
   - Max tokens: **8192** (important — lower values truncate weekly compilation)
   - **Enable "Control Home Assistant"** (Tools)
4. Set `permear_agent_id` in `secrets.yaml` to the resulting `conversation.*` entity ID

### AI Task entities (non-interactive cycles)

#### Primary: OpenRouter with DeepSeek V4-Flash

1. Get OpenRouter API key at https://openrouter.ai/keys
2. HA → Settings → Devices & Services → **OpenRouter** → configure with key
3. Add a sub-entry **AI Task** with model `deepseek/deepseek-v4-flash`
4. The entity ID will be like `ai_task.openrouter_deepseek_v3`. Note it.
5. If it's different from the default in `permear_config.py`, edit:
   ```python
   AI_TASK_PRIMARY = "ai_task.your_actual_entity_id"
   ```

**Strongly recommended:** set up BYOK for DeepSeek — see [docs/byok.md](byok.md). $5 lasts ~4 years at typical PERMEAR usage and avoids rate limits.

#### Secondary: Google AI Task (fallback)

1. Same Google Generative AI integration (already set up above)
2. Add a sub-entry **AI Task**
3. The entity ID will be `ai_task.google_ai_task`

---

## Post-install steps

### 1. Restart Home Assistant

Settings → System → Restart.

### 2. Run initial entity discovery

Developer Tools → Services:

```yaml
service: shell_command.discover_entities
```

This populates `/config/memory/monitored_entities.json` with entities exposed to voice assistants.

### 3. Test Telegram

Send "hi" to your Telegram bot. The agent should respond.

### 4. Verify sensors

Developer Tools → States → search `permear`:
- `sensor.permear_health` should be in `all_ok` or `recovering`
- `sensor.current_day_memory` should have today's date

### 5. (Optional) Add Lovelace health card

HA → Settings → Dashboards → your dashboard → ⋮ → Edit Dashboard → ⋮ → **Raw configuration editor**

Paste contents of `/config/memory/lovelace_card.yaml` at the bottom (under `cards:` or as a top-level card under your view).

### 6. Customize

Edit:
- `/config/memory/soul.json` — agent name, tone, behavior rules
- `/config/memory/users.json` — one key per resident

See [docs/customization.md](customization.md) for the full guide.

---

## File structure

```
/config/
├── scripts/
│   ├── lib/                          Shared library (memory, agent, logs)
│   │   ├── __init__.py
│   │   ├── memory.py                 JSON/YAML I/O
│   │   ├── agent.py                  Circuit breaker + health helpers
│   │   └── logs.py                   Error classification
│   ├── permear_config.py             All paths and constants
│   ├── build_briefing.py             Daily briefing prompt builder
│   ├── build_prebriefing.py          Hourly pre-briefing prompt builder
│   ├── briefing_simple.py            Python fallback if LLM fails 3x
│   ├── weekly_compile.py             Weekly compilation (3 JSON inputs)
│   ├── apply_daily_memory.py         Save extracted memories
│   ├── apply_quick_learning.py       Save restriction from chat
│   ├── append_daily.py               Add event/interaction to daily
│   ├── discover_entities.py          Sync with entity registry
│   ├── manage_agent_automations.py   CRUD for agent automations
│   ├── manage_archived.py            Silenced 24h errors
│   ├── ha_log_monitor.py             Parse home-assistant.log
│   ├── ha_updates_check.py           HA updates via Supervisor API
│   ├── ha_update_manager.py          Install/skip updates
│   ├── circuit_breaker.py            Entry point → lib/agent.py
│   ├── process_log_event.py          Entry point → lib/logs.py
│   ├── sensor_permear_health.py      Health sensor (4 states)
│   ├── sensor_current_day.py         Today's daily as sensor attrs
│   ├── sensor_perennial.py           soul/users/insights as sensor attrs
│   ├── log_fallback.py               Increment fallback counter
│   ├── forget_old_items.py           30-day retention
│   ├── get_monitored_entities_text.py  Format entities for prompts
│   ├── build_automation_spec.py      Transform spec → HA format
│   ├── write_pending_spec.py         Avoid 255-char limit
│   └── generate_buffer_events.py     Regenerate triggers
│
├── memory/
│   ├── soul.json                     Agent personality
│   ├── users.json                    Household profiles
│   ├── insights.json                 Patterns, pending, suggestions
│   ├── guidelines.json               IMMUTABLE (chmod 444)
│   ├── monitored_entities.json       Entity list + events
│   ├── agent_circuit.json            Auto-generated (circuit state)
│   ├── archived_errors.json          Auto-generated (silenced errors)
│   ├── insights_archived.json        Auto-generated (30-day archive)
│   ├── pending_auto_spec.json        Temp file (auto cleanup)
│   ├── lovelace_card.yaml            Dashboard snippet
│   └── daily/
│       └── {monday..sunday}.json     7 weekday files
│
├── automations/
│   ├── permear.yaml                  Main PERMEAR automations
│   └── agent_automations.yaml        Agent-created (starts as [])
│
└── secrets.yaml                      With permear_chat_id, etc.
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Telegram bot doesn't respond | Token wrong or HA can't reach Telegram | Check `secrets.yaml`, `tail /config/home-assistant.log` |
| `Circuit breaker open` Telegram message | LLM had 3 consecutive failures | Wait 10 min cooldown, check provider status |
| `sensor.permear_health` shows `fallback_active` | Primary hit rate limit | Check OpenRouter / DeepSeek dashboards |
| Briefing didn't arrive at 23:30 | Circuit breaker open or Telegram chat ID wrong | Check `sensor.permear_health.summary` |
| Pre-briefing always silent | This is by design — `SILENCE` when nothing matters | Check daily file is populating to confirm cycles run |
| `Error code 429` in logs | DeepSeek rate-limited | Set up BYOK (see [docs/byok.md](byok.md)) |
| Automation creation says "couldn't parse" | Provider returned empty/non-JSON | Be more specific (entity name, time) |

Quick diagnostic commands:

```bash
python3 /config/scripts/circuit_breaker.py status
python3 /config/scripts/sensor_permear_health.py
python3 -c "import sys; sys.path.insert(0, '/config/scripts'); from lib.agent import get_health_summary_for_prompt; print(get_health_summary_for_prompt())"
```
