#!/usr/bin/env python3
"""
Build the weekly compilation prompt.
v5.0: Reviews agent automations, prompt compaction, no allowed_actions.
"""
import json, os
from datetime import datetime

MEMORY_DIR = "/config/memory"
DAILY_DIR = os.path.join(MEMORY_DIR, "daily")
AGENT_YAML = "/config/automations/agent_automations.yaml"
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

MAX_EVENTS_PER_DAY = 20
MAX_INTERACTIONS_PER_DAY = 10

def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def load_agent_automations():
    try:
        import yaml
        with open(AGENT_YAML, 'r') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def main():
    guidelines = load_json(os.path.join(MEMORY_DIR, "guidelines.json"))
    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    users = load_json(os.path.join(MEMORY_DIR, "users.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))

    # Week data (compacted)
    week_txt = ""
    for day in DAYS:
        daily = load_json(os.path.join(DAILY_DIR, f"{day}.json"),
                          {"date": "no data", "events": [], "interactions": [], "daily_memories": []})
        week_txt += f"\n=== {day.upper()} ({daily.get('date', '?')}) ===\n"

        events = daily.get("events", [])
        if len(events) > MAX_EVENTS_PER_DAY:
            week_txt += f"Events: {len(events)} (last {MAX_EVENTS_PER_DAY} shown)\n"
            events = events[-MAX_EVENTS_PER_DAY:]
        else:
            week_txt += f"Events: {len(events)}\n"
        for e in events:
            week_txt += f"  {e.get('time','?')} {e.get('detail','?')}\n"

        interactions = daily.get("interactions", [])
        if len(interactions) > MAX_INTERACTIONS_PER_DAY:
            week_txt += f"Interactions: {len(interactions)} (last {MAX_INTERACTIONS_PER_DAY} shown)\n"
            interactions = interactions[-MAX_INTERACTIONS_PER_DAY:]
        else:
            week_txt += f"Interactions: {len(interactions)}\n"
        for i in interactions:
            week_txt += f"  {i.get('time','?')} ({i.get('channel','?')}): {i.get('summary','?')}\n"

        memories = daily.get("daily_memories", [])
        if memories:
            week_txt += "Memories: " + "; ".join(memories) + "\n"

    # Agent automations
    agent_autos = load_agent_automations()
    autos_txt = "AGENT AUTOMATIONS (review — propose removing unused ones):\n"
    if agent_autos:
        for a in agent_autos:
            autos_txt += f"  - {a.get('alias','?')} (id: {a.get('id','?')})\n"
    else:
        autos_txt += "  None currently active.\n"

    prompt = f"""WEEKLY COMPILATION — Analyze the week and propose edits to perennial files.

GUIDELINES (IMMUTABLE):
{json.dumps(guidelines, ensure_ascii=False, indent=2)}

CURRENT PERENNIAL FILES:
--- insights.json ---
{json.dumps(insights, ensure_ascii=False, indent=2)}

--- soul.json ---
{json.dumps(soul, ensure_ascii=False, indent=2)}

--- users.json ---
{json.dumps(users, ensure_ascii=False, indent=2)}

{autos_txt}

WEEK DATA:
{week_txt}

INSTRUCTIONS:
1. Analyze all 7 days. Identify patterns, anomalies, learnings.
2. Propose edits following each file's guidelines.
3. Review agent automations — propose removing obsolete ones.
4. You may suggest new automations based on observed patterns.
5. Return ONLY valid JSON. No text before or after.

RESPONSE FORMAT:
{{
  "insights": {{
    "new_patterns": [], "remove_patterns": [],
    "new_pending": [], "remove_pending": [],
    "new_suggestions": []
  }},
  "soul": {{
    "behavior_rules": {{"add": [], "remove": []}}
  }},
  "users": {{
    "user_key": {{
      "field_name": {{"add": [], "remove": []}}
    }}
  }},
  "automation_suggestions": [
    {{"alias": "name", "description": "what it does and when", "trigger_type": "numeric_state|state|time", "entity": "sensor.x"}}
  ],
  "automations_to_remove": ["alias_or_id"]
}}

Omit empty sections. If nothing changed: {{"no_changes": true}}"""

    print(prompt)

if __name__ == "__main__":
    main()
