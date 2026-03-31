#!/usr/bin/env python3
"""
Weekly compilation. Receives JSON from the LLM with proposed edits
to perennial files. Applies them respecting guidelines.
Creates backups before any edit.
"""
import json, sys, os, shutil
from datetime import datetime

MEMORY_DIR = "/config/memory"

def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def backup_file(path):
    if os.path.exists(path):
        backup = path + f".bak.{datetime.now().strftime('%Y%m%d')}"
        shutil.copy2(path, backup)

def apply_insights(current, edits, guidelines):
    max_patterns = 30

    for p in edits.get("new_patterns", []):
        if p not in current.get("detected_patterns", []):
            current.setdefault("detected_patterns", []).append(p)
    current["detected_patterns"] = current.get("detected_patterns", [])[-max_patterns:]

    for p in edits.get("remove_patterns", []):
        if p in current.get("detected_patterns", []):
            current["detected_patterns"].remove(p)

    for p in edits.get("new_pending", []):
        if p not in current.get("pending_items", []):
            current.setdefault("pending_items", []).append(p)
    for p in edits.get("remove_pending", []):
        if p in current.get("pending_items", []):
            current["pending_items"].remove(p)
    current["pending_items"] = current.get("pending_items", [])[:20]

    for s in edits.get("new_suggestions", []):
        if s not in current.get("automation_suggestions", []):
            current.setdefault("automation_suggestions", []).append(s)
    current["automation_suggestions"] = current.get("automation_suggestions", [])[:10]

    current["last_compilation"] = datetime.now().isoformat()
    return current

def apply_soul(current, edits, guidelines):
    protected = ["name", "mission", "values"]

    for field in edits:
        if field in protected:
            continue
        if field == "behavior_rules":
            rules = edits[field]
            if isinstance(rules, dict):
                for r in rules.get("add", []):
                    if r not in current.get("behavior_rules", []):
                        current.setdefault("behavior_rules", []).append(r)
                for r in rules.get("remove", []):
                    if r in current.get("behavior_rules", []):
                        current["behavior_rules"].remove(r)
            current["behavior_rules"] = current.get("behavior_rules", [])[:15]
        elif field == "tone":
            current["tone"] = edits["tone"]

    return current

def apply_users(current, edits, guidelines):
    for user_key, user_edits in edits.items():
        if user_key not in current:
            if "role" in user_edits:
                current[user_key] = user_edits
            continue

        for field, value in user_edits.items():
            if field == "observed_patterns" and isinstance(value, dict):
                obs = current[user_key].get("observed_patterns", [])
                for p in value.get("add", []):
                    if p not in obs:
                        obs.append(p)
                for p in value.get("remove", []):
                    if p in obs:
                        obs.remove(p)
                current[user_key]["observed_patterns"] = obs[-15:]
            else:
                current[user_key][field] = value

    return current

def main():
    if len(sys.argv) < 2:
        print("Usage: weekly_compile.py '<json_from_llm>'")
        return

    raw = " ".join(sys.argv[1:])

    try:
        start = raw.index('{')
        end = raw.rindex('}') + 1
        edits = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        print("ERROR: Invalid JSON. Compilation aborted.")
        return

    if edits.get("no_changes"):
        print("No changes proposed. Compilation complete.")
        return

    guidelines = load_json(os.path.join(MEMORY_DIR, "guidelines.json"))
    insights = load_json(os.path.join(MEMORY_DIR, "insights.json"),
                         {"detected_patterns": [], "pending_items": [], "automation_suggestions": []})
    soul = load_json(os.path.join(MEMORY_DIR, "soul.json"))
    users = load_json(os.path.join(MEMORY_DIR, "users.json"))

    results = []

    if "insights" in edits:
        backup_file(os.path.join(MEMORY_DIR, "insights.json"))
        insights = apply_insights(insights, edits["insights"], guidelines)
        with open(os.path.join(MEMORY_DIR, "insights.json"), 'w') as f:
            json.dump(insights, f, ensure_ascii=False, indent=2)
        results.append("insights.json updated")

    if "soul" in edits:
        backup_file(os.path.join(MEMORY_DIR, "soul.json"))
        soul = apply_soul(soul, edits["soul"], guidelines)
        with open(os.path.join(MEMORY_DIR, "soul.json"), 'w') as f:
            json.dump(soul, f, ensure_ascii=False, indent=2)
        results.append("soul.json updated")

    if "users" in edits:
        backup_file(os.path.join(MEMORY_DIR, "users.json"))
        users = apply_users(users, edits["users"], guidelines)
        with open(os.path.join(MEMORY_DIR, "users.json"), 'w') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        results.append("users.json updated")

    summary = ", ".join(results) if results else "No files modified"
    print(f"Weekly compilation complete: {summary}")

if __name__ == "__main__":
    main()
