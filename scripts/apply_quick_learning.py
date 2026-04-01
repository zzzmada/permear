#!/usr/bin/env python3
"""
Apply a restriction learned from user rejection directly to users.json.
Called when the user responds to a pre-briefing alert with rejection keywords.
"""
import json, sys, os

USERS_PATH = "/config/memory/users.json"

def main():
    if len(sys.argv) < 2:
        return

    raw = " ".join(sys.argv[1:])

    try:
        start = raw.index('{')
        end = raw.rindex('}') + 1
        data = json.loads(raw[start:end])
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
        print("No users found in users.json.")
        return

    target_user = user_keys[0]
    restrictions = users[target_user].get("restrictions", [])

    if restriction not in restrictions:
        restrictions.append(restriction)
        users[target_user]["restrictions"] = restrictions[-20:]

        with open(USERS_PATH, 'w') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

        print(f"Restriction added for {target_user}: {restriction}")
    else:
        print("Restriction already exists.")

if __name__ == "__main__":
    main()
