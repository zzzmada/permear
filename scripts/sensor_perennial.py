#!/usr/bin/env python3
"""Expose perennial memory files as JSON for HA command_line sensor."""
import json, os

MEMORY_DIR = "/config/memory"

def load_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def main():
    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    users = load_json(os.path.join(MEMORY_DIR, "users.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"))

    print(json.dumps({
        "soul": soul,
        "users": users,
        "insights": insights
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
