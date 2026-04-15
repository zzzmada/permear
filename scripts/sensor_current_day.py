#!/usr/bin/env python3
"""Expose current day's memory as JSON for HA command_line sensor."""
import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import DAILY_DIR, DAYS

def main():
    path = os.path.join(DAILY_DIR, f"{DAYS[datetime.now().weekday()]}.json")
    empty = {"events": [], "interactions": [], "daily_memories": []}
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                print(json.dumps(data, ensure_ascii=False))
                return
        except (json.JSONDecodeError, KeyError):
            pass
    print(json.dumps(empty))

if __name__ == "__main__":
    main()
