# Migration Guide — PERMEAR v5.x → v7.2

Upgrade from the old single-agent architecture to the new dual-path system with fallback, health monitoring, and active forgetting.

Estimated time: ~10–15 minutes.

---

## Main changes in v7.2

* Dual LLM architecture:

  * `conversation` → interactive chat/voice
  * `ai_task` → structured non-interactive tasks
* Automatic provider fallback
* Shared `lib/` modules
* Active forgetting / archive system
* Real-time error monitoring improvements
* English-standardized public repository structure

---

## 1. Backup your current installation

```bash
cd /config

tar -czf permear_backup_$(date +%Y%m%d).tar.gz \
scripts/ memory/ automations/permear.yaml \
configuration.yaml secrets.yaml
```

---

## 2. Download the new version

```bash
cd /tmp
git clone https://github.com/zzzmada/permear.git permear_v72
```

---

## 3. Replace files

### Scripts

```bash
rm -rf /config/scripts
cp -r /tmp/permear_v72/scripts /config/
chmod +x /config/scripts/*.py
```

### Automations

```bash
cp /tmp/permear_v72/automations/permear.yaml \
/config/automations/permear.yaml
```

### Memory templates and new files

```bash
cp /tmp/permear_v72/memory/guidelines.json /config/memory/
chmod 444 /config/memory/guidelines.json

cp /tmp/permear_v72/memory/*.example.json /config/memory/ 2>/dev/null || true
```

### Configuration additions

Merge the contents of:

```text
configuration_additions.yaml
```

into your:

```text
/config/configuration.yaml
```

---

## 4. Configure AI Task entities

v7.2 requires two AI Task entities:

| Purpose  | Suggested provider    |
| -------- | --------------------- |
| Primary  | OpenRouter + DeepSeek |
| Fallback | Gemini                |

Edit:

```text
/config/scripts/permear_config.py
```

Example:

```python
AI_TASK_PRIMARY = "ai_task.openrouter_deepseek_v3"
AI_TASK_SECONDARY = "ai_task.google_ai_task"
```

---

## 5. Update secrets.yaml

Add:

```yaml
permear_chat_id: YOUR_CHAT_ID
permear_agent_id: conversation.google_ai_conversation
permear_person_entity: person.your_name
```

---

## 6. Validate installation

### Validate Python

```bash
python3 -m compileall /config/scripts
```

### Validate YAML

```bash
python3 -c "import yaml; yaml.safe_load(open('/config/automations/permear.yaml'))"
```

### Validate JSON

```bash
for f in /config/memory/*.json; do
python3 -c "import json; json.load(open('$f'))"
done
```

---

## 7. Restart Home Assistant

After restart:

* Reload automations
* Reload command-line sensors

---

## 8. Quick test

### Telegram

Send:

```text
hi
```

to your bot.

### Health sensor

Check:

```text
sensor.permear_health
```

Expected state:

```text
all_ok
```

### Pre-briefing

Trigger manually:

```yaml
service: automation.trigger
target:
  entity_id: automation.permear_prebriefing
data:
  skip_condition: true
```

---

## Common issues

### `fallback_active`

Primary provider failed or hit rate limit.

Usually solved automatically by the secondary provider.

---

### Telegram not responding

Check:

* Telegram bot token
* `permear_chat_id`
* Home Assistant logs

---

### `sensor.permear_health unavailable`

Create empty circuit file:

```bash
echo '{"daily_stats": {}}' > /config/memory/agent_circuit.json
```

---

## Rollback

```bash
cd /config
tar -xzf permear_backup_YYYYMMDD.tar.gz
```

Restart Home Assistant afterward.

---

For additional setup details, see the main README.
