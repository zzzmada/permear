#!/usr/bin/env python3
"""
v7.0 — Active forgetting: archives pending and suggestions not mentioned in 30+ days.
v8-S1: migrated from insights.json to guidelines.json (action_items).

State in guidelines.json (action_items._timestamps):
  "_timestamps": {
    "pending":     {"<text>": "<iso datetime last_seen>"},
    "suggestions": {"<text>": "<iso datetime last_seen>"}
  }

Output file: insights_archived.json
  {"items": [{"type": ..., "text": ..., "last_seen": ..., "archived_at": ...}]}
"""
import sys
import os
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory import load_json, save_json, parse_iso, locked_update
from permear_config import MEMORY_DIR, INSIGHTS_ARCHIVED_PATH, GUIDELINES_PATH

RETENTION_DAYS = 30


def ensure_timestamps(guidelines):
    """Ensure _timestamps inside action_items for all current items."""
    action = guidelines.setdefault("action_items", {})
    ts = action.setdefault("_timestamps", {})
    now = datetime.now().isoformat()
    for field in ["pending", "suggestions"]:
        ts.setdefault(field, {})
        for item in action.get(field, []):
            if item not in ts[field]:
                ts[field][item] = now
    return guidelines


def archive_old_items(guidelines):
    """Move items with last_seen > RETENTION_DAYS to the archived list."""
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    archived_items = []
    action = guidelines.get("action_items", {})
    ts = action.get("_timestamps", {})

    for field in ["pending", "suggestions"]:
        items = action.get(field, [])
        timestamps = ts.get(field, {})

        kept = []
        for item in items:
            last_seen_str = timestamps.get(item)
            if not last_seen_str:
                kept.append(item)
                continue

            last_seen = parse_iso(last_seen_str)
            if last_seen and last_seen < cutoff:
                archived_items.append({
                    "type": field,
                    "text": item,
                    "last_seen": last_seen_str,
                    "archived_at": datetime.now().isoformat(),
                })
                timestamps.pop(item, None)
            else:
                kept.append(item)

        action[field] = kept

    return guidelines, archived_items


def main():
    guidelines_pre = load_json(GUIDELINES_PATH)
    if not guidelines_pre:
        print("guidelines.json empty or not found.")
        return

    # v7.3-B.2 — locked_update for guidelines (lock 1)
    archived = []
    with locked_update(GUIDELINES_PATH) as guidelines:
        ensure_timestamps(guidelines)
        guidelines, archived = archive_old_items(guidelines)

    if archived:
        # locked_update for archive (lock 2 — different file, no deadlock)
        with locked_update(INSIGHTS_ARCHIVED_PATH, default={"items": []}) as archive:
            archive["items"].extend(archived)
            archive["last_run"] = datetime.now().isoformat()

        print(f"Archived {len(archived)} old item(s):")
        for a in archived:
            print(f"  [{a['type']}] {a['text'][:80]}")
    else:
        print("No old items to archive.")


if __name__ == "__main__":
    main()
