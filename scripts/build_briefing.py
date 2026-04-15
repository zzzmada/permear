#!/usr/bin/env python3
"""Build the daily briefing prompt (21h). Compact, includes updates and agent automations."""
import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR, AGENT_YAML, DAYS, DAYS_DISPLAY

def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

def count_agent_automations():
    try:
        import yaml
        with open(AGENT_YAML, 'r') as f:
            data = yaml.safe_load(f)
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0

def main():
    updates_txt = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--updates" and i + 1 < len(sys.argv):
            updates_txt = sys.argv[i + 1]

    idx = datetime.now().weekday()
    day_display = DAYS_DISPLAY[idx]
    date_str = datetime.now().strftime("%Y-%m-%d")

    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))
    daily = load_json(os.path.join(MEMORY_DIR, "daily", f"{DAYS[idx]}.json"),
                      {"events": [], "interactions": [], "daily_memories": []})

    if daily.get("date") != date_str:
        daily = {"events": [], "interactions": [], "daily_memories": []}

    events = daily.get("events", [])
    interactions = daily.get("interactions", [])
    memories = daily.get("daily_memories", [])

    events_txt = f"{len(events)} events"
    if events:
        events_txt += ": " + ", ".join(f"{e.get('time','?')}-{e.get('detail','?')}" for e in events[-10:])

    memories_txt = ""
    if memories:
        memories_txt = "Memories learned today: " + "; ".join(memories[:10])
        memories_txt += "\n(Note: extracted during earlier pre-briefings. More will be extracted after this briefing.)"

    pending = insights.get("pending_items", [])
    pending_txt = "Open items: " + "; ".join(pending) if pending else ""
    auto_count = count_agent_automations()
    auto_txt = f"Agent automations: {auto_count} active." if auto_count > 0 else ""
    updates_section = f"HA UPDATES:\n{updates_txt}" if updates_txt and "up to date" not in updates_txt.lower() else ""

    prompt = f"""You are {soul.get('name', 'Assistant')}, a residential assistant and system caretaker.

TASK: Daily briefing for {day_display}, {date_str}. Telegram message. Max 120 words. No emojis, no markdown.

TODAY: {events_txt}
Interactions: {len(interactions)}
{memories_txt}
{pending_txt}
{auto_txt}
{updates_section}

STRUCTURE:
1. One or two sentences about the day — what happened, anything unusual.
2. What the system learned today (memories), in one sentence.
3. If there are HA updates available, mention them.
4. Skip anything routine.
Tone: direct, like a brief shift report."""
    print(prompt)

if __name__ == "__main__":
    main()
