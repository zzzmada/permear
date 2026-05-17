#!/usr/bin/env python3
"""
v7.0 — Active forgetting: archives patterns and pending items without mention for 30+ days.

State in insights.json (new field):
  "_timestamps": {
    "detected_patterns": {"<text>": "<iso datetime last_seen>"},
    "pending":           {"<text>": "<iso datetime last_seen>"}
  }

Output file: insights_archived.json
  {"items": [{"type": ..., "text": ..., "last_seen": ..., "archived_at": ...}]}
"""
import sys
import os
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory import load_json, save_json, parse_iso
from permear_config import MEMORY_DIR, INSIGHTS_ARCHIVED_PATH

INSIGHTS_PATH = os.path.join(MEMORY_DIR, "insights.json")
RETENTION_DAYS = 30


def ensure_timestamps(insights):
    """Ensure _timestamps for all current items (first run: now)."""
    if "_timestamps" not in insights:
        insights["_timestamps"] = {}

    now = datetime.now().isoformat()

    for field in ["detected_patterns", "pending"]:
        if field not in insights["_timestamps"]:
            insights["_timestamps"][field] = {}

        for item in insights.get(field, []):
            if item not in insights["_timestamps"][field]:
                insights["_timestamps"][field][item] = now

    return insights


def archive_old_items(insights):
    """Move items with last_seen > RETENTION_DAYS to archived list."""
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    archived_items = []

    for field in ["detected_patterns", "pending"]:
        items = insights.get(field, [])
        timestamps = insights.get("_timestamps", {}).get(field, {})

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

        insights[field] = kept

    return insights, archived_items


def append_to_archive(items):
    archive = load_json(INSIGHTS_ARCHIVED_PATH, default={"items": []})
    archive["items"].extend(items)
    archive["last_run"] = datetime.now().isoformat()
    save_json(INSIGHTS_ARCHIVED_PATH, archive)


def main():
    insights = load_json(INSIGHTS_PATH)
    if not insights:
        print("insights.json empty or not found.")
        return

    insights = ensure_timestamps(insights)
    insights, archived = archive_old_items(insights)

    save_json(INSIGHTS_PATH, insights)

    if archived:
        append_to_archive(archived)
        print(f"Archived {len(archived)} old item(s):")
        for a in archived:
            print(f"  [{a['type']}] {a['text'][:80]}")
    else:
        print("No old items to archive.")


if __name__ == "__main__":
    main()
