#!/usr/bin/env python3
"""Build the weekly compilation prompt — reads all 7 dailies + guidelines + perennials."""
import json, os
from datetime import datetime

MEMORY_DIR = "/config/memory"
DAILY_DIR = os.path.join(MEMORY_DIR, "daily")
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

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

    week_txt = ""
    for day in DAYS:
        daily = load_json(os.path.join(DAILY_DIR, f"{day}.json"),
                          {"date": "no data", "events": [], "interactions": [], "daily_memories": []})
        week_txt += f"\n=== {day.upper()} ({daily.get('date', '?')}) ===\n"
        week_txt += f"Events: {len(daily.get('events', []))}\n"
        for e in daily.get("events", []):
            week_txt += f"  {e.get('time','?')} - {e.get('detail','?')}\n"
        week_txt += f"Interactions: {len(daily.get('interactions', []))}\n"
        for i in daily.get("interactions", []):
            week_txt += f"  {i.get('time','?')} ({i.get('channel','?')}): {i.get('summary','?')}\n"
        week_txt += f"Daily memories:\n"
        for m in daily.get("daily_memories", []):
            week_txt += f"  - {m}\n"

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

WEEK DATA:
{week_txt}

INSTRUCTIONS:
1. Analyze all 7 days and identify patterns, anomalies, and learnings.
2. Propose edits ONLY following each file's guidelines.
3. Return ONLY valid JSON in the format below. No text before or after.

RESPONSE FORMAT (pure JSON):
{{
  "insights": {{
    "new_patterns": ["pattern 1", "pattern 2"],
    "remove_patterns": ["obsolete pattern"],
    "new_pending": ["new pending item"],
    "remove_pending": ["resolved pending item"],
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
  }}
}}

If no edits for a file, omit the key. If nothing changed, return: {{"no_changes": true}}"""

    print(prompt)

if __name__ == "__main__":
    main()
