#!/usr/bin/env python3
"""Weekly compilation. Truncation detection, any-field diff in apply_users."""
import json, sys, os, shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR, LOG_DIR

def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

def backup_file(path):
    if os.path.exists(path):
        shutil.copy2(path, path + f".bak.{datetime.now().strftime('%Y%m%d')}")

def detect_truncation(raw):
    if not raw or not raw.strip():
        return True, "Empty response"
    s = raw.strip()
    if s.count('{') - s.count('}') > 0:
        return True, f"Unbalanced braces: {s.count('{') - s.count('}')} unclosed"
    if s.count('[') - s.count(']') > 0:
        return True, f"Unbalanced brackets: {s.count('[') - s.count(']')} unclosed"
    return False, None

def log_error(raw, msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    f = os.path.join(LOG_DIR, f"weekly_compile_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    with open(f, 'w') as fh:
        fh.write(f"Error: {msg}\nTimestamp: {datetime.now().isoformat()}\nLength: {len(raw)}\n---\n{raw}")
    print(f"Error log saved to {f}")

def apply_insights(current, edits, _):
    for p in edits.get("new_patterns", []):
        if p not in current.get("detected_patterns", []):
            current.setdefault("detected_patterns", []).append(p)
    current["detected_patterns"] = current.get("detected_patterns", [])[-30:]
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

def apply_soul(current, edits, _):
    for field in edits:
        if field in ["name", "mission", "values"]:
            continue
        if field == "behavior_rules" and isinstance(edits[field], dict):
            for r in edits[field].get("add", []):
                if r not in current.get("behavior_rules", []):
                    current.setdefault("behavior_rules", []).append(r)
            for r in edits[field].get("remove", []):
                if r in current.get("behavior_rules", []):
                    current["behavior_rules"].remove(r)
            current["behavior_rules"] = current.get("behavior_rules", [])[:15]
        elif field == "tone":
            current["tone"] = edits["tone"]
    return current

def apply_users(current, edits, _):
    for user_key, user_edits in edits.items():
        if user_key not in current:
            if "role" in user_edits:
                current[user_key] = user_edits
            continue
        for field, value in user_edits.items():
            if isinstance(value, dict) and ("add" in value or "remove" in value):
                lst = current[user_key].get(field, [])
                if not isinstance(lst, list):
                    lst = []
                for item in value.get("add", []):
                    if item not in lst:
                        lst.append(item)
                for item in value.get("remove", []):
                    if item in lst:
                        lst.remove(item)
                current[user_key][field] = lst[-20:]
            else:
                current[user_key][field] = value
    return current

def main():
    if len(sys.argv) < 2:
        print("Usage: weekly_compile.py '<json_from_llm>'")
        return
    raw = " ".join(sys.argv[1:])
    is_trunc, reason = detect_truncation(raw)
    if is_trunc:
        print(f"ERROR: Response appears truncated — {reason}")
        print("Fix: Set max_tokens to 8192+ in your LLM integration settings.")
        log_error(raw, reason)
        return
    try:
        edits = json.loads(raw[raw.index('{'):raw.rindex('}') + 1])
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: Invalid JSON — {e}")
        log_error(raw, str(e))
        return
    if edits.get("no_changes"):
        print("No changes proposed. Compilation complete.")
        return

    guidelines = load_json(os.path.join(MEMORY_DIR, "guidelines.json"))
    results = []
    for key, apply_fn, default in [
        ("insights", apply_insights, {"detected_patterns": [], "pending_items": [], "automation_suggestions": []}),
        ("soul", apply_soul, None),
        ("users", apply_users, None),
    ]:
        if key in edits:
            path = os.path.join(MEMORY_DIR, f"{key}.json")
            backup_file(path)
            current = load_json(path, default)
            current = apply_fn(current, edits[key], guidelines)
            with open(path, 'w') as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            results.append(f"{key}.json updated")
    print(f"Weekly compilation complete: {', '.join(results) if results else 'No files modified'}")

if __name__ == "__main__":
    main()
