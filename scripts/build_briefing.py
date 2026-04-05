#!/usr/bin/env python3
"""
Build the daily briefing prompt for the LLM.
v4.0: Compact format, prioritizes pending action approvals.
"""
import json, os
from datetime import datetime

MEMORY_DIR = "/config/memory"
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
DAYS_DISPLAY = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                'Friday', 'Saturday', 'Sunday']

def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def main():
    idx = datetime.now().weekday()
    day_name = DAYS[idx]
    day_display = DAYS_DISPLAY[idx]
    date_str = datetime.now().strftime("%Y-%m-%d")

    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))
    daily = load_json(os.path.join(MEMORY_DIR, "daily", f"{day_name}.json"),
                      {"events": [], "interactions": [], "daily_memories": []})
    allowed_actions = load_json(os.path.join(MEMORY_DIR, "allowed_actions.json"),
                                {"approved": [], "proposed": []})

    if daily.get("date") != date_str:
        daily = {"events": [], "interactions": [], "daily_memories": []}

    # Events — count + last 10 highlights only
    events = daily.get("events", [])
    events_txt = f"  {len(events)} events total."
    if events:
        events_txt += " Highlights:\n"
        for e in events[-10:]:
            events_txt += f"  {e.get('time','?')} - {e.get('detail','?')}\n"

    # Interactions — count only
    interactions = daily.get("interactions", [])
    interactions_txt = f"  {len(interactions)} interactions today."

    # Memories
    memories = daily.get("daily_memories", [])
    memories_txt = ""
    if memories:
        for m in memories:
            memories_txt += f"  - {m}\n"
        memories_txt += "  (Note: these were extracted during earlier pre-briefings today.)\n"
    else:
        memories_txt = "  No memories extracted today.\n"

    # Pending action approvals
    proposed = allowed_actions.get("proposed", [])
    approvals_txt = ""
    if proposed:
        approvals_txt = "PENDING ACTION APPROVALS:\n"
        for i, action in enumerate(proposed, 1):
            approvals_txt += f"  {i}. {action.get('description', 'No description')}\n"
        approvals_txt += "  → Tell the user to reply: approve 1, approve 2, reject 1, etc.\n"

    # Pending items — compact
    pending = insights.get("pending_items", [])
    pending_txt = ""
    if pending:
        pending_txt = "OPEN ITEMS: " + "; ".join(pending) + "\n"

    prompt = f"""You are {soul.get('name', 'Assistant')}, a residential assistant.

TASK: Generate the daily briefing for {day_display}, {date_str}.
Sent as Telegram message. Be CONCISE: max 120 words. No emojis, no markdown.

{approvals_txt}
TODAY: {events_txt}
{interactions_txt}
MEMORIES LEARNED: {memories_txt}
{pending_txt}
STRUCTURE YOUR RESPONSE IN THIS ORDER:
1. FIRST — If there are pending action approvals, present them clearly and ask the user to approve or reject each one by number (e.g., "reply approve 1 or reject 1"). This is the priority.
2. SECOND — One or two sentences about the day: what happened, anything unusual.
3. THIRD — What the system learned today (memories), in one sentence.
4. Skip anything routine or already known from patterns.

Tone: direct, like a brief shift report. If nothing notable happened, say so in one sentence."""

    print(prompt)

if __name__ == "__main__":
    main()
