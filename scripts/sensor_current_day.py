#!/usr/bin/env python3
"""Expose current day's memory file as JSON for HA command_line sensor."""
import json, os
from datetime import datetime

DAILY_DIR = "/config/memory/daily"
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

def main():
    day = DAYS[datetime.now().weekday()]
    path = os.path.join(DAILY_DIR, f"{day}.json")
    today = datetime.now().strftime("%Y-%m-%d")

    empty = {"events": [], "interactions": [], "daily_memories": []}

    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if data.get("date") == today:
                print(json.dumps(data, ensure_ascii=False))
                return
        except (json.JSONDecodeError, KeyError):
            pass

    print(json.dumps(empty))

if __name__ == "__main__":
    main()
