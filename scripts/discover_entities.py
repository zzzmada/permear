#!/usr/bin/env python3
<<<<<<< HEAD
"""Autodiscover entities exposed to conversation agent. Preserves monitor/events."""
import json, sys, os
=======
"""
Discover HA entities and populate monitored_entities.json.
v5.2: adds --add / --remove flags for manual monitoring control.
v5.1: syncs from entities exposed to voice assistants (core.entity_registry).
Preserves existing monitor settings and events fields.
Run manually: python3 /config/scripts/discover_entities.py
"""
import argparse
import json
import os
import sys
>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
<<<<<<< HEAD
from permear_config import ENTITIES_PATH, ENTITY_REGISTRY_PATH, TOKEN_PATH, HA_URL, MAX_ENTITIES
EXCLUDE_PATTERNS = ["sensor.sun_", "sensor.time", "sensor.date",
                     "sensor.uptime", "sensor.last_boot", "binary_sensor.updater"]
def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f: return f.read().strip()
    except: return None
=======
from permear_config import *
from lib.memory import load_json, save_json


def _load_entities_dict():
    """Load monitored_entities.json and return dict keyed by entity_id."""
    data = load_json(ENTITIES_PATH, {"entities": [], "source": "entity_registry"})
    source = data.get("source", "entity_registry")
    try:
        return {e["entity_id"]: e for e in data.get("entities", [])}, source
    except (KeyError, TypeError):
        return {}, "entity_registry"


def _save_entities_dict(existing_dict, source):
    """Recalculate count, sort and save entities file."""
    entities = sorted(existing_dict.values(), key=lambda x: x["entity_id"])
    count = sum(1 for e in entities if e.get("monitor", True))
    output = {
        "updated_at": datetime.now().isoformat(),
        "source": source,
        "count": count,
        "entities": entities,
    }
    save_json(ENTITIES_PATH, output)
    return count


def cmd_add(entity_id, friendly_name):
    existing, source = _load_entities_dict()
    if entity_id in existing:
        if existing[entity_id].get("monitor"):
            print(f"Entity {entity_id} already monitored.")
            return
        existing[entity_id]["monitor"] = True
    else:
        domain = entity_id.split(".")[0]
        existing[entity_id] = {
            "entity_id": entity_id,
            "friendly_name": friendly_name,
            "domain": domain,
            "monitor": True,
        }
    _save_entities_dict(existing, source)
    print(f"Entity {entity_id} added to monitoring.")


def cmd_remove(entity_id):
    existing, source = _load_entities_dict()
    if entity_id not in existing:
        print(f"Entity {entity_id} not in list.")
        return
    if not existing[entity_id].get("monitor"):
        print(f"Entity {entity_id} not monitored.")
        return
    existing[entity_id]["monitor"] = False
    _save_entities_dict(existing, source)
    print(f"Entity {entity_id} removed from monitoring.")


