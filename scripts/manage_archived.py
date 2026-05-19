#!/usr/bin/env python3
"""
v6.x — Manages errors archived ("silenced 24h") via Telegram button.
State in /config/memory/archived_errors.json. Auto-expires after 24h.
v7.3-B.2 — migrated to locked_update for atomic read-modify-write.

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
from lib.memory import load_json, locked_update
from permear_config import ARCHIVED_ERRORS_PATH

EXPIRATION_HOURS = 24


def _cleanup_inplace(state):
    """Cleanup expired entries from state dict in place. Returns count removed."""
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
    return removed


def cmd_archive(hash_val, component, message_preview):
    now = datetime.now()
    expires = now + timedelta(hours=EXPIRATION_HOURS)

    with locked_update(ARCHIVED_ERRORS_PATH, default={"errors": {}}) as state:
        _cleanup_inplace(state)
        state["errors"][hash_val] = {
            "component": component,
            "message_preview": message_preview[:100],
            "archived_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
    print(f"OK: archived until {expires.strftime('%m/%d %H:%M')}")


def cmd_is_archived(hash_val):
    # Read-only path doesn't need locked_update — just load
    state = load_json(ARCHIVED_ERRORS_PATH, default={"errors": {}})
    # Filter expired in-memory without writing
    now = datetime.now()
    is_present = False
    for h, info in state.get("errors", {}).items():
        if h != hash_val:
            continue
        try:
            if now < datetime.fromisoformat(info["expires_at"]):
                is_present = True
        except (ValueError, KeyError):
            pass
        break
    print("YES" if is_present else "NO")


def cmd_cleanup():
    with locked_update(ARCHIVED_ERRORS_PATH, default={"errors": {}}) as state:
        removed = _cleanup_inplace(state)
    print(f"REMOVED: {removed}")


def cmd_list():
    with locked_update(ARCHIVED_ERRORS_PATH, default={"errors": {}}) as state:
        _cleanup_inplace(state)
        errors = dict(state.get("errors", {}))  # snapshot for printing outside lock

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
