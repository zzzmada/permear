#!/usr/bin/env python3
"""Append event or interaction to the daily file."""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_json, save_json


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


def load_daily():
    path = get_daily_path()
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_json(path, new_daily(today))
    if data.get("date") != today:
        return new_daily(today)
    return data


def save_daily(data):
    save_json(get_daily_path(), data)


def main():
    if len(sys.argv) < 3:
        print("Usage: append_daily.py <type> <detail>")
        print("  type: event | interaction | memory | flag")
        print("  detail: descriptive text")
        return

    kind = sys.argv[1]
    detail = " ".join(sys.argv[2:])
    time_str = datetime.now().strftime("%H:%M")

    daily = load_daily()

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

    save_daily(daily)
    print(f"OK: {kind} recorded at {time_str}")


if __name__ == "__main__":
    main()
