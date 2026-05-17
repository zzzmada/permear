# Migration: PERMEAR 5.x → 7.2.0

This is a **breaking change release**. Estimated time: **15-20 minutes**.

---

## Before you start

```bash
# Backup everything
cd /config
tar -czf permear_v5_backup_$(date +%Y%m%d).tar.gz \
    scripts/ memory/ automations/permear.yaml secrets.yaml
```

If anything goes wrong:

```bash
tar -xzf permear_v5_backup_*.tar.gz
# Restart HA
```

---

## Step 1: Set up AI Task entities

PERMEAR 7.2 uses native `ai_task.generate_data` for non-interactive cycles. You need **two AI Task entities**.

### Primary: DeepSeek via OpenRouter

1. Get OpenRouter API key at https://openrouter.ai/keys
2. HA → Settings → Devices & Services → **OpenRouter** → configure with key
3. Add a sub-entry **AI Task** with model `deepseek/deepseek-v4-flash`
4. Note the entity ID (typically `ai_task.openrouter_deepseek_v3`)
5. **Strongly recommended:** set up BYOK — see [docs/byok.md](docs/byok.md)

### Secondary: Gemini (you likely already have it)

1. HA → existing Google Generative AI integration
2. Add a sub-entry **AI Task**
3. Note the entity ID (`ai_task.google_ai_task`)

### Verify both work

Developer Tools → Actions:

```yaml
service: ai_task.generate_data
data:
  task_name: "Migration test"
  entity_id: ai_task.openrouter_deepseek_v3
  instructions: "Reply with OK."
  structure:
    r: { selector: { text: {} } }
```

Should return `data.r: OK`. Repeat with `ai_task.google_ai_task`.

---

## Step 2: Replace PERMEAR files

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

---

## Step 3: Update permear_config.py

Edit `/config/scripts/permear_config.py`:

```python
AI_TASK_PRIMARY = "ai_task.openrouter_deepseek_v3"   # your primary entity ID
AI_TASK_SECONDARY = "ai_task.google_ai_task"          # your secondary entity ID
```

Also verify `DAYS` list matches your daily file names. Default is English (`monday.json` etc.). If you have Portuguese filenames, either:
- Rename your files (`mv segunda.json monday.json` etc.), OR
- Edit `DAYS` to match your filenames.

---

## Step 4: Translate memory files (if needed)

If your `soul.json`, `users.json`, `insights.json` were in another language (Portuguese), translate keys to English. The new code expects:

| File | New keys (v7.2) |
|---|---|
| `soul.json` | `name`, `mission`, `tone`, `values`, `behavior_rules` |
| `users.json` per user | `role`, `response_style`, `primary_channel`, `preferred_temperature`, `interests`, `restrictions`, `observed_patterns` |
| `insights.json` | `last_compilation`, `detected_patterns`, `pending`, `automation_suggestions`, `_timestamps` |
| daily files | `date`, `events`, `interactions`, `daily_memories`, `briefing_sent`, `bulletin_triggered` |

For most users from English-based v5.x, no changes needed. Compare with `memory/*.example.json` if unsure.

---

## Step 5: Update secrets.yaml

Add (if missing):

```yaml
permear_chat_id: YOUR_TELEGRAM_CHAT_ID
permear_agent_id: conversation.your_interactive_agent
permear_person_entity: person.your_name
```

---

## Step 6: Update configuration.yaml

Remove old PERMEAR `shell_command:` and `sensor:` blocks. Paste contents of `configuration_additions.yaml` from the new repo.

---

## Step 7: Validate and restart

```bash
# Validate Python imports
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

---

## Step 8: Smoke test

1. **Sensor exists:** Developer Tools → States → `sensor.permear_health` → state should be `all_ok` or `recovering`
2. **AI Task works:** force pre-briefing manually:
   ```yaml
   service: automation.trigger
   target: { entity_id: automation.permear_prebriefing }
   data: { skip_condition: true }
   ```
3. **Telegram works:** send "hi" to your bot — should respond
4. **List automations works:** send `/list_automations` — should respond

---

## Common issues

| Symptom | Fix |
|---|---|
| `sensor.permear_health` unavailable | Create empty state: `echo '{}' > /config/memory/agent_circuit.json`, reload sensors |
| `429` errors in logs | Set up BYOK (see [docs/byok.md](docs/byok.md)) |
| YAML parse error | Re-paste `configuration_additions.yaml` carefully, check indentation |
| Callbacks not working | Reload Automations after restart |

---

## Rollback

```bash
cd /config
tar -xzf /config/permear_v5_backup_*.tar.gz
# Restart HA
```

Need help? Open an issue at https://github.com/zzzmada/permear/issues with HA log excerpt.
