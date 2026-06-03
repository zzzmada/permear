#!/usr/bin/env python3
"""v7.5-B — ARAS attention sensor. Reads the day's accumulated stats."""
import json
import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permear_config import MEMORY_DIR
from lib.memory import load_json

ATTENTION_PATH = os.path.join(MEMORY_DIR, "aras_stats.json")


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    stats = load_json(ATTENTION_PATH, {})
    if stats.get("data") != today:
        stats = {"data": today, "total": 0, "emit": 0,
                 "gray": 0, "suppress": 0, "llm_calls": 0}

    total = stats.get("total", 0)
    suppress = stats.get("suppress", 0)
    taxa = round(100 * suppress / total, 1) if total else 0.0

    out = {
        "state": taxa,
        "emitidos_hoje": stats.get("emit", 0),
        "suprimidos_hoje": suppress,
        "cinzentos_hoje": stats.get("gray", 0),
        "chamadas_llm_hoje": stats.get("llm_calls", 0),
        "total_avaliado_hoje": total,
        "threshold_emit_atual": stats.get("emit_threshold"),  # v7.9-C: None until the first cycle
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
