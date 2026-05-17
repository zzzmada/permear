#!/usr/bin/env python3
"""HA command_line sensor: perennial memory files."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR
def load(p):
    try:
        with open(p, 'r') as f: return json.load(f)
    except: return {}
def main():
    print(json.dumps({"soul": load(os.path.join(MEMORY_DIR, "soul.json")),
                       "users": load(os.path.join(MEMORY_DIR, "users.json")),
                       "insights": load(os.path.join(MEMORY_DIR, "insights.json"))}, ensure_ascii=False))
if __name__ == "__main__":
    main()
