# Migration Guide

## From v7.2.0 → v7.3.0 (5 minutes)

v7.3 is a stability release. Almost transparent for v7.2 users.

### Step 1: Backup

```bash
cd /config
tar -czf permear_v72_backup_$(date +%Y%m%d).tar.gz \
    scripts/ memory/ automations/permear.yaml secrets.yaml
```

### Step 2: Update files

```bash
cd /tmp
git clone https://github.com/zzzmada/permear permear_v73
cd permear_v73

# Replace scripts (keep your permear_config.py customizations)
cp -r scripts /config/scripts.new
cp /config/scripts/permear_config.py /config/scripts.new/   # preserve your config
rm -rf /config/scripts
mv /config/scripts.new /config/scripts
chmod +x /config/scripts/*.py

# Replace automation
cp automations/permear.yaml /config/automations/permear.yaml
```

### Step 3: Add the new AI Task secrets

Edit `/config/secrets.yaml` and add:

```yaml
# New in v7.3 — AI Task entities (used by !secret in permear.yaml)
permear_ai_task_primary: ai_task.openrouter_deepseek_v3
permear_ai_task_secondary: ai_task.google_ai_task
```

Adjust the entity IDs to match your actual HA AI Task entities (Settings → Devices & Services → look at the entity IDs of your AI Task entries).

### Step 4: Restart HA

That's it. No memory file changes. No configuration.yaml changes.

### Verify

```bash
# Should show no errors
tail -50 /config/home-assistant.log | grep -i "permear\|secret\|nabu"

# Sensor still alive
# Developer Tools → States → sensor.permear_health
```

---

## From v5.x → v7.3.0

This is a **breaking change release**. Estimated time: **20-30 minutes**.

### Before you start

```bash
cd /config
tar -czf permear_v5_backup_$(date +%Y%m%d).tar.gz \
    scripts/ memory/ automations/permear.yaml secrets.yaml
```

If anything goes wrong:

```bash
tar -xzf permear_v5_backup_*.tar.gz
# Restart HA
```

### Step 1: Set up AI Task entities

PERMEAR 7.3 uses native `ai_task.generate_data` for non-interactive cycles.

**Primary: DeepSeek via OpenRouter**

1. Get OpenRouter API key at https://openrouter.ai/keys
2. HA → Settings → Devices & Services → **OpenRouter** → configure with key
3. Add a sub-entry **AI Task** with model `deepseek/deepseek-v4-flash`
4. Note the entity ID (typically `ai_task.openrouter_deepseek_v3`)
5. **Strongly recommended:** set up BYOK — see [docs/byok.md](docs/byok.md)

**Secondary: Gemini (you likely already have it)**

1. HA → existing Google Generative AI integration
2. Add a sub-entry **AI Task**
3. Note the entity ID (`ai_task.google_ai_task`)

**Verify both work** — Developer Tools → Actions:

```yaml
service: ai_task.generate_data
data:
  task_name: "Migration test"
  entity_id: ai_task.openrouter_deepseek_v3
  instructions: "Reply with OK."
  structure:
    r: { selector: { text: {} } }
```

Should return `data.r: OK`. Repeat with secondary.

### Step 2: Replace PERMEAR files

**Don't merge** — replace completely. This avoids git conflicts.

```bash
# Delete old PERMEAR
rm -rf /config/scripts
rm /config/automations/permear.yaml
rm -f /config/memory/guidelines.json
chmod u+w /config/memory/guidelines.json 2>/dev/null || true

# Clone fresh
cd /tmp
git clone https://github.com/zzzmada/permear
cd permear

# Copy new files
cp -r scripts /config/
cp automations/permear.yaml /config/automations/
cp memory/guidelines.json /config/memory/
cp memory/lovelace_card.yaml /config/memory/
chmod 444 /config/memory/guidelines.json
chmod +x /config/scripts/*.py
```

### Step 3: Update permear_config.py

Edit `/config/scripts/permear_config.py` — verify:

```python
AI_TASK_PRIMARY = "ai_task.openrouter_deepseek_v3"
AI_TASK_SECONDARY = "ai_task.google_ai_task"
```

### Step 4: Translate memory files (if needed)

If your `soul.json`, `users.json`, `insights.json` were in another language, translate keys to English. New code expects:

| File | New keys |
|---|---|
| `soul.json` | `name`, `mission`, `tone`, `values`, `behavior_rules` |
| `users.json` per user | `role`, `response_style`, `primary_channel`, `preferred_temperature`, `interests`, `restrictions`, `observed_patterns` |
| `insights.json` | `last_compilation`, `detected_patterns`, `pending`, `automation_suggestions`, `_timestamps` |
| daily files | `date`, `events`, `interactions`, `daily_memories`, `briefing_sent`, `bulletin_triggered` |

For most users on English-based v5.x, no changes needed. Compare with `memory/*.example.json` if unsure.

### Step 5: Update secrets.yaml

Add to `/config/secrets.yaml`:

```yaml
permear_chat_id: YOUR_TELEGRAM_CHAT_ID
permear_agent_id: conversation.your_interactive_agent
permear_person_entity: person.your_name
permear_ai_task_primary: ai_task.openrouter_deepseek_v3
permear_ai_task_secondary: ai_task.google_ai_task
```

### Step 6: Update configuration.yaml

Remove old PERMEAR `shell_command:` and `sensor:` blocks. Paste contents of `configuration_additions.yaml` from the new repo.

### Step 7: Validate and restart

```bash
# Validate Python
python3 -c "
import sys
sys.path.insert(0, '/config/scripts')
from permear_config import *
from lib.memory import load_json
from lib.agent import get_health_summary_for_prompt
print('Python OK')
"

# Validate YAML
python3 -c "
import yaml
class L(yaml.SafeLoader): pass
L.add_constructor('!secret', lambda l, n: 'SEC')
L.add_constructor('!include', lambda l, n: 'INC')
L.add_constructor('!include_dir_named', lambda l, n: 'INC')
yaml.load(open('/config/automations/permear.yaml'), Loader=L)
print('YAML OK')
"
```

Then HA → Settings → System → **Restart**.

### Step 8: Smoke test

1. **Sensor exists:** Developer Tools → States → `sensor.permear_health` → state should be `all_ok`
2. **AI Task works:** force pre-briefing — `service: automation.trigger`, target: `automation.permear_prebriefing`, data: `skip_condition: true`
3. **Telegram works:** send "hi" to your bot
4. **List automations works:** send `/list_automations`

### Rollback if needed

```bash
cd /config
tar -xzf permear_v5_backup_*.tar.gz
# Restart HA
```

---

## Common issues

| Symptom | Fix |
|---|---|
| `sensor.permear_health` unavailable | `echo '{}' > /config/memory/agent_circuit.json`, reload sensors |
| `429` errors in logs | Set up BYOK ([docs/byok.md](docs/byok.md)) |
| YAML parse error | Check indentation in `configuration_additions.yaml` |
| Callbacks not working | Reload Automations after restart |

Need help? Open an issue at https://github.com/zzzmada/permear/issues.
