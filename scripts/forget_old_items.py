#!/usr/bin/env python3
"""
v7.0 — Active forgetting: archives patterns and pending items without mention for 30+ days.
v7.3-B.2 — migrated to locked_update for atomic read-modify-write.
"""
import sys
import os
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory import locked_update, parse_iso
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


def main():
    # v7.3-B.2 — atomic read-modify-write
    archived = []
    found_data = False
    with locked_update(INSIGHTS_PATH) as insights:
        if not insights:
            return
        found_data = True
        insights = ensure_timestamps(insights)
        insights, archived = archive_old_items(insights)

    if not found_data:
        print("insights.json empty or not found.")
        return

    if archived:
        # Append to archive (separate file, separate lock)
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
