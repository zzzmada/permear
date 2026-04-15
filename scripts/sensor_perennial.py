#!/usr/bin/env python3
"""Expose perennial memory files as JSON for HA command_line sensor."""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR

def load(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def main():
    print(json.dumps({
        "soul": load(os.path.join(MEMORY_DIR, "soul.json")),
        "users": load(os.path.join(MEMORY_DIR, "users.json")),
        "insights": load(os.path.join(MEMORY_DIR, "insights.json"))
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
