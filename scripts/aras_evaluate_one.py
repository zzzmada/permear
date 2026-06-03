#!/usr/bin/env python3
"""
Evaluates a single candidate via the ARAS Filter. Used by the priority=2
entity-alert automation (permear_aras_priority_alerts). Returns JSON
{decision, salience, rationale, content}.

Usage: aras_evaluate_one.py '<content>' '<entity_id>'
"""
import sys
import os
import json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import ENTITIES_PATH, GUIDELINES_PATH, PRIMARY_RESIDENT
from lib.memory import load_json
from lib.memory_db import get_today_emitted_keys
from lib.aras_filter import evaluate_salience


def main():
    content = sys.argv[1] if len(sys.argv) > 1 else ""
    entity_id = sys.argv[2] if len(sys.argv) > 2 else None

    guidelines = load_json(GUIDELINES_PATH, {})
    resident = guidelines.get("residents", {}).get(PRIMARY_RESIDENT, {})
    monitored = load_json(ENTITIES_PATH, {"entities": []})
    # SD5: recent_alerts from the DB (source='heartbeat', today) — was interacoes[] in JSON
    recent_keys = get_today_emitted_keys()
    # v7.7-A: orphan priority — ignore monitor:false
    priorities = {
        e["entity_id"]: int(e.get("priority", 0))
        for e in monitored.get("entities", [])
        if e.get("entity_id") and e.get("monitor", True)
    }

    # canonical key for the candidate
    ctype = "event"
    key = f"{ctype}:{entity_id}" if entity_id else f"{ctype}:{content[:40].lower().strip()}"
    candidate = {
        "type": ctype,
        "content": content,
        "entity_id": entity_id,
        "key": key,
        "timestamp": datetime.now().isoformat(),
    }
    user_state = {
        "restrictions": resident.get("restrictions", []),
        "recent_alerts": recent_keys,
        "entity_priorities": priorities,
        "current_hour": datetime.now().hour,
    }

    result = evaluate_salience(candidate, user_state)
    result["content"] = content
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
