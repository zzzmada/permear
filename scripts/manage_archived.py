#!/usr/bin/env python3
"""
v6.x — Manages errors archived ("silenced 24h") via Telegram button.
State in /config/memory/archived_errors.json.
Auto-expires after 24h (cleanup on query).

Commands:
  archive <hash> <component> <message_preview>
  is_archived <hash>      -> prints "YES" or "NO"
  cleanup                 -> removes expired, returns count removed
  list                    -> shows active archived
"""
import sys
import os
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory import load_json, save_json
from permear_config import ARCHIVED_ERRORS_PATH

EXPIRATION_HOURS = 24


def load_state():
    return load_json(ARCHIVED_ERRORS_PATH, default={"errors": {}})


def save_state(state):
    save_json(ARCHIVED_ERRORS_PATH, state)


def cleanup_expired(state):
    now = datetime.now()
    removed = 0
    keep = {}
    for h, info in state.get("errors", {}).items():
        try:
            expires_at = datetime.fromisoformat(info["expires_at"])
            if now < expires_at:
                keep[h] = info
            else:
                removed += 1
        except (ValueError, KeyError):
            removed += 1
    state["errors"] = keep
    return state, removed


def cmd_archive(hash_val, component, message_preview):
    state = load_state()
    state, _ = cleanup_expired(state)
    now = datetime.now()
    expires = now + timedelta(hours=EXPIRATION_HOURS)
    state["errors"][hash_val] = {
        "component": component,
        "message_preview": message_preview[:100],
        "archived_at": now.isoformat(),
        "expires_at": expires.isoformat(),
    }
    save_state(state)
    print(f"OK: archived until {expires.strftime('%m/%d %H:%M')}")


def cmd_is_archived(hash_val):
    state = load_state()
    state, removed = cleanup_expired(state)
    if removed > 0:
        save_state(state)
    print("YES" if hash_val in state.get("errors", {}) else "NO")


def cmd_cleanup():
    state = load_state()
    state, removed = cleanup_expired(state)
    save_state(state)
    print(f"REMOVED: {removed}")


def cmd_list():
    state = load_state()
    state, _ = cleanup_expired(state)
    save_state(state)
    errors = state.get("errors", {})
    if not errors:
        print("No active archived errors.")
        return
    for h, info in errors.items():
        print(f"{h} | {info['component']} | expires {info['expires_at']}")


def main():
    if len(sys.argv) < 2:
        print("Usage: manage_archived.py {archive|is_archived|cleanup|list}")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "archive":
        if len(sys.argv) < 5:
            print("ERROR: archive needs hash, component, message")
            sys.exit(1)
        cmd_archive(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]))
    elif cmd == "is_archived":
        if len(sys.argv) < 3:
            print("NO")
            return
        cmd_is_archived(sys.argv[2])
    elif cmd == "cleanup":
        cmd_cleanup()
    elif cmd == "list":
        cmd_list()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