def load_token():
    try:
        with open(TOKEN_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
def ha_api(endpoint, token):
    try:
<<<<<<< HEAD
        req = Request(f"{HA_URL}/api/{endpoint}",
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urlopen(req, timeout=15) as r: return json.loads(r.read().decode())
    except: return None
def get_exposed_ids():
    if not os.path.exists(ENTITY_REGISTRY_PATH): return None
    try:
        with open(ENTITY_REGISTRY_PATH, 'r') as f: registry = json.load(f)
    except: return None
    exposed = set()
    for e in registry.get("data", {}).get("entities", []):
        if e.get("options", {}).get("conversation", {}).get("should_expose", False):
            exposed.add(e.get("entity_id", ""))
    return exposed if exposed else None
def load_current():
    try:
        with open(ENTITIES_PATH, 'r') as f: return json.load(f)
    except: return {"updated_at": None, "count": 0, "entities": []}
def save_entities(data):
    os.makedirs(os.path.dirname(ENTITIES_PATH), exist_ok=True)
    data["count"] = len(data.get("entities", []))
    with open(ENTITIES_PATH, 'w') as f: json.dump(data, f, ensure_ascii=False, indent=2)
def discover(token):
    exposed = get_exposed_ids()
    states = ha_api("states", token)
    if not states: print("ERROR: Cannot read HA states API"); return
    state_map = {s.get("entity_id", ""): s for s in states}
    current = load_current()
    existing = {e["entity_id"]: e for e in current.get("entities", [])}
    discovered = []
    for eid, state in state_map.items():
        if exposed is not None and eid not in exposed: continue
        if any(eid.startswith(p) for p in EXCLUDE_PATTERNS): continue
        friendly = state.get("attributes", {}).get("friendly_name", eid)
        domain = eid.split(".")[0] if "." in eid else ""
        entry = {"entity_id": eid, "friendly_name": friendly, "domain": domain, "monitor": False}
        if eid in existing:
            old = existing[eid]
            entry["monitor"] = old.get("monitor", False)
            if "events" in old: entry["events"] = old["events"]
        discovered.append(entry)
    for eid, old in existing.items():
        if eid not in {e["entity_id"] for e in discovered}: discovered.append(old)
    discovered.sort(key=lambda e: e["entity_id"])
    if len(discovered) > MAX_ENTITIES: discovered = discovered[:MAX_ENTITIES]
    source = "entity_registry" if exposed else "api_all"
    save_entities({"updated_at": datetime.now().isoformat(), "source": source,
                   "count": len(discovered), "entities": discovered})
    mon = sum(1 for e in discovered if e.get("monitor"))
    evts = sum(1 for e in discovered if e.get("events"))
    print(f"OK: {len(discovered)} entities ({mon} monitored, {evts} with events) via {source}")
def add_entity(eid, fname):
    current = load_current()
    if any(e["entity_id"] == eid for e in current.get("entities", [])):
        print(f"Already exists: {eid}"); return
    current.setdefault("entities", []).append({
        "entity_id": eid, "friendly_name": fname or eid,
        "domain": eid.split(".")[0] if "." in eid else "unknown", "monitor": True})
    save_entities(current); print(f"Added: {eid}")
def remove_entity(eid):
    current = load_current()
    new = [e for e in current.get("entities", []) if e["entity_id"] != eid]
    if len(new) == len(current.get("entities", [])): print(f"Not found: {eid}"); return
    current["entities"] = new; save_entities(current); print(f"Removed: {eid}")
def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--add":
        add_entity(sys.argv[2] if len(sys.argv) > 2 else None,
                   sys.argv[3] if len(sys.argv) > 3 else None); return
    if len(sys.argv) >= 2 and sys.argv[1] == "--remove":
        if len(sys.argv) > 2: remove_entity(sys.argv[2]); return
    token = load_token()
    if not token: print("ERROR: No token at " + TOKEN_PATH); return
    discover(token)
=======
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        print(f"HA API error: {e}")
        return None


def get_exposed_entity_ids():
    """Read entity registry and return set of entity_ids exposed to conversation."""
    try:
        with open(ENTITY_REGISTRY_PATH, 'r') as f:
            data = json.load(f)
        entries = data.get("data", {}).get("entities", [])
        exposed = {
            e["entity_id"]
            for e in entries
            if e.get("options", {}).get("conversation", {}).get("should_expose") is True
        }
        return exposed
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(f"WARNING: Could not read entity registry ({e}). Falling back to domain filter.")
        return None


def main():
    parser = argparse.ArgumentParser(description="Discover HA entities for PERMEAR monitoring.")
    parser.add_argument("--add", nargs="+", metavar=("ENTITY_ID", "FRIENDLY_NAME"),
                        help="Add entity to monitoring")
    parser.add_argument("--remove", metavar="ENTITY_ID",
                        help="Remove entity from monitoring")
    args = parser.parse_args()

    if args.add:
        entity_id = args.add[0]
        friendly_name = " ".join(args.add[1:]) if len(args.add) > 1 else entity_id
        cmd_add(entity_id, friendly_name)
        return

    if args.remove:
        cmd_remove(args.remove)
        return

    token = load_token()
    if not token:
        print("ERROR: Token not found at", TOKEN_PATH)
        return

    states = ha_api("states", token)
    if not states:
        print("ERROR: Could not fetch states from HA.")
        return
    states_by_id = {s["entity_id"]: s for s in states}

    exposed_ids = get_exposed_entity_ids()

    existing = {}
    existing_data = load_json(ENTITIES_PATH, {"entities": []})
    for entry in existing_data.get("entities", []):
        try:
            existing[entry["entity_id"]] = entry
        except (KeyError, TypeError):
            pass

    entities = []

    if exposed_ids:
        for entity_id in sorted(exposed_ids):
            state = states_by_id.get(entity_id)
            friendly_name = (
                state.get("attributes", {}).get("friendly_name", entity_id)
                if state else entity_id
            )
            domain = entity_id.split(".")[0]

            if entity_id in existing:
                entry = existing[entity_id].copy()
                entry["friendly_name"] = friendly_name
                entities.append(entry)
            else:
                entry = {
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "domain": domain,
                    "monitor": True,
                }
                entities.append(entry)

        for entity_id, entry in existing.items():
            if entity_id not in exposed_ids:
                entry = entry.copy()
                entry["monitor"] = False
                entities.append(entry)

        print(f"Source: entity registry - {len(exposed_ids)} exposed entities")
    else:
        MONITORED_DOMAINS = [
            "light", "switch", "binary_sensor", "sensor", "climate",
            "media_player", "cover", "fan", "input_boolean", "lock"
        ]
        SKIP_PREFIXES = [
            "sensor.time", "sensor.date", "sensor.last_boot",
            "sensor.sun", "sun.sun", "weather.",
        ]
        for state in states:
            entity_id = state.get("entity_id", "")
            domain = entity_id.split(".")[0]
            if domain not in MONITORED_DOMAINS:
                continue
            if any(entity_id.startswith(p) for p in SKIP_PREFIXES):
                continue
            if entity_id in existing:
                entities.append(existing[entity_id])
            else:
                friendly_name = state.get("attributes", {}).get("friendly_name", entity_id)
                entities.append({
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "domain": domain,
                    "monitor": True,
                })
        print(f"Source: domain filter (fallback) - {len(entities)} entities")

    entities_sorted = sorted(entities, key=lambda x: x["entity_id"])
    monitor_count = sum(1 for e in entities_sorted if e.get("monitor", True))
    source = "entity_registry" if exposed_ids else "domain_filter"

    output = {
        "updated_at": datetime.now().isoformat(),
        "source": source,
        "count": monitor_count,
        "entities": entities_sorted,
    }

    save_json(ENTITIES_PATH, output)
    print(f"OK: {len(entities_sorted)} total entities ({monitor_count} monitored) saved to {ENTITIES_PATH}")


>>>>>>> 3ee64b2 (v7.2.0: dual LLM path architecture, automatic fallback and active forgetting)
if __name__ == "__main__":
    main()
