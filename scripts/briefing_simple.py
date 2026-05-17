#!/usr/bin/env python3
"""
v6.x — Python fallback briefing for when LLM agent fails 3 retries.
Generates a minimal text-only summary from the daily file.
"""
import os
import sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import DAYS, DAYS_DISPLAY, DAILY_DIR
from lib.memory import load_json


def main():
    idx = datetime.now().weekday()
    day_key = DAYS[idx]
    day_display = DAYS_DISPLAY[idx]
    date_str = datetime.now().strftime("%Y-%m-%d")

    path = os.path.join(DAILY_DIR, f"{day_key}.json")
    daily = load_json(path, {"events": [], "interactions": [], "daily_memories": []})

    if daily.get("date") != date_str:
        print(f"Briefing for {day_display}, {date_str}: agent unavailable. No data for today yet.")
        return

    events = daily.get("events", [])
    interactions = daily.get("interactions", [])
    memories = daily.get("daily_memories", [])

    lines = [f"Briefing for {day_display}, {date_str} (fallback - agent unavailable)."]
    lines.append(f"Events: {len(events)}.")
    lines.append(f"Interactions: {len(interactions)}.")
    if memories:
        lines.append("Memories: " + "; ".join(memories[:3]))
    else:
        lines.append("Memories: none.")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
