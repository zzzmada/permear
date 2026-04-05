#!/usr/bin/env python3
"""
Process action approval/rejection via Telegram commands.
Usage: process_action_approval.py "approve 1" or "reject 2"
Numbers reference the position in the 'proposed' array (1-indexed).
"""
import json, sys, os
from datetime import datetime

ACTIONS_PATH = "/config/memory/allowed_actions.json"

def main():
    if len(sys.argv) < 2:
        print("Usage: process_action_approval.py 'approve 1' or 'reject 2'")
        return

    command = " ".join(sys.argv[1:]).strip().lower()

    # Parse command
    parts = command.split()
    if len(parts) < 2:
        print("INVALID: Expected 'approve N' or 'reject N'")
        return

    action_type = parts[0]
    if action_type not in ["approve", "reject"]:
        print(f"INVALID: Unknown command '{action_type}'. Use 'approve' or 'reject'.")
        return

    try:
        index = int(parts[1]) - 1  # Convert to 0-indexed
    except ValueError:
        print(f"INVALID: '{parts[1]}' is not a number.")
        return

    # Load actions file
    try:
        with open(ACTIONS_PATH, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: Cannot read {ACTIONS_PATH}: {e}")
        return

    proposed = data.get("proposed", [])

    if index < 0 or index >= len(proposed):
        print(f"INVALID: No proposed action at position {index + 1}. There are {len(proposed)} pending.")
        return

    action = proposed[index]
    action_id = action.get("id", "unknown")
    action_desc = action.get("description", "no description")

    if action_type == "approve":
        # Move from proposed to approved
        proposed.pop(index)
        action["last_executed"] = None
        data.setdefault("approved", []).append(action)
        data["proposed"] = proposed

        with open(ACTIONS_PATH, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(json.dumps({
            "result": "approved",
            "id": action_id,
            "message": f"Action approved: {action_desc}"
        }))

    elif action_type == "reject":
        # Remove from proposed
        proposed.pop(index)
        data["proposed"] = proposed

        with open(ACTIONS_PATH, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(json.dumps({
            "result": "rejected",
            "id": action_id,
            "message": f"Action rejected and removed: {action_desc}"
        }))

if __name__ == "__main__":
    main()
