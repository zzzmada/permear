#!/usr/bin/env python3
"""Append events, interactions, or memories to the current day's file."""
import json, sys, os
from datetime import datetime

DAILY_DIR = "/config/memory/daily"
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

def get_daily_path():
    day = DAYS[datetime.now().weekday()]
    return os.path.join(DAILY_DIR, f"{day}.json")

def load_daily():
    path = get_daily_path()
    today = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(path):
        with open(path, 'r') as f:
            data = json.load(f)
        if data.get("date") != today:
            return new_daily(today)
        return data
    return new_daily(today)

def new_daily(date_str):
    return {
        "date": date_str,
        "events": [],
        "interactions": [],
        "daily_memories": [],
        "briefing_sent": False
    }

def save_daily(data):
    path = get_daily_path()
    os.makedirs(DAILY_DIR, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    if len(sys.argv) < 3:
        print("Usage: append_daily.py <type> <detail>")
        print("  type: event | interaction | memory | flag")
        return

    entry_type = sys.argv[1]
    detail = " ".join(sys.argv[2:])
    timestamp = datetime.now().strftime("%H:%M")

    daily = load_daily()

    if entry_type == "event":
        existing = [e for e in daily["events"]
                    if e["time"] == timestamp and e["detail"] == detail]
        if not existing:
            daily["events"].append({
                "time": timestamp, "type": "auto", "detail": detail
            })

    elif entry_type == "interaction":
        # detail format: "channel:summary" e.g. "telegram:Asked about temperature"
        parts = detail.split(":", 1)
        channel = parts[0] if len(parts) > 1 else "unknown"
        summary = parts[1] if len(parts) > 1 else detail
        daily["interactions"].append({
            "time": timestamp, "channel": channel, "summary": summary.strip()
        })

    elif entry_type == "memory":
        if detail not in daily["daily_memories"]:
            daily["daily_memories"].append(detail)

    elif entry_type == "flag":
        if detail in daily:
            daily[detail] = True

    save_daily(daily)
    print(f"OK: {entry_type} logged at {timestamp}")

if __name__ == "__main__":
    main()
