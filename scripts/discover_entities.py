#!/usr/bin/env python3
"""
Autodiscover entities exposed to the conversation agent.
Reads entity_registry's should_expose flag to match what the LLM sees.
Preserves 'events' and 'monitor' fields set by user or previous runs.

Usage:
  discover_entities.py              # Full discovery
  discover_entities.py --add <id> <friendly_name>
  discover_entities.py --remove <id>
"""
import json, sys, os
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

ENTITIES_PATH = "/config/memory/monitored_entities.json"
ENTITY_REGISTRY_PATH = "/config/.storage/core.entity_registry"
TOKEN_PATH = "/config/.permear_token"
HA_URL = "http://localhost:8123"

EXCLUDE_PATTERNS = [
    "sensor.sun_", "sensor.time", "sensor.date",
    "sensor.uptime", "sensor.last_boot",
    "binary_sensor.updater"
]

MAX_ENTITIES = 80

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
    """Read entity_registry to find entities with should_expose=true."""
    if not os.path.exists(ENTITY_REGISTRY_PATH):
        return None
    try:
        with open(ENTITY_REGISTRY_PATH, 'r') as f:
            registry = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None

    exposed = set()
    entities = registry.get("data", {}).get("entities", [])
    for entity in entities:
        entity_id = entity.get("entity_id", "")
        options = entity.get("options", {})
        conv_options = options.get("conversation", {})
        if conv_options.get("should_expose", False):
            exposed.add(entity_id)
    return exposed if exposed else None

def is_excluded(entity_id):
    for pattern in EXCLUDE_PATTERNS:
        if entity_id.startswith(pattern):
            return True
    return False

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
    states = ha_api("states", token) if token else None
    if not states:
        print("ERROR: Cannot read HA states API")
        return False

    state_map = {s.get("entity_id", ""): s for s in states}

    # Build lookup of existing entries to preserve events/monitor fields
    current = load_current()
    existing_lookup = {}
    for e in current.get("entities", []):
        existing_lookup[e["entity_id"]] = e

    discovered = []
    for eid, state in state_map.items():
        if exposed_ids is not None and eid not in exposed_ids:
            continue
        if is_excluded(eid):
            continue

        friendly = state.get("attributes", {}).get("friendly_name", eid)
        domain = eid.split(".")[0] if "." in eid else ""

        entry = {
            "entity_id": eid,
            "friendly_name": friendly,
            "domain": domain,
            "monitor": False
        }

        # Preserve existing fields (monitor, events) from previous data
        if eid in existing_lookup:
            old = existing_lookup[eid]
            entry["monitor"] = old.get("monitor", False)
            if "events" in old:
                entry["events"] = old["events"]

        discovered.append(entry)

    # Also keep manually added entities not in discovery
    discovered_ids = {e["entity_id"] for e in discovered}
    for eid, old in existing_lookup.items():
        if eid not in discovered_ids:
            # Keep it — might be manually added or temporarily unavailable
            discovered.append(old)

    discovered.sort(key=lambda e: e["entity_id"])

    if len(discovered) > MAX_ENTITIES:
        discovered = discovered[:MAX_ENTITIES]

    source = "entity_registry" if exposed_ids else "api_all"
    result = {
        "updated_at": datetime.now().isoformat(),
        "count": len(discovered),
        "entities": discovered
    }

    save_entities(result)
    monitored = sum(1 for e in discovered if e.get("monitor"))
    with_events = sum(1 for e in discovered if e.get("events"))
    print(f"OK: {len(discovered)} entities ({monitored} monitored, "
          f"{with_events} with event triggers) via {source}")
    return True

def add_entity(entity_id, friendly_name):
    current = load_current()
    entities = current.get("entities", [])

    for e in entities:
        if e["entity_id"] == entity_id:
            print(f"Already exists: {entity_id}")
            return

    entities.append({
        "entity_id": entity_id,
        "friendly_name": friendly_name or entity_id,
        "domain": entity_id.split(".")[0] if "." in entity_id else "unknown",
        "monitor": True
    })

    current["entities"] = entities
    save_entities(current)
    print(f"Added: {entity_id} (monitor: true)")

def remove_entity(entity_id):
    current = load_current()
    entities = current.get("entities", [])
    new_entities = [e for e in entities if e["entity_id"] != entity_id]

    if len(new_entities) == len(entities):
        print(f"Not found: {entity_id}")
        return

    current["entities"] = new_entities
    save_entities(current)
    print(f"Removed: {entity_id}")

def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--add":
        eid = sys.argv[2] if len(sys.argv) > 2 else None
        fname = sys.argv[3] if len(sys.argv) > 3 else None
        if eid:
            add_entity(eid, fname)
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "--remove":
        eid = sys.argv[2] if len(sys.argv) > 2 else None
        if eid:
            remove_entity(eid)
        return

    token = load_token()
    if not token:
        print("ERROR: No token at /config/.permear_token")
        return
    discover(token)

if __name__ == "__main__":
    main()
