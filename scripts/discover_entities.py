#!/usr/bin/env python3
"""
Discover HA entities and populate monitored_entities.json.
v5.2: adds --add / --remove flags for manual monitoring control.
v5.1: syncs from entities exposed to voice assistants (core.entity_registry).
v7.5-C: detecta entidades novas de classe sensível e escreve pending_priority.json.
Preserves existing monitor settings and events fields.
Run manually: python3 /config/scripts/discover_entities.py
"""
import argparse
import json
import os
import sys
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import *
from lib.memory import load_json, save_json

PENDING_PRIORITY_PATH = os.path.join(MEMORY_DIR, "pending_priority.json")

SENSITIVE_DEVICE_CLASSES = {
    "water", "moisture",
    "smoke", "gas", "carbon_monoxide",
    "safety", "tamper",
}
SENSITIVE_DOMAINS = {"alarm_control_panel"}


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
            print(f"Entidade {entity_id} já estava monitorada.")
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
    print(f"Entidade {entity_id} adicionada ao monitoramento.")


def cmd_remove(entity_id):
    existing, source = _load_entities_dict()
    if entity_id not in existing:
        print(f"Entidade {entity_id} não estava na lista.")
        return
    if not existing[entity_id].get("monitor"):
        print(f"Entidade {entity_id} não estava monitorada.")
        return
    existing[entity_id]["monitor"] = False
    _save_entities_dict(existing, source)
    print(f"Entidade {entity_id} removida do monitoramento.")


def detect_sensitive_new(new_entity_ids, states_by_id):
    """Retorna lista de entidades novas de classe sensível para perguntar priority."""
    out = []
    for eid in new_entity_ids:
        domain = eid.split(".")[0]
        attrs = states_by_id.get(eid, {}).get("attributes", {})
        dc = attrs.get("device_class", "")
        friendly = attrs.get("friendly_name", eid)
        if domain in SENSITIVE_DOMAINS or dc in SENSITIVE_DEVICE_CLASSES:
            out.append({"entity_id": eid, "friendly_name": friendly, "device_class": dc})
    return out


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
    except URLError as e:
        print(f"HA API error: {e}")
        return None


def get_exposed_entity_ids():
    """Read entity registry and return set of entity_ids exposed to conversation.
    v7.3-A: endpoint /api/config/entity_registry/list retornou 404 nesta versão do HA
    (disponível apenas via WebSocket, não REST). Mantida leitura via arquivo .storage —
    HA escreve atomicamente (temp + rename), risco de race condition mínimo na prática.
    """
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
                        help="Adicionar entidade ao monitoramento")
    parser.add_argument("--remove", metavar="ENTITY_ID",
                        help="Remover entidade do monitoramento")
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

        print(f"Source: entity registry — {len(exposed_ids)} exposed entities")
    else:
        MONITORED_DOMAINS = [
            "light", "switch", "binary_sensor", "sensor", "climate",
            "media_player", "cover", "fan", "input_boolean", "lock"
        ]
        SKIP_PREFIXES = [
            "sensor.time", "sensor.date", "sensor.last_boot",
            "sensor.sun", "sun.sun", "weather.",
            "sensor.brasileirao", "sensor.briefing",
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
        print(f"Source: domain filter (fallback) — {len(entities)} entities")

    entities_sorted = sorted(entities, key=lambda x: x["entity_id"])
    monitor_count = sum(1 for e in entities_sorted if e.get("monitor", True))
    source = "entity_registry" if exposed_ids else "domain_filter"

    # v7.5-C — detectar entidades novas de classe sensível
    candidate_ids = exposed_ids if exposed_ids else {s.get("entity_id") for s in states}
    new_entity_ids = [eid for eid in candidate_ids if eid not in existing]
    sensitive_new = detect_sensitive_new(new_entity_ids, states_by_id)
    save_json(PENDING_PRIORITY_PATH, {"entities": sensitive_new})
    if sensitive_new:
        print(f"Entidades sensíveis novas: {len(sensitive_new)} — pending_priority.json atualizado")
    else:
        print("Nenhuma entidade sensível nova detectada.")

    output = {
        "updated_at": datetime.now().isoformat(),
        "source": source,
        "count": monitor_count,
        "entities": entities_sorted,
    }

    save_json(ENTITIES_PATH, output)
    print(f"OK: {len(entities_sorted)} total entities ({monitor_count} monitored) saved to {ENTITIES_PATH}")


if __name__ == "__main__":
    main()
