#!/usr/bin/env python3
"""CRUD for agent-managed automations."""
import json, sys, os, time
import yaml
from urllib.request import Request, urlopen
from urllib.error import URLError
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import AGENT_YAML, TOKEN_PATH, HA_URL, MAX_AUTOMATIONS
def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f: return f.read().strip()
    except: print("ERROR: No token at " + TOKEN_PATH); return None
def ha_api(ep, method="GET", data=None, token=None):
    try:
        body = json.dumps(data).encode() if data else None
        req = Request(f"{HA_URL}/api/{ep}", data=body,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method=method)
        with urlopen(req, timeout=10) as r: return json.loads(r.read().decode())
    except: return None
def entity_exists(eid, token): return ha_api(f"states/{eid}", token=token) is not None
def load_autos():
    if not os.path.exists(AGENT_YAML): return []
    try:
        with open(AGENT_YAML, 'r') as f: data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except: return []
def save_autos(autos):
    os.makedirs(os.path.dirname(AGENT_YAML), exist_ok=True)
    with open(AGENT_YAML, 'w') as f:
        yaml.dump(autos, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    try:
        with open(AGENT_YAML, 'r') as f: yaml.safe_load(f)
        return True
    except: return False
def reload(token):
    return ha_api("services/automation/reload", method="POST", data={}, token=token) is not None if token else False
def validate_ents(obj, token):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "entity_id" and isinstance(v, str) and not entity_exists(v, token): return False, v
            ok, bad = validate_ents(v, token)
            if not ok: return False, bad
    elif isinstance(obj, list):
        for item in obj:
            ok, bad = validate_ents(item, token)
            if not ok: return False, bad
    return True, None
def create(json_str, token):
    if not json_str or not json_str.strip(): print("ERROR: Empty spec."); return
    try: spec = json.loads(json_str[json_str.index('{'):json_str.rindex('}') + 1])
    except (ValueError, json.JSONDecodeError) as e: print(f"ERROR: Invalid JSON — {e}"); return
    alias = spec.get("alias", "").strip()
    if not alias: print("ERROR: 'alias' required."); return
    trigger = spec.get("trigger"); action = spec.get("action")
    if not trigger or not action: print("ERROR: 'trigger' and 'action' required."); return
    if isinstance(trigger, dict): trigger = [trigger]
    if isinstance(action, dict): action = [action]
    condition = spec.get("condition", [])
    if isinstance(condition, dict): condition = [condition]
    if token:
        ok, bad = validate_ents({"trigger": trigger, "action": action}, token)
        if not ok: print(f"ERROR: Entity '{bad}' not found."); return
    autos = load_autos()
    if len(autos) >= MAX_AUTOMATIONS: print(f"ERROR: Max {MAX_AUTOMATIONS} reached."); return
    if any(a.get("alias","").lower() == alias.lower() for a in autos):
        print(f"ERROR: '{alias}' exists."); return
    aid = f"permear_agent_{int(time.time())}"
    autos.append({"alias": alias, "id": aid, "trigger": trigger,
                  "condition": condition, "action": action, "mode": "single"})
    if not save_autos(autos): autos.pop(); save_autos(autos); print("ERROR: YAML invalid."); return
    r = reload(token)
    print(json.dumps({"result": "created", "id": aid, "alias": alias,
          "message": f"Automation created: '{alias}' ({aid})." + (" Active." if r else " Reload failed.")}))
def remove(identifier, token):
    autos = load_autos(); il = identifier.strip().lower()
    found = next((i for i, a in enumerate(autos)
                  if a.get("id","").lower() == il or a.get("alias","").lower() == il), None)
    if found is None: print(f"ERROR: '{identifier}' not found."); return
    removed = autos.pop(found); save_autos(autos); reload(token)
    print(json.dumps({"result": "removed", "alias": removed.get("alias"),
                      "message": f"Removed: '{removed.get('alias')}'"} ))
def list_autos():
    autos = load_autos()
    if not autos: print("NO_AUTOMATIONS"); return
    print(json.dumps({"automations": [{"id": a.get("id","?"), "alias": a.get("alias","?")}
                                       for a in autos], "count": len(autos)}, ensure_ascii=False))
def main():
    if len(sys.argv) < 2: print("Usage: manage_agent_automations.py [create|remove|list]"); return
    cmd = sys.argv[1].lower(); token = load_token()
    if cmd == "create": create(" ".join(sys.argv[2:]) if len(sys.argv) > 2 else "", token)
    elif cmd == "remove": remove(sys.argv[2] if len(sys.argv) > 2 else "", token)
    elif cmd == "list": list_autos()
if __name__ == "__main__":
    main()
