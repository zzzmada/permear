#!/usr/bin/env python3
<<<<<<< HEAD
"""Apply restriction from user rejection to users.json."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR
def main():
    if len(sys.argv) < 2: return
    raw = " ".join(sys.argv[1:])
    try: data = json.loads(raw[raw.index('{'):raw.rindex('}') + 1])
    except (ValueError, json.JSONDecodeError): print("Invalid JSON."); return
    restriction = data.get("new_restriction")
    if not restriction: print("No restriction."); return
    path = os.path.join(MEMORY_DIR, "users.json")
    try:
        with open(path, 'r') as f: users = json.load(f)
    except: print("users.json not found."); return
    target = list(users.keys())[0] if users else None
    if not target: return
    restrictions = users[target].get("restrictions", [])
    if restriction not in restrictions:
        restrictions.append(restriction)
        users[target]["restrictions"] = restrictions[-20:]
        with open(path, 'w') as f: json.dump(users, f, ensure_ascii=False, indent=2)
        print(f"Restriction added: {restriction}")
    else: print("Already exists.")
=======
"""
v7.1-E — Simplified apply_quick_learning.

Receives the restriction as a direct string (ai_task guarantees schema).
No json.loads, no markdown fence strip, no try/except parsing.

Usage: apply_quick_learning.py "restriction string"
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory import load_json, save_json
from permear_config import MEMORY_DIR


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("No clear restriction identified.")
        return

    restriction = sys.argv[1].strip()

    # Values that indicate "no extractable restriction"
    if restriction.lower() in ['null', 'none', 'n/a', '-', '']:
        print("No clear restriction identified.")
        return

    if len(restriction) < 10:
        print(f"Restriction too short to be useful: '{restriction}'")
        return

    users_path = os.path.join(MEMORY_DIR, "users.json")
    users = load_json(users_path)

    # Detect primary user (first key in dict)
    if not users:
        print("No user configured in users.json.")
        return

    user_key = list(users.keys())[0]
    restrictions = users[user_key].get("restrictions", [])

    # Case-insensitive dedup
    existing_lower = [r.lower() for r in restrictions]
    if restriction.lower() in existing_lower:
        print(f"Restriction already registered: '{restriction[:60]}'")
        return

    if len(restrictions) >= 15:
        print(f"15-restriction limit reached for {user_key}. Not added.")
        return

    restrictions.append(restriction)
    users[user_key]["restrictions"] = restrictions
    save_json(users_path, users)

    print(f"Restriction added for {user_key}: '{restriction[:60]}'")


>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
if __name__ == "__main__":
    main()
