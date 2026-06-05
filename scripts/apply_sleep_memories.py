#!/usr/bin/env python3
"""SD5 — Receives JSON array of memories from ai_task, writes to Organic Memory DB.
Each memory may optionally carry [entity:<entity_id>] at the end.
If entity_id is valid (present in monitored_entities.json), the key is set to
observation:<entity_id> for deterministic reinforce. Otherwise written keyless.
"""
import json, sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.memory_db import init_db, add_or_reinforce

ENTITY_TAG = re.compile(r'\[entity:([^\]]+)\]\s*$')


def _load_valid_entity_ids():
    from permear_config import ENTITIES_PATH
    try:
        with open(ENTITIES_PATH) as f:
            data = json.load(f)
        return {e["entity_id"] for e in data.get("entities", []) if e.get("entity_id")}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return set()


def parse_memory(raw: str):
    """Split raw memory string into (content, key|None).
    key = 'observation:<entity_id>' if entity tag is valid; None otherwise.
    """
    m = ENTITY_TAG.search(raw)
    if not m:
        return raw.strip(), None
    entity_id = m.group(1).strip()
    content = raw[:m.start()].strip()
    return content, entity_id


def main():
    if len(sys.argv) < 2:
        print("Uso: apply_sleep_memories.py '<json_array>'")
        sys.exit(1)
    try:
        novas = json.loads(sys.argv[1].strip())
        if not isinstance(novas, list):
            raise ValueError("esperado array JSON")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"JSON invalido: {e}. Descartando.")
        sys.exit(0)
    if not novas:
        print("Lista vazia — nada a gravar.")
        sys.exit(0)
    init_db()
    valid_ids = _load_valid_entity_ids()
    new_c = reinforced = skipped = 0
    for raw in novas:
        raw = (raw or "").strip()
        if not raw:
            continue
        content, entity_id = parse_memory(raw)
        if not content:
            skipped += 1
            continue
        # Validate entity_id; discard if not in monitored_entities
        if entity_id and entity_id in valid_ids:
            key = f"observation:{entity_id}"
        else:
            key = None
        _, was_new, _ = add_or_reinforce(content, kind="observation", source="daily", key=key)
        if was_new:
            new_c += 1
        else:
            reinforced += 1
    print(f"OK DB: +{new_c} nova(s), {reinforced} reforçada(s), {skipped} ignorada(s)")


if __name__ == "__main__":
    main()
