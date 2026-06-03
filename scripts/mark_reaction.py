#!/usr/bin/env python3
"""SD23-A — Marks reacted=true in DB metadata when the user replies via Telegram."""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import get_recent_emits, update_metadata

REACTION_WINDOW_MIN = 15


def main():
    items = get_recent_emits(minutes=REACTION_WINDOW_MIN)
    marked = 0
    for item in items:
        meta = json.loads(item["metadata"]) if item.get("metadata") else {}
        if meta.get("reacted"):
            continue
        if update_metadata(item["id"], {"reacted": True}):
            marked += 1
    print(f"OK: {marked} alert(s) marked as reacted")


if __name__ == "__main__":
    main()
