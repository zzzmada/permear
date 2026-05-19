#!/usr/bin/env python3
"""v7.1-G — Receives JSON array of memories from ai_task and saves to today's daily file.
v7.3-B.2 — migrated to locked_update for atomic read-modify-write."""
import json, sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import DAILY_DIR, DAYS
from lib.memory import locked_update

MAX_MEMORIES = 15


def main():
    if len(sys.argv) < 2:
        print("Usage: apply_daily_memory.py '<json_array>'")
        sys.exit(1)

    raw = sys.argv[1].strip()
    try:
        new_items = json.loads(raw)
        if not isinstance(new_items, list):
            raise ValueError("expected JSON array")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Invalid JSON: {e}. Discarding.")
        sys.exit(0)

    if not new_items:
        print("Empty list - nothing to save.")
        sys.exit(0)

    day = DAYS[datetime.now().weekday()]
    path = os.path.join(DAILY_DIR, f"{day}.json")
    today = datetime.now().strftime("%Y-%m-%d")

    if not os.path.exists(path):
        print(f"File {day}.json does not exist. Aborting.")
        sys.exit(1)

    # v7.3-B.2 — atomic read-modify-write
    added_count = 0
    with locked_update(path) as daily:
        if daily.get("date") != today:
            print(f"File is from another week ({daily.get('date')}). Aborting.")
            sys.exit(1)

        existing = daily.get("daily_memories", [])
        for m in new_items:
            m = str(m).strip()
            if m and m not in existing:
                existing.append(m)
                added_count += 1

        daily["daily_memories"] = existing[:MAX_MEMORIES]

    print(f"OK: +{added_count} memory(ies) saved to {day}.json")


if __name__ == "__main__":
    main()
