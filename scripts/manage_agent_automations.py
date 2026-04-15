#!/usr/bin/env python3
"""CRUD for agent-managed automations. create/remove/list."""
import json, sys, os, time
import yaml
from urllib.request import Request, urlopen
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import AGENT_YAML, TOKEN_PATH, HA_URL, MAX_AUTOMATIONS

def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("ERROR: Token not found at " + TOKEN_PATH)
        return None

def ha_api(endpoint, method="GET", data=None, token=None):
    url = f"{HA_URL}/api/{endpoint}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    try:
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=10) as resp:
            return json.loads(resp.read().decode())
    except URLError:
        return None

def entity_exists(eid, token):
    return ha_api(f"states/{eid}", token=token) is not None

def load_automations():
    if not os.path.exists(AGENT_YAML):
        return []
    try:
        with open(AGENT_YAML, 'r') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except (yaml.YAMLError, TypeError):
        return []

def save_automations(automations):
    os.makedirs(os.path.dirname(AGENT_YAML), exist_ok=True)
    with open(AGENT_YAML, 'w') as f:
        yaml.dump(automations, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    try:
        with open(AGENT_YAML, 'r') as f:
            yaml.safe_load(f)
        return True
    except yaml.YAMLError:
        return False

def reload_automations(token):
    return ha_api("services/automation/reload", method="POST", data={}, token=token) is not None if token else False

def validate_entities(obj, token):
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key == "entity_id" and isinstance(val, str) and not entity_exists(val, token):
                return False, val
            ok, bad = validate_entities(val, token)
            if not ok:
                return False, bad
    elif isinstance(obj, list):
        for item in obj:
            ok, bad = validate_entities(item, token)
            if not ok:
                return False, bad
    return True, None

def create_automation(json_str, token):
    if not json_str or not json_str.strip():
        print("ERROR: Empty spec.")
        return
    try:
        spec = json.loads(json_str[json_str.index('{'):json_str.rindex('}') + 1])
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: Invalid JSON — {e}")
        return

    alias = spec.get("alias", "").strip()
    if not alias:
        print("ERROR: 'alias' required.")
        return
    trigger = spec.get("trigger")
    action = spec.get("action")
    if not trigger or not action:
        print("ERROR: 'trigger' and 'action' required.")
        return
    if isinstance(trigger, dict): trigger = [trigger]
    if isinstance(action, dict): action = [action]
    condition = spec.get("condition", [])
    if isinstance(condition, dict): condition = [condition]

    if token:
        ok, bad = validate_entities({"trigger": trigger, "action": action}, token)
        if not ok:
            print(f"ERROR: Entity '{bad}' does not exist.")
            return

    automations = load_automations()
    if len(automations) >= MAX_AUTOMATIONS:
        print(f"ERROR: Max {MAX_AUTOMATIONS} reached.")
        return
    if any(a.get("alias", "").lower() == alias.lower() for a in automations):
        print(f"ERROR: '{alias}' already exists.")
        return

    auto_id = f"permear_agent_{int(time.time())}"
    automations.append({"alias": alias, "id": auto_id, "trigger": trigger,
                        "condition": condition, "action": action, "mode": "single"})
    if not save_automations(automations):
        automations.pop()
        save_automations(automations)
        print("ERROR: YAML validation failed.")
        return
    reloaded = reload_automations(token)
    print(json.dumps({"result": "created", "id": auto_id, "alias": alias,
                      "message": f"Automation created: '{alias}' (id: {auto_id})."
                      + (" Active." if reloaded else " Reload failed.")}))

def remove_automation(identifier, token):
    automations = load_automations()
    il = identifier.strip().lower()
    found = next((i for i, a in enumerate(automations)
                  if a.get("id","").lower() == il or a.get("alias","").lower() == il), None)
    if found is None:
        print(f"ERROR: No automation '{identifier}'.")
        return
    removed = automations.pop(found)
    save_automations(automations)
    reload_automations(token)
    print(json.dumps({"result": "removed", "alias": removed.get("alias"),
                      "message": f"Removed: '{removed.get('alias')}'"} ))

def list_automations():
    automations = load_automations()
    if not automations:
        print("NO_AUTOMATIONS")
        return
    print(json.dumps({"automations": [{"id": a.get("id","?"), "alias": a.get("alias","?")}
                                       for a in automations],
                      "count": len(automations)}, ensure_ascii=False))

def main():
    if len(sys.argv) < 2:
        print("Usage: manage_agent_automations.py [create|remove|list]")
        return
    cmd = sys.argv[1].lower()
    token = load_token()
    if cmd == "create":
        create_automation(" ".join(sys.argv[2:]) if len(sys.argv) > 2 else "", token)
    elif cmd == "remove":
        remove_automation(sys.argv[2] if len(sys.argv) > 2 else "", token)
    elif cmd == "list":
        list_automations()

if __name__ == "__main__":
    main()
