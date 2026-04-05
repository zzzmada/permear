#!/usr/bin/env python3
"""
Build the weekly compilation prompt — reads all 7 dailies + guidelines +
perennials + allowed_actions. Includes prompt compaction for large daily files.
"""
import json, os
from datetime import datetime

MEMORY_DIR = "/config/memory"
DAILY_DIR = os.path.join(MEMORY_DIR, "daily")
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

def main():
    guidelines = load_json(os.path.join(MEMORY_DIR, "guidelines.json"))
    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    users = load_json(os.path.join(MEMORY_DIR, "users.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))
    allowed_actions = load_json(os.path.join(MEMORY_DIR, "allowed_actions.json"),
                                {"approved": [], "proposed": []})

    week_txt = ""
    for day in DAYS:
        daily = load_json(os.path.join(DAILY_DIR, f"{day}.json"),
                          {"date": "no data", "events": [], "interactions": [], "daily_memories": []})
        week_txt += f"\n=== {day.upper()} ({daily.get('date', '?')}) ===\n"

        # Compact events if too many
        events = daily.get("events", [])
        if len(events) > MAX_EVENTS_PER_DAY:
            week_txt += f"Events: {len(events)} (showing last {MAX_EVENTS_PER_DAY})\n"
            events = events[-MAX_EVENTS_PER_DAY:]
        else:
            week_txt += f"Events: {len(events)}\n"
        for e in events:
            week_txt += f"  {e.get('time','?')} - {e.get('detail','?')}\n"

        # Compact interactions if too many
        interactions = daily.get("interactions", [])
        if len(interactions) > MAX_INTERACTIONS_PER_DAY:
            week_txt += f"Interactions: {len(interactions)} (showing last {MAX_INTERACTIONS_PER_DAY})\n"
            interactions = interactions[-MAX_INTERACTIONS_PER_DAY:]
        else:
            week_txt += f"Interactions: {len(interactions)}\n"
        for i in interactions:
            week_txt += f"  {i.get('time','?')} ({i.get('channel','?')}): {i.get('summary','?')}\n"

        week_txt += f"Daily memories:\n"
        for m in daily.get("daily_memories", []):
            week_txt += f"  - {m}\n"

    # Allowed actions summary
    actions_txt = ""
    approved = allowed_actions.get("approved", [])
    if approved:
        actions_txt += "CURRENTLY APPROVED ACTIONS:\n"
        for a in approved:
            exec_info = f" (last executed: {a.get('last_executed', 'never')})" if a.get('last_executed') else ""
            actions_txt += f"  - {a.get('id','?')}: {a.get('description','?')}{exec_info}\n"
    else:
        actions_txt += "CURRENTLY APPROVED ACTIONS: None\n"

    prompt = f"""WEEKLY COMPILATION — Analyze the week and propose edits to perennial files.

GUIDELINES (IMMUTABLE — follow strictly):
{json.dumps(guidelines, ensure_ascii=False, indent=2)}

CURRENT STATE OF PERENNIAL FILES:

--- insights.json ---
{json.dumps(insights, ensure_ascii=False, indent=2)}

--- soul.json ---
{json.dumps(soul, ensure_ascii=False, indent=2)}

--- users.json ---
{json.dumps(users, ensure_ascii=False, indent=2)}

{actions_txt}

WEEK DATA:
{week_txt}

INSTRUCTIONS:
1. Analyze all 7 days and identify patterns, anomalies, and learnings.
2. Propose edits ONLY following each file's guidelines.
3. Based on observed patterns, you may propose NEW allowed actions the agent could execute autonomously. These go in "proposed_actions" — they will NOT be active until the user approves them.
4. Keep your response concise. Return ONLY valid JSON. No text before or after.

RESPONSE FORMAT (pure JSON):
{{
  "insights": {{
    "new_patterns": ["pattern 1"],
    "remove_patterns": ["obsolete pattern"],
    "new_pending": ["pending item"],
    "remove_pending": ["resolved item"],
    "new_suggestions": ["automation suggestion"]
  }},
  "soul": {{
    "behavior_rules": {{
      "add": ["new rule"],
      "remove": ["obsolete rule"]
    }}
  }},
  "users": {{
    "user_1": {{
      "observed_patterns": {{
        "add": ["new pattern"],
        "remove": ["outdated pattern"]
      }}
    }}
  }},
  "proposed_actions": [
    {{
      "id": "short_snake_case_id",
      "description": "Human-readable description of when and what the action does",
      "conditions": [
        {{"entity": "sensor.example", "operator": ">=", "value": 70}},
        {{"type": "time_after", "value": "18:00"}},
        {{"type": "time_before", "value": "23:00"}}
      ],
      "action": {{
        "service": "climate.set_temperature",
        "data": {{"entity_id": "climate.example", "temperature": 24, "hvac_mode": "cool"}}
      }},
      "notification": "Description of what was done — use {{trigger_value}} for the sensor value that triggered it.",
      "cooldown_minutes": 120
    }}
  ]
}}

If no edits for a section, omit the key. If nothing changed, return: {{"no_changes": true}}"""

    print(prompt)

if __name__ == "__main__":
    main()
