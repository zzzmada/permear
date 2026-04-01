#!/usr/bin/env python3
"""Receive memory suggestions from the LLM and save to today's daily file."""
import json, sys, os
from datetime import datetime

DAILY_DIR = "/config/memory/daily"
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

def main():
    if len(sys.argv) < 2:
        print("Usage: update_daily_memory.py '<json_from_llm>'")
        return

    raw = " ".join(sys.argv[1:])

    try:
        start = raw.index('{')
        end = raw.rindex('}') + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        print("Invalid JSON received. Discarding.")
        return

    day = DAYS[datetime.now().weekday()]
    path = os.path.join(DAILY_DIR, f"{day}.json")
    today = datetime.now().strftime("%Y-%m-%d")

    if os.path.exists(path):
        with open(path, 'r') as f:
            daily = json.load(f)
        if daily.get("date") != today:
            print("File is from a different week. Aborting.")
            return
    else:
        print("Daily file does not exist. Aborting.")
        return

    new_memories = data.get("daily_memories", [])
    for m in new_memories:
        if m not in daily["daily_memories"]:
            daily["daily_memories"].append(m)

    daily["daily_memories"] = daily["daily_memories"][:20]

    with open(path, 'w') as f:
        json.dump(daily, f, ensure_ascii=False, indent=2)

    print(f"OK: +{len(new_memories)} memories saved to {day}.json")

if __name__ == "__main__":
    main()
