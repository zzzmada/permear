#!/usr/bin/env python3
"""Append event or interaction to the daily file."""
import sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
<<<<<<< HEAD
from permear_config import DAILY_DIR, DAYS

def get_daily_path():
    return os.path.join(DAILY_DIR, f"{DAYS[datetime.now().weekday()]}.json")
def load_daily():
    path = get_daily_path()
    today = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(path):
        with open(path, 'r') as f:
            data = json.load(f)
        if data.get("date") != today:
            return {"date": today, "events": [], "interactions": [], "daily_memories": [], "briefing_sent": False}
        return data
    return {"date": today, "events": [], "interactions": [], "daily_memories": [], "briefing_sent": False}
def save_daily(data):
    os.makedirs(DAILY_DIR, exist_ok=True)
    with open(get_daily_path(), 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
def main():
    if len(sys.argv) < 3: return
    entry_type, detail = sys.argv[1], " ".join(sys.argv[2:])
    timestamp = datetime.now().strftime("%H:%M")
    daily = load_daily()
    if entry_type == "event":
        if not any(e["time"] == timestamp and e["detail"] == detail for e in daily["events"]):
            daily["events"].append({"time": timestamp, "type": "auto", "detail": detail})
    elif entry_type == "interaction":
        parts = detail.split(":", 1)
        channel = parts[0] if len(parts) > 1 else "unknown"
        summary = parts[1].strip() if len(parts) > 1 else detail
        daily["interactions"].append({"time": timestamp, "channel": channel, "summary": summary})
    elif entry_type == "memory":
        if detail not in daily["daily_memories"]:
            daily["daily_memories"].append(detail)
    elif entry_type == "flag":
        if detail in daily: daily[detail] = True
    save_daily(daily)
    print(f"OK: {entry_type} logged at {timestamp}")
=======
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


>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
if __name__ == "__main__":
    main()
