# Migration Guide: PERMEAR 5.x → 7.2.0

This guide helps existing PERMEAR users upgrade from version 5.x to 7.2.0.

**Estimated time:** 30 minutes (including LLM provider setup).

**Breaking changes:** moderate. Daily file keys renamed to English, scripts reorganized, AI Task entities required for non-interactive cycles.

---

## Before you start

### Back up everything

```bash
cd /config
tar -czf permear_v5_backup_$(date +%Y%m%d).tar.gz \
    scripts/ memory/ automations/permear.yaml secrets.yaml
mv permear_v5_backup_*.tar.gz /config/backups/
```

### Document your customizations

If you've edited:
- `/config/memory/soul.json` — copy your `regras_comportamento` list
- `/config/memory/users.json` — copy each user's `padroes_observados` and `restricoes`
- `/config/memory/insights.json` — copy `padroes_detectados`, `pendencias`, `sugestoes_automacao`

You'll re-paste these into the renamed fields below.

---

## Step 1: Set up AI Task entities

PERMEAR 7.2 uses native `ai_task.generate_data` for non-interactive cycles. You need **two** AI Task entities:

### Primary (DeepSeek via OpenRouter)

1. Get an OpenRouter API key: https://openrouter.ai/keys
2. Optional but recommended: get a DeepSeek key at https://platform.deepseek.com and add it to OpenRouter Settings → Integrations → DeepSeek as BYOK
3. In HA: Settings → Devices & Services → Add Integration → **OpenRouter**
4. Configure with your OpenRouter API key
5. Add a sub-entry **AI Task** with model `deepseek/deepseek-v4-flash`
6. Note the entity ID (typically `ai_task.openrouter_deepseek_v3` or similar)

### Secondary (Gemini)

You likely already have this from your v5.x conversation agent.

1. In HA: Settings → Devices & Services → Google Generative AI (existing instance)
2. Add a sub-entry **AI Task**
3. Note the entity ID (`ai_task.google_ai_task`)

### Verify both work

Developer Tools → Actions:

```yaml
service: ai_task.generate_data
data:
  task_name: "Migration test"
  entity_id: ai_task.openrouter_deepseek_v3   # then repeat with secondary
  instructions: "Respond with the single word OK."
  structure:
    response:
      selector:
        text: {}
```

You should see `response: OK` in the result.

---

## Step 2: Update file structure

### Pull new code

```bash
cd /tmp
git clone https://github.com/zzzmada/permear permear_v7
```

### Replace scripts

```bash
rm -rf /config/scripts
cp -r /tmp/permear_v7/scripts /config/
chmod +x /config/scripts/*.py
```

### Update permear_config.py

Edit `/config/scripts/permear_config.py`. Verify or change:

```python
AI_TASK_PRIMARY = "ai_task.openrouter_deepseek_v3"   # your primary entity ID
AI_TASK_SECONDARY = "ai_task.google_ai_task"          # your secondary entity ID
```

### Replace automation

```bash
cp /tmp/permear_v7/automations/permear.yaml /config/automations/permear.yaml
```

If you don't have it yet, create the empty agent automations file:

```bash
[ -f /config/automations/agent_automations.yaml ] || echo "[]" > /config/automations/agent_automations.yaml
```

### Update configuration.yaml

Open `/config/configuration.yaml`. **Remove** old PERMEAR shell_command and sensor blocks. **Add** the contents of `/tmp/permear_v7/configuration_additions.yaml`.

---

## Step 3: Migrate memory files

### soul.json — translate keys

**Old (v5.x):**
```json
{
  "nome": "PERMEAR",
  "missao": "...",
  "tom": "...",
  "valores": [...],
  "regras_comportamento": [...]
}
```

**New (v7.2):**
```json
{
  "name": "PERMEAR",
  "mission": "...",
  "tone": "...",
  "values": [...],
  "behavior_rules": [...]
}
```

Edit `/config/memory/soul.json` and rename keys. Keep your existing values.

### users.json — translate keys

**Old (v5.x):**
```json
{
  "alice": {
    "papel": "...",
    "estilo_resposta": "...",
    "temperatura_preferida": 22,
    "canal_principal": "telegram",
    "interesses": [...],
    "restricoes": [...],
    "padroes_observados": [...]
  }
}
```

**New (v7.2):**
```json
{
  "alice": {
    "role": "...",
    "response_style": "...",
    "preferred_temperature": 22,
    "primary_channel": "telegram",
    "interests": [...],
    "restrictions": [...],
    "observed_patterns": [...]
  }
}
```

### insights.json — translate keys

**Old:**
```json
{
  "ultima_compilacao": null,
  "padroes_detectados": [],
  "pendencias": [],
  "sugestoes_automacao": []
}
```

**New:**
```json
{
  "last_compilation": null,
  "detected_patterns": [],
  "pending": [],
  "automation_suggestions": [],
  "_timestamps": {}
}
```

### daily files — translate keys

