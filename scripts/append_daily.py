#!/usr/bin/env python3
"""Append event or interaction to the daily file.
v7.3-B.2 — migrated to locked_update for atomic read-modify-write."""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import locked_update


def get_daily_path():
    day = DAYS[datetime.now().weekday()]
    return os.path.join(DAILY_DIR, f"{day}.json")


def new_daily(date_str):
    return {
        "date": date_str,
        "events": [],
        "interactions": [],
        "daily_memories": [],
        "bulletin_triggered": False,
        "briefing_sent": False
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: append_daily.py <type> <detail>")
        print("  type: event | interaction | memory | flag")
        print("  detail: descriptive text")
        return

    kind = sys.argv[1]
    detail = " ".join(sys.argv[2:])
    time_str = datetime.now().strftime("%H:%M")
    today = datetime.now().strftime("%Y-%m-%d")
    path = get_daily_path()

    # v7.3-B.2 — atomic read-modify-write via locked_update
    with locked_update(path, default=new_daily(today)) as daily:
        # Reset if loaded file is from another day (weekly recycle)
        if daily.get("date") != today:
            daily.clear()
            daily.update(new_daily(today))

        if kind == "event":
            existing = [e for e in daily["events"] if e["time"] == time_str and e["detail"] == detail]
            if not existing:
                daily["events"].append({"time": time_str, "type": "auto", "detail": detail})

        elif kind == "interaction":
            parts = detail.split(":", 1)
            channel = parts[0] if len(parts) > 1 else "unknown"
            summary = parts[1] if len(parts) > 1 else detail
            daily["interactions"].append({"time": time_str, "channel": channel, "summary": summary.strip()})

        elif kind == "memory":
            if detail not in daily["daily_memories"]:
                daily["daily_memories"].append(detail)

        elif kind == "flag":
            if detail in daily:
                daily[detail] = True

    print(f"OK: {kind} recorded at {time_str}")


if __name__ == "__main__":
    main()
