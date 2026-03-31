#!/usr/bin/env python3
"""Build the daily briefing prompt for the LLM."""
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

    if daily.get("date") != date_str:
        daily = {"events": [], "interactions": [], "daily_memories": []}

    events_txt = ""
    for e in daily.get("events", []):
        events_txt += f"  {e.get('time','?')} - {e.get('detail','?')}\n"
    if not events_txt:
        events_txt = "  No events recorded today.\n"

    interactions_txt = ""
    for i in daily.get("interactions", []):
        interactions_txt += f"  {i.get('time','?')} ({i.get('channel','?')}): {i.get('summary','?')}\n"
    if not interactions_txt:
        interactions_txt = "  No interactions recorded today.\n"

    memories_txt = ""
    for m in daily.get("daily_memories", []):
        memories_txt += f"  - {m}\n"
    if not memories_txt:
        memories_txt = "  No new memories today.\n"

    patterns_txt = ""
    for p in insights.get("detected_patterns", []):
        patterns_txt += f"  - {p}\n"
    if not patterns_txt:
        patterns_txt = "  No patterns recorded yet.\n"

    pending_txt = ""
    for p in insights.get("pending_items", []):
        pending_txt += f"  - {p}\n"
    if not pending_txt:
        pending_txt = "  No pending items.\n"

    prompt = f"""You are {soul.get('name', 'Assistant')}, a residential assistant.

TASK: Generate the daily briefing for {day_display}, {date_str}.
This text will be sent as a Telegram message.
Format: flowing text, concise, max 200 words. No emojis, no markdown.

TODAY'S EVENTS:
{events_txt}
TODAY'S INTERACTIONS (voice and Telegram):
{interactions_txt}
MEMORIES RECORDED TODAY:
{memories_txt}
LONG-TERM PATTERNS (insights):
{patterns_txt}
OPEN PENDING ITEMS:
{pending_txt}
INSTRUCTIONS:
1. Summarize the day intelligently: what happened, what was different from the usual pattern.
2. Highlight memories recorded today — the user wants to know what the system learned.
3. If there are relevant pending items, mention briefly.
4. If nothing special happened, say so in one sentence and mention something useful.
5. Tone: direct, informative, like a shift report."""

    print(prompt)

if __name__ == "__main__":
    main()
