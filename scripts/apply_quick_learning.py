#!/usr/bin/env python3
"""Apply a restriction learned from user rejection directly to users.json."""
import json, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR

USERS_PATH = os.path.join(MEMORY_DIR, "users.json")

def main():
    if len(sys.argv) < 2:
        return
    raw = " ".join(sys.argv[1:])
    try:
        data = json.loads(raw[raw.index('{'):raw.rindex('}') + 1])
    except (ValueError, json.JSONDecodeError):
        print("Invalid JSON. Discarding.")
        return
    restriction = data.get("new_restriction")
    if not restriction:
        print("No restriction to apply.")
        return
    try:
        with open(USERS_PATH, 'r') as f:
            users = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("users.json not found or invalid.")
        return
    user_keys = list(users.keys())
    if not user_keys:
        return
    target = user_keys[0]
    restrictions = users[target].get("restrictions", [])
    if restriction not in restrictions:
        restrictions.append(restriction)
        users[target]["restrictions"] = restrictions[-20:]
        with open(USERS_PATH, 'w') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        print(f"Restriction added for {target}: {restriction}")
    else:
        print("Restriction already exists.")

if __name__ == "__main__":
    main()
