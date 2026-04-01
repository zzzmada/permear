#!/usr/bin/env python3
"""Build the pre-briefing proactive evaluation prompt."""
import json, os, sys
from datetime import datetime

MEMORY_DIR = "/config/memory"
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
    idx = datetime.now().weekday()
    day_name = DAYS[idx]
    timestamp = datetime.now().strftime("%H:%M")

    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    users = load_json(os.path.join(MEMORY_DIR, "users.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))
    daily = load_json(os.path.join(MEMORY_DIR, "daily", f"{day_name}.json"),
                      {"events": [], "interactions": [], "daily_memories": []})

    today = datetime.now().strftime("%Y-%m-%d")
    if daily.get("date") != today:
        daily = {"events": [], "interactions": [], "daily_memories": []}

    house_state = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "State not available."

    events_txt = ""
    for e in daily.get("events", []):
        events_txt += f"  {e.get('time','?')} - {e.get('detail','?')}\n"
    if not events_txt:
        events_txt = "  No events yet.\n"

    interactions_txt = ""
    for i in daily.get("interactions", []):
        interactions_txt += f"  {i.get('time','?')} ({i.get('channel','?')}): {i.get('summary','?')}\n"
    if not interactions_txt:
        interactions_txt = "  No interactions yet.\n"

    patterns_txt = ""
    for p in insights.get("detected_patterns", []):
        patterns_txt += f"  - {p}\n"
    if not patterns_txt:
        patterns_txt = "  No patterns recorded.\n"

    restrictions_all = []
    for user_key, user_data in users.items():
        for r in user_data.get("restrictions", []):
            restrictions_all.append(f"  - [{user_key}] {r}")
    restrictions_txt = "\n".join(restrictions_all) if restrictions_all else "  None."

    prompt = f"""You are {soul.get('name', 'Assistant')}, a residential assistant.

TASK: Evaluate the current house state and decide if anything warrants contacting the user right now ({timestamp}).

CURRENT HOUSE STATE:
{house_state}

TODAY'S EVENTS SO FAR:
{events_txt}
TODAY'S INTERACTIONS:
{interactions_txt}
KNOWN PATTERNS (insights — what you already know is normal):
{patterns_txt}
USER RESTRICTIONS (things they said they do NOT want to be alerted about):
{restrictions_txt}

DECISION RULES:
1. If something RELEVANT that the user probably doesn't know and would benefit from knowing now → write a short message (max 2 sentences). Can be an alert, question, or observation.
2. If NOTHING relevant or the situation is known/expected per patterns → respond EXACTLY: SILENCE
3. NEVER alert about things already in known patterns as normal.
4. NEVER alert about things in user restrictions.
5. Questions are welcome: "The window has been open for 2 hours, should I close it?" or "The AC is off and the room is 29 degrees, should I turn it on?"
6. If you already sent an alert about the same topic today (check interactions), do NOT repeat.
7. Prefer SILENCE when in doubt. Less is more.

RESPOND ONLY: the short message OR the word SILENCE. Nothing else."""

    print(prompt)

if __name__ == "__main__":
    main()