For each `/config/memory/daily/*.json` (Portuguese names):
1. Rename file: `segunda.json` → `monday.json`, etc.
2. Translate inner keys:
   - `data` → `date`
   - `eventos` → `events`
   - `interacoes` → `interactions`
   - `memorias_do_dia` → `daily_memories`
   - `briefing_enviado` → `briefing_sent`
   - `boletim_disparado` → `bulletin_triggered`
   - Inner event keys: `hora` → `time`, `tipo` → `type`, `detalhe` → `detail`
   - Inner interaction keys: `hora` → `time`, `canal` → `channel`, `resumo` → `summary`

**Bulk script for daily files:**

```bash
cd /config/memory/daily
declare -A renames=(
    [segunda]=monday [terca]=tuesday [quarta]=wednesday
    [quinta]=thursday [sexta]=friday [sabado]=saturday [domingo]=sunday
)
for old in "${!renames[@]}"; do
    [ -f "$old.json" ] && mv "$old.json" "${renames[$old]}.json"
done
for f in *.json; do
    python3 -c "
import json
with open('$f') as fh: d = json.load(fh)
m = {'data':'date','eventos':'events','interacoes':'interactions',
     'memorias_do_dia':'daily_memories','briefing_enviado':'briefing_sent',
     'boletim_disparado':'bulletin_triggered','hora':'time','tipo':'type',
     'detalhe':'detail','canal':'channel','resumo':'summary'}
def rename(obj):
    if isinstance(obj, dict): return {m.get(k, k): rename(v) for k, v in obj.items()}
    if isinstance(obj, list): return [rename(x) for x in obj]
    return obj
with open('$f', 'w') as fh: json.dump(rename(d), fh, indent=2, ensure_ascii=False)
"
done
```

### monitored_entities.json — keys unchanged, but verify

Same structure as v5.x. No translation needed for this file.

### Replace guidelines.json

```bash
cp /tmp/permear_v7/memory/guidelines.json /config/memory/guidelines.json
chmod 444 /config/memory/guidelines.json
```

---

## Step 4: Update secrets.yaml

Add the new entries (if not already present):

```yaml
permear_chat_id: YOUR_TELEGRAM_CHAT_ID
permear_agent_id: conversation.your_interactive_agent
permear_person_entity: person.your_name
```

These replace the hard-coded values that previous versions had in `permear.yaml`.

---

## Step 5: Validate before restart

```bash
# Validate Python scripts compile
python3 -c "
import sys
sys.path.insert(0, '/config/scripts')
from permear_config import *
from lib.memory import load_json
from lib.agent import get_health_summary_for_prompt
print('imports OK')
"

# Validate YAML
python3 -c "
import yaml
class L(yaml.SafeLoader): pass
L.add_constructor('!secret', lambda l, n: 'SECRET:' + l.construct_scalar(n))
L.add_constructor('!include', lambda l, n: 'INCLUDE:' + l.construct_scalar(n))
yaml.load(open('/config/automations/permear.yaml'), Loader=L)
print('YAML OK')
"

# Validate memory JSON
for f in /config/memory/*.json; do
    python3 -c "import json; json.load(open('$f'))" && echo "$f OK"
done
```

---

## Step 6: Restart Home Assistant

Settings → System → Restart.

---

## Step 7: Smoke test

1. **Sensor exists:**
   Developer Tools → States → `sensor.permear_health` → should show `all_ok`

2. **AI Task primary works:**
   Force pre-briefing manually:
   ```yaml
   service: automation.trigger
   target:
     entity_id: automation.permear_prebriefing
   data:
     skip_condition: true
   ```
   Wait ~30s. Should either get a Telegram message or silent SILENCE.

3. **Telegram chat works:**
   Send "hi" to your bot — should respond.

4. **List automations works:**
   Send `/list_automations` — should respond (probably "No automations yet").

---

## Common issues

### "Sensor.permear_health unavailable"

Likely cause: `sensor_permear_health.py` not found or `agent_circuit.json` doesn't exist yet.

```bash
# Create empty state file
echo '{"daily_stats": {}}' > /config/memory/agent_circuit.json
# Reload command-line sensors
# HA → Developer Tools → YAML → Reload Command Line Sensors
```

### "Provider returned error 429"

Solution: set up BYOK. See README "Configure LLMs" section.

### "Error parsing YAML automation"

Probably an indentation issue when pasting `configuration_additions.yaml`. Validate:

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/configuration.yaml'))"
```

### Telegram callbacks not working

Reload automations after restart:
*HA → Developer Tools → YAML → Reload Automations*

---

## Rollback if needed

```bash
cd /config
tar -xzf /config/backups/permear_v5_backup_YYYYMMDD.tar.gz
# Restart HA
```

---

## Need help?

Open an issue at https://github.com/zzzmada/permear/issues with:
- Output of `cat /config/memory/agent_circuit.json`
- Last 100 lines of `/config/home-assistant.log`
- Which step you got stuck on
