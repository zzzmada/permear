#!/usr/bin/env python3
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
if __name__ == "__main__":
    main()
