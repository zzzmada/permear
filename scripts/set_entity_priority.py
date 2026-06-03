#!/usr/bin/env python3
"""v7.5-C — Writes an entity's priority to monitored_entities.json."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import ENTITIES_PATH
from lib.memory import locked_update


def main():
    if len(sys.argv) < 3:
        print("Usage: set_entity_priority.py <entity_id> <priority 0-2>")
        sys.exit(1)
    entity_id = sys.argv[1]
    try:
        priority = int(sys.argv[2])
    except ValueError:
        print(f"ERR: priority must be an integer (0-2), got: {sys.argv[2]}")
        sys.exit(1)

    with locked_update(ENTITIES_PATH, default={"entities": []}) as data:
        found = False
        for e in data.get("entities", []):
            if e.get("entity_id") == entity_id:
                e["priority"] = priority
                e["priority_source"] = "user"
                found = True
                break
        if not found:
            data.setdefault("entities", []).append({
                "entity_id": entity_id,
                "monitor": True,
                "priority": priority,
                "priority_source": "user",
            })
    print(f"OK: {entity_id} priority={priority}")


if __name__ == "__main__":
    main()
