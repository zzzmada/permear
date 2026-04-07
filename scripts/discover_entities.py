#!/usr/bin/env python3
"""
Autodiscover entities exposed to the conversation agent.
Filters by entity_registry's should_expose flag to match exactly
what the LLM can see — avoids sending 150+ irrelevant entities.

Usage:
  discover_entities.py              # Full discovery
  discover_entities.py --add <id> <name>   # Add manual entry
  discover_entities.py --remove <id>       # Remove entry

IMPORTANT: The entity_registry file location varies by HA version.
Common paths: /config/.storage/core.entity_registry
"""
import json, sys, os
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

ENTITIES_PATH = "/config/memory/monitored_entities.json"
ENTITY_REGISTRY_PATH = "/config/.storage/core.entity_registry"
TOKEN_PATH = "/config/.permear_token"
HA_URL = "http://localhost:8123"
MAX_ENTITIES = 50

# Entities to always exclude even if exposed
EXCLUDE_PATTERNS = [
    "sensor.sun_", "sensor.time", "sensor.date",
    "sensor.uptime", "sensor.last_boot",
    "binary_sensor.updater"
]

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
        # Check conversation integration exposure
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
        return {"last_update": None, "source": "none", "entities": []}

def save_entities(data):
    os.makedirs(os.path.dirname(ENTITIES_PATH), exist_ok=True)
    with open(ENTITIES_PATH, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def discover(token):
    # Get exposed entity IDs from registry
    exposed_ids = get_exposed_entity_ids()

    # Get all states from REST API
    states = ha_api("states", token) if token else None
    if not states:
        print("ERROR: Cannot read HA states API")
        return False

    # Build lookup of states
    state_map = {}
    for s in states:
        state_map[s.get("entity_id", "")] = s

    # Preserve manual entries
    current = load_current()
    manual_entries = [e for e in current.get("entities", []) if e.get("manual", False)]

    discovered = []
    for eid, state in state_map.items():
        # If we have registry data, only include exposed entities
        if exposed_ids is not None and eid not in exposed_ids:
            continue

        if is_excluded(eid):
            continue
        if state.get("state") in ["unavailable"]:
            continue

        friendly = state.get("attributes", {}).get("friendly_name", eid)
        domain = eid.split(".")[0] if "." in eid else ""

        discovered.append({
            "entity_id": eid,
            "friendly_name": friendly,
            "domain": domain,
            "manual": False
        })

    # Merge: manual first, then discovered (dedup)
    seen_ids = set()
    merged = []

    for e in manual_entries:
        if e["entity_id"] not in seen_ids:
            merged.append(e)
            seen_ids.add(e["entity_id"])

    for e in discovered:
        if e["entity_id"] not in seen_ids and len(merged) < MAX_ENTITIES:
            merged.append(e)
            seen_ids.add(e["entity_id"])

    source = "entity_registry" if exposed_ids else "api_all_domains"
    result = {
        "last_update": datetime.now().isoformat(),
        "source": source,
        "entities": merged
    }

    save_entities(result)
    print(f"OK: {len(merged)} entities ({len(manual_entries)} manual + "
          f"{len(merged) - len(manual_entries)} discovered via {source})")
    return True

def add_entity(entity_id, friendly_name):
    current = load_current()
    entities = current.get("entities", [])

    for e in entities:
        if e["entity_id"] == entity_id:
            print(f"Already monitored: {entity_id}")
            return

    entities.append({
        "entity_id": entity_id,
        "friendly_name": friendly_name or entity_id,
        "domain": entity_id.split(".")[0] if "." in entity_id else "unknown",
        "manual": True
    })

    current["entities"] = entities
    save_entities(current)
    print(f"Added: {entity_id} (manual)")

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
        print("ERROR: No token found at /config/.permear_token")
        return
    discover(token)

if __name__ == "__main__":
    main()
