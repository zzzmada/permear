#!/usr/bin/env python3
"""Autodiscover entities exposed to conversation agent. Preserves monitor and events fields."""
import json, sys, os
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import ENTITIES_PATH, ENTITY_REGISTRY_PATH, TOKEN_PATH, HA_URL, MAX_ENTITIES

EXCLUDE_PATTERNS = ["sensor.sun_", "sensor.time", "sensor.date",
                     "sensor.uptime", "sensor.last_boot", "binary_sensor.updater"]

def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def ha_api(endpoint, token):
    url = f"{HA_URL}/api/{endpoint}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except URLError:
        return None

def get_exposed_entity_ids():
    if not os.path.exists(ENTITY_REGISTRY_PATH):
        return None
    try:
        with open(ENTITY_REGISTRY_PATH, 'r') as f:
            registry = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None
    exposed = set()
    for entity in registry.get("data", {}).get("entities", []):
        if entity.get("options", {}).get("conversation", {}).get("should_expose", False):
            exposed.add(entity.get("entity_id", ""))
    return exposed if exposed else None

def load_current():
    try:
        with open(ENTITIES_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"updated_at": None, "count": 0, "entities": []}

def save_entities(data):
    os.makedirs(os.path.dirname(ENTITIES_PATH), exist_ok=True)
    data["count"] = len(data.get("entities", []))
    with open(ENTITIES_PATH, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def discover(token):
    exposed_ids = get_exposed_entity_ids()
    states = ha_api("states", token)
    if not states:
        print("ERROR: Cannot read HA states API")
        return
    state_map = {s.get("entity_id", ""): s for s in states}
    current = load_current()
    existing = {e["entity_id"]: e for e in current.get("entities", [])}

    discovered = []
    for eid, state in state_map.items():
        if exposed_ids is not None and eid not in exposed_ids:
            continue
        if any(eid.startswith(p) for p in EXCLUDE_PATTERNS):
            continue
        friendly = state.get("attributes", {}).get("friendly_name", eid)
        domain = eid.split(".")[0] if "." in eid else ""
        entry = {"entity_id": eid, "friendly_name": friendly, "domain": domain, "monitor": False}
        if eid in existing:
            old = existing[eid]
            entry["monitor"] = old.get("monitor", False)
            if "events" in old:
                entry["events"] = old["events"]
        discovered.append(entry)

    for eid, old in existing.items():
        if eid not in {e["entity_id"] for e in discovered}:
            discovered.append(old)

    discovered.sort(key=lambda e: e["entity_id"])
    if len(discovered) > MAX_ENTITIES:
        discovered = discovered[:MAX_ENTITIES]

    source = "entity_registry" if exposed_ids else "api_all"
    save_entities({"updated_at": datetime.now().isoformat(), "source": source,
                   "count": len(discovered), "entities": discovered})
    monitored = sum(1 for e in discovered if e.get("monitor"))
    with_events = sum(1 for e in discovered if e.get("events"))
    print(f"OK: {len(discovered)} entities ({monitored} monitored, {with_events} with events) via {source}")

def add_entity(eid, fname):
    current = load_current()
    if any(e["entity_id"] == eid for e in current.get("entities", [])):
        print(f"Already exists: {eid}")
        return
    current.setdefault("entities", []).append({
        "entity_id": eid, "friendly_name": fname or eid,
        "domain": eid.split(".")[0] if "." in eid else "unknown", "monitor": True})
    save_entities(current)
    print(f"Added: {eid} (monitor: true)")

def remove_entity(eid):
    current = load_current()
    new = [e for e in current.get("entities", []) if e["entity_id"] != eid]
    if len(new) == len(current.get("entities", [])):
        print(f"Not found: {eid}")
        return
    current["entities"] = new
    save_entities(current)
    print(f"Removed: {eid}")

def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--add":
        add_entity(sys.argv[2] if len(sys.argv) > 2 else None,
                   sys.argv[3] if len(sys.argv) > 3 else None)
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "--remove":
        if len(sys.argv) > 2:
            remove_entity(sys.argv[2])
        return
    token = load_token()
    if not token:
        print("ERROR: No token at " + TOKEN_PATH)
        return
    discover(token)

if __name__ == "__main__":
    main()
