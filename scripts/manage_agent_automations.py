#!/usr/bin/env python3
"""
CRUD for agent-managed automations in a dedicated YAML file.
Usage:
  manage_agent_automations.py create '<json_automation>'
  manage_agent_automations.py remove '<id_or_alias>'
  manage_agent_automations.py list
"""
import json, sys, os, time
import yaml
from urllib.request import Request, urlopen
from urllib.error import URLError

AGENT_YAML = "/config/automations/agent_automations.yaml"
TOKEN_PATH = "/config/.permear_token"
HA_URL = "http://localhost:8123"
MAX_AUTOMATIONS = 20

def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("ERROR: Token not found at /config/.permear_token")
        print("Create: HA Profile → Long-Lived Access Tokens → Create")
        print("Save: echo 'TOKEN' > /config/.permear_token && chmod 600 /config/.permear_token")
        return None

def ha_api(endpoint, method="GET", data=None, token=None):
    url = f"{HA_URL}/api/{endpoint}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        return None

def entity_exists(entity_id, token):
    result = ha_api(f"states/{entity_id}", token=token)
    return result is not None

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
        yaml.dump(automations, f, default_flow_style=False,
                  allow_unicode=True, sort_keys=False)
    # Validate written file
    try:
        with open(AGENT_YAML, 'r') as f:
            yaml.safe_load(f)
        return True
    except yaml.YAMLError as e:
        print(f"ERROR: Written YAML is invalid — {e}")
        return False

def reload_automations(token):
    if not token:
        return False
    result = ha_api("services/automation/reload", method="POST", data={}, token=token)
    return result is not None

def validate_entities(obj, token):
    """Recursively find and validate entity_ids in a dict/list."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key == "entity_id" and isinstance(val, str):
                if not entity_exists(val, token):
                    return False, val
            result = validate_entities(val, token)
            if not result[0]:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = validate_entities(item, token)
            if not result[0]:
                return result
    return True, None

def create_automation(json_str, token):
    if not json_str or not json_str.strip():
        print("ERROR: Empty spec. Provide JSON with alias, trigger, and action.")
        return

    # Extract JSON from potentially messy input
    try:
        start = json_str.index('{')
        end = json_str.rindex('}') + 1
        spec = json.loads(json_str[start:end])
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: Invalid JSON — {e}")
        return

    alias = spec.get("alias", "").strip()
    if not alias:
        print("ERROR: 'alias' is required.")
        return

    trigger = spec.get("trigger")
    if not trigger:
        print("ERROR: 'trigger' is required.")
        return
    if isinstance(trigger, dict):
        trigger = [trigger]

    action = spec.get("action")
    if not action:
        print("ERROR: 'action' is required.")
        return
    if isinstance(action, dict):
        action = [action]

    condition = spec.get("condition", [])
    if isinstance(condition, dict):
        condition = [condition]

    # Validate all entity_ids
    if token:
        valid, bad_entity = validate_entities({"trigger": trigger, "action": action}, token)
        if not valid:
            print(f"ERROR: Entity '{bad_entity}' does not exist in HA.")
            return

    automations = load_automations()

    if len(automations) >= MAX_AUTOMATIONS:
        print(f"ERROR: Maximum {MAX_AUTOMATIONS} automations reached. Remove one first.")
        return

    for a in automations:
        if a.get("alias", "").lower() == alias.lower():
            print(f"ERROR: Automation with alias '{alias}' already exists.")
            return

    auto_id = f"permear_agent_{int(time.time())}"

    new_auto = {
        "alias": alias,
        "id": auto_id,
        "trigger": trigger,
        "condition": condition,
        "action": action,
        "mode": "single"
    }

    automations.append(new_auto)

    if not save_automations(automations):
        automations.pop()
        save_automations(automations)
        print("ERROR: YAML validation failed. Automation not created.")
        return

    reloaded = reload_automations(token)

    print(json.dumps({
        "result": "created",
        "id": auto_id,
        "alias": alias,
        "message": f"Automation created: '{alias}' (id: {auto_id})."
            + (" Active immediately." if reloaded else " Reload failed — will activate on HA restart.")
    }))

def remove_automation(identifier, token):
    automations = load_automations()
    identifier_lower = identifier.strip().lower()

    found = None
    for i, a in enumerate(automations):
        if (a.get("id", "").lower() == identifier_lower or
                a.get("alias", "").lower() == identifier_lower):
            found = i
            break

    if found is None:
        print(f"ERROR: No automation found matching '{identifier}'.")
        return

    removed = automations.pop(found)
    save_automations(automations)
    reload_automations(token)

    print(json.dumps({
        "result": "removed",
        "id": removed.get("id"),
        "alias": removed.get("alias"),
        "message": f"Automation removed: '{removed.get('alias')}'"
    }))

def list_automations():
    automations = load_automations()
    if not automations:
        print("NO_AUTOMATIONS")
        return

    result = []
    for a in automations:
        result.append({
            "id": a.get("id", "?"),
            "alias": a.get("alias", "?"),
        })
    print(json.dumps({"automations": result, "count": len(result)}, ensure_ascii=False))

def main():
    if len(sys.argv) < 2:
        print("Usage: manage_agent_automations.py [create|remove|list] [args]")
        return

    command = sys.argv[1].lower()
    token = load_token()

    if command == "create":
        if len(sys.argv) < 3:
            print("ERROR: JSON spec required.")
            return
        create_automation(" ".join(sys.argv[2:]), token)
    elif command == "remove":
        if len(sys.argv) < 3:
            print("ERROR: Automation id or alias required.")
            return
        remove_automation(sys.argv[2], token)
    elif command == "list":
        list_automations()
    else:
        print(f"ERROR: Unknown command '{command}'.")

if __name__ == "__main__":
    main()
